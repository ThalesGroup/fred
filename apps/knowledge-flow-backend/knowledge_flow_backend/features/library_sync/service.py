# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Writing into a library on behalf of a system that synchronizes a source.

The other ingestion surface serves a person picking files in a browser, and
mints a fresh document per upload so two uploads keep two versions. A system
mirroring a source needs the opposite: the same name written twice is the same
document again. So a document here is addressed by a key the caller chose,
looked up rather than derived, and everything underneath — storage, processing,
permissions, accounting — is the one the other surface already uses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import BackgroundTasks, UploadFile
from fred_core import KeycloakUser, TagPermission
from fred_core.documents.document_structures import DocumentMetadata
from fred_core.tasks.models import IngestionProcessingProfile as TaskProfile
from fred_core.tasks.models import StartIngestionParams, StartIngestionRequest, TaskTarget
from fred_core.tasks.service import TaskService
from sqlalchemy.exc import IntegrityError

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.ingestion.ingestion_controller import (
    cleanup_uploaded_temp_file,
    resolve_tag_owners,
    uploadfile_to_path,
)
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.library_sync.structures import (
    DocumentAccepted,
    DocumentRemoved,
    InvalidSourceRequest,
    LibraryDocument,
    LibraryDocuments,
    SynchronizationUnavailable,
    document_state,
    split_document_path,
    validate_source_key,
    validate_synchronized_by,
    validate_version,
)
from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService
from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionAlreadyActive
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcessWithoutUser
from knowledge_flow_backend.features.tag.structure import Tag, TagCreate, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.models.task_models import ACTIVE_DOCUMENT_INDEX

logger = logging.getLogger(__name__)


class LibrarySyncService:
    """One library, one synchronizing caller, documents addressed by its own keys."""

    def __init__(self) -> None:
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self._metadata_store = context.get_metadata_store()
        self._rebac = context.get_rebac_engine()
        self._metadata_service = MetadataService()
        self._tag_service = TagService()
        self._ingestion_service = get_ingestion_service()
        self._task_service: TaskService = context.get_task_service()
        # Built as the upload surface builds its own, so both feed one pipeline.
        config = context.get_config()
        self._scheduler: IngestionTaskService | None = None
        if config.scheduler.enabled:
            self._scheduler = IngestionTaskService(
                scheduler_config=config.scheduler,
                processing_config=config.processing,
                metadata_service=self._ingestion_service.metadata_service,
                max_parallelism=config.scheduler.temporal.ingestion_workflow_parallelism,
            )

    # ---------- documents ----------

    async def write_document(
        self,
        user: KeycloakUser,
        *,
        library_id: str,
        path: str,
        source_key: str,
        document_version: Optional[str],
        source_tag: str,
        upload: UploadFile,
        profile: IngestionProcessingProfile = IngestionProcessingProfile.medium,
        background_tasks: BackgroundTasks | None = None,
    ) -> DocumentAccepted:
        """Write one document, addressed by the caller's key.

        The bytes are stored and the write is accepted; processing runs on the
        pipeline every upload goes through, and the returned task is how the
        caller follows it to an outcome.
        """
        # Authorization first: what a caller with no right over this library is
        # told must not depend on how well formed its request was.
        await self._rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_id)

        source_key = validate_source_key(source_key)
        document_version = validate_version(document_version, label="A document version", code_prefix="document_version")
        folders, document_name = split_document_path(path)
        if self._scheduler is None:
            # Refused before a folder is made or a byte is read: a deployment
            # that cannot process a document must not half-take it.
            raise SynchronizationUnavailable("This deployment has no scheduler enabled, so it cannot process documents.")

        library = await self._tag_store.get_tag_by_id(library_id)
        folder_id = await self._resolve_folder(user, library, folders)
        existing = await self._metadata_store.get_metadata_by_source_key(library_id, source_key)
        if existing is not None:
            await self._refile(user, existing, folder_id)
        owning_team_id = await self._owning_team_id(user, folder_id)

        # Both copy bytes — off the upload, then into the content store. On this
        # surface a whole source's worth of them arrives concurrently, so neither
        # runs on the event loop.
        input_file = await asyncio.to_thread(uploadfile_to_path, upload, filename=document_name)
        metadata: DocumentMetadata | None = None
        task_id: str | None = None
        submission_started = False
        try:
            metadata = await self._ingestion_service.extract_metadata(
                user,
                file_path=input_file,
                tags=[folder_id],
                source_tag=source_tag,
                profile=profile,
                # The suffix-based draft version is what makes two uploads two
                # documents. Here the key already says they are one.
                apply_versioning=False,
            )
            if existing is not None:
                # The identifier is reused, never recomputed from the key: this
                # surface adds no second identity scheme, and a caller never has
                # to learn the one Fred uses.
                metadata.identity.document_uid = existing.identity.document_uid
                metadata.source.date_added_to_kb = existing.source.date_added_to_kb
            metadata.source.source_library_id = library_id
            metadata.source.source_key = source_key
            metadata.source.document_version = document_version

            await asyncio.to_thread(self._ingestion_service.save_input, user, metadata, input_file.parent)
            await self._ingestion_service.save_metadata(user, metadata=metadata)
            if existing is not None:
                await self._drop_previous_vectors(metadata.document_uid)

            # The task comes first and is not optional: it is the only thing
            # the caller gets back to follow the write with.
            try:
                task = await self._task_service.start(
                    StartIngestionRequest(params=StartIngestionParams(resource_ids=[metadata.document_uid], profile=TaskProfile(profile.value))),
                    created_by=user.uid,
                    team_id=owning_team_id,
                    target=TaskTarget(type="document", id=metadata.document_uid, label=document_name),
                )
            except IntegrityError as exc:
                if ACTIVE_DOCUMENT_INDEX in str(exc.orig):
                    raise IngestionAlreadyActive("Ingestion is already active for this document") from exc
                raise
            task_id = task.task_id
            submission_started = True
            await self._scheduler.submit_documents(
                user=user,
                pipeline_name="library_sync",
                files=[
                    FileToProcessWithoutUser(
                        source_tag=source_tag,
                        tags=[folder_id],
                        document_uid=metadata.document_uid,
                        display_name=document_name,
                        profile=profile,
                        task_id=task_id,
                    )
                ],
                background_tasks=background_tasks,
            )

            logger.info(
                "[LIBRARY SYNC] library=%s key=%s created=%s task=%s by=%s",
                library_id,
                source_key,
                existing is None,
                task_id,
                user.uid,
            )
            return DocumentAccepted(
                source_key=source_key,
                path=path,
                document_version=document_version,
                created=existing is None,
                document_uid=metadata.document_uid,
                task_id=task_id,
            )
        except IngestionAlreadyActive:
            # The existing admission owns this document; never discard its input.
            raise
        except Exception:
            if task_id is not None:
                try:
                    await self._task_service.fail_task(task_id, "Ingestion admission failed", only_if_unbound=True)
                except Exception:
                    logger.warning("Could not settle unsubmitted ingestion task %s", task_id, exc_info=True)
            if not submission_started and existing is None and metadata is not None:
                # Nothing was there before this call, so nothing of it should
                # survive the failure. An update is left alone on purpose:
                # discarding it would destroy a document the caller asked to
                # replace, not to remove, and its next write converges anyway.
                await self._discard(user.uid, metadata.document_uid)
            raise
        finally:
            # The worker restores the input from the content store, so the
            # upload's copy is done with the moment the write is answered.
            await asyncio.to_thread(cleanup_uploaded_temp_file, input_file)

    async def remove_document(self, user: KeycloakUser, *, library_id: str, source_key: str) -> DocumentRemoved:
        """Take one document out of the library, addressed by the same key.

        The library itself is never read or rewritten: a caller that had to send
        the folder's own name and description back to drop one document could
        rename that folder by getting one field wrong, and two callers doing it
        would lose each other's work.
        """
        await self._rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_id)
        source_key = validate_source_key(source_key)

        existing = await self._metadata_store.get_metadata_by_source_key(library_id, source_key)
        if existing is None:
            # A source that removes what it already removed is still in sync.
            return DocumentRemoved(source_key=source_key, removed=False)

        folders = list(existing.tags.tag_ids or [])
        if folders:
            # Taking its last folder away is what deletes a document, and what
            # moves the storage charge and drops the permission links with it.
            for tag_id in folders:
                await self._metadata_service.remove_tag_id_from_document(user, existing, tag_id)
        else:
            # A keyed document in no folder at all — a platform import that
            # carried the key but not the membership. There is no folder to take
            # away, so removing one would report success and leave the document,
            # its content and the key it holds behind. Authorization was the
            # library's, which is the library this document names as its own.
            await self._metadata_service.delete_document_and_artifacts_trusted(user.uid, existing.document_uid)
        logger.info("[LIBRARY SYNC] library=%s key=%s removed by=%s", library_id, source_key, user.uid)
        return DocumentRemoved(source_key=source_key, removed=True)

    async def list_documents(self, user: KeycloakUser, *, library_id: str, limit: int) -> LibraryDocuments:
        """What the library holds under the caller's keys, and where each write stands.

        Only keyed documents: a person's upload into the same library has no
        key, so the caller could neither address it nor tell whether it is in
        sync. Bounded, and honest about it — a page short of the whole library
        says so rather than passing for it.
        """
        await self._rebac.check_user_permission_or_raise(user, TagPermission.READ, library_id)
        # One past the page: enough to know there is more, without counting it all.
        rows = await self._metadata_store.list_by_source_library(library_id, limit=limit + 1)
        items = [
            LibraryDocument(
                source_key=row.source.source_key,
                document_uid=row.document_uid,
                document_version=row.source.document_version,
                state=document_state(row.processing),
            )
            for row in rows[:limit]
            if row.source.source_key is not None
        ]
        return LibraryDocuments(items=items, truncated=len(rows) > limit)

    # ---------- the library's own source version ----------

    async def read_source_version(self, user: KeycloakUser, library_id: str) -> Optional[str]:
        await self._rebac.check_user_permission_or_raise(user, TagPermission.READ, library_id)
        library = await self._tag_store.get_tag_by_id(library_id)
        return library.source_version

    async def record_source_version(self, user: KeycloakUser, library_id: str, source_version: Optional[str]) -> Optional[str]:
        await self._rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_id)
        source_version = validate_version(source_version, label="A source version", code_prefix="source_version")
        library = await self._tag_store.get_tag_by_id(library_id)
        library.source_version = source_version
        # `updated_at` is left where it is: a cursor moves on every poll, and
        # bumping it would put the folder at the top of "recently changed" for
        # runs that changed nothing in it.
        await self._tag_store.update_tag_by_id(library_id, library)
        return source_version

    # ---------- the machine that fills the library ----------

    async def record_synchronized_by(self, user: KeycloakUser, library_id: str, synchronized_by: str) -> str:
        """Record which machine fills this library, which is what closes it to people.

        Moving a library from one machine to another is refused rather than
        applied: two of them filling one folder is a fault upstream, and taking
        the second silently would leave the first writing into a folder it no
        longer owns. Re-recording the same one is not a move, so a retry is safe.
        """
        await self._rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_id)
        synchronized_by = validate_synchronized_by(synchronized_by)

        library = await self._tag_store.get_tag_by_id(library_id)
        if library.synchronized_by == synchronized_by:
            return synchronized_by
        if library.synchronized_by is not None:
            raise InvalidSourceRequest(
                "synchronized_by_conflict",
                f"This library is already filled by {library.synchronized_by}.",
            )

        library.synchronized_by = synchronized_by
        await self._tag_store.update_tag_by_id(library_id, library)
        logger.info("[LIBRARY SYNC] library=%s is filled by %s", library_id, synchronized_by)
        return synchronized_by

    # ---------- internals ----------

    async def _owning_team_id(self, user: KeycloakUser, folder_id: str) -> Optional[str]:
        """The team a task for this folder is filed under; None for a personal space.

        Resolved by the upload surface's own lookup, so a task from either
        surface lands on the same team's activity page.
        """
        team_ids, _ = await resolve_tag_owners([folder_id], user)
        return next(iter(team_ids)) if len(team_ids) == 1 else None

    async def _resolve_folder(self, user: KeycloakUser, library: Tag, folders: list[str]) -> str:
        """Walk the path inside the library, creating the folders that are missing.

        Creation is authorized by the right to write in the parent, so one grant
        over a library reaches its whole subtree and nothing outside it. Folders
        carry the library's owner, not the caller's: a folder owned by the pod
        would sit outside the library's own namespace.
        """
        owner_id = library.owner_id
        # `team_id` here only says which owner the folder belongs to. Passing the
        # caller's own id as a team would claim it owns them, so a library that
        # is the caller's own personal space passes none and gets the same owner.
        team_id = owner_id if owner_id != user.uid else None

        folder_id = library.id
        parent_path = library.full_path
        for name in folders:
            full_path = f"{parent_path}/{name}"
            existing = await self._tag_store.get_by_owner_type_full_path(
                owner_id=owner_id,
                tag_type=TagType.DOCUMENT,
                full_path=full_path,
            )
            if existing is None:
                try:
                    folder = TagCreate(name=name, path=parent_path, description=None, type=TagType.DOCUMENT, team_id=team_id)
                except ValueError as exc:
                    # A folder rule the caller broke — a path too deep for the
                    # library it starts from, above all. That is a bad request,
                    # not a server fault, and it must read as one.
                    raise InvalidSourceRequest("document_path_invalid", f"{full_path}: {exc}") from exc
                created = await self._tag_service.create_tag_for_user(folder, user)
                folder_id = created.id
            else:
                folder_id = existing.id
            parent_path = full_path
        return folder_id

    async def _drop_previous_vectors(self, document_uid: str) -> None:
        """Take the revision being replaced out of the index before re-embedding.

        A chunk's id is derived from where it sits in the content, so a new
        revision's chunks land beside the old ones instead of over them. Left
        alone, search keeps returning text the document no longer contains, and
        a source watched for months grows an index of every revision it ever
        had — which is the defect this surface exists to remove, one layer down.

        The same step the revectorize workflow takes before re-embedding a
        document it is rebuilding from stored content.
        """
        context = ApplicationContext.get_instance()
        vector_store = context.get_create_vector_store(context.get_embedder())
        await asyncio.to_thread(vector_store.delete_vectors_for_document, document_uid=document_uid)

    async def _refile(self, user: KeycloakUser, existing: DocumentMetadata, folder_id: str) -> None:
        """Put a document where its source now says it is.

        Run before anything is written, so a folder the caller may not write in
        refuses the whole call rather than half of it. Rewriting `tag_ids`
        directly would be shorter and wrong: a document's permissions and its
        storage charge both hang off one link per folder, and only these two
        paths move them.
        """
        current = list(existing.tags.tag_ids or [])
        if current == [folder_id]:
            return
        if folder_id not in current:
            await self._metadata_service.add_tag_id_to_document(user, existing, folder_id)
        for stale in [tag_id for tag_id in current if tag_id != folder_id]:
            await self._metadata_service.remove_tag_id_from_document(user, existing, stale)

    async def _discard(self, actor_uid: str, document_uid: str) -> None:
        """Leave nothing behind from a write that never completed.

        Asks for the full delete first whatever stage the write reached: a row
        can exist even when the call that was writing it raised — the follow-ups
        that credit storage and link permissions run after it — and only that
        path releases what the row was charged. `MetadataNotFound` then means
        there is genuinely no row, and only loose bytes to reclaim.
        """
        try:
            await self._metadata_service.delete_document_and_artifacts_trusted(actor_uid, document_uid)
        except MetadataNotFound:
            await self._metadata_service.purge_document_artifacts(document_uid)
        except Exception:  # noqa: BLE001
            # The failure the caller needs to see is the one being raised, not
            # this one; an artifact left over is what the corpus audit is for.
            logger.warning("[LIBRARY SYNC] Could not discard the partial document %s", document_uid, exc_info=True)
