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

from fastapi import UploadFile
from fred_core import KeycloakUser, TagPermission
from fred_core.documents.document_structures import DocumentMetadata

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.ingestion.ingestion_controller import (
    cleanup_uploaded_temp_file,
    uploadfile_to_path,
)
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.library_sync.structures import (
    DocumentRemoved,
    DocumentWritten,
    InvalidSourceRequest,
    split_document_path,
    validate_source_key,
    validate_version,
)
from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService
from knowledge_flow_backend.features.scheduler.activities import output_process
from knowledge_flow_backend.features.scheduler.push_files_activities import push_input_process
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess
from knowledge_flow_backend.features.tag.structure import Tag, TagCreate, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService

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
    ) -> DocumentWritten:
        """Write one document, addressed by the caller's key.

        Processing runs inline rather than being queued, so that the reply is an
        outcome the caller can act on. A queue ticket would be the progress
        stream again in another shape: it says the bytes were accepted, not that
        the document is in the library, and a failure after it would leave a
        half-built document behind with nobody listening.
        """
        # Authorization first: what a caller with no right over this library is
        # told must not depend on how well formed its request was.
        await self._rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, library_id)

        source_key = validate_source_key(source_key)
        document_version = validate_version(document_version, label="A document version", code_prefix="document_version")
        folders, document_name = split_document_path(path)

        library = await self._tag_store.get_tag_by_id(library_id)
        folder_id = await self._resolve_folder(user, library, folders)
        existing = await self._metadata_store.get_metadata_by_source_key(library_id, source_key)
        if existing is not None:
            await self._refile(user, existing, folder_id)

        profile = ApplicationContext.get_instance().get_config().processing.default_profile
        # Both copy bytes — off the upload, then into the content store. On this
        # surface a whole source's worth of them arrives concurrently, so neither
        # runs on the event loop.
        input_file = await asyncio.to_thread(uploadfile_to_path, upload, filename=document_name)
        metadata: DocumentMetadata | None = None
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
            metadata = await push_input_process(user=user, metadata=metadata, input_file=str(input_file), profile=profile)
            await output_process(
                file=FileToProcess(
                    document_uid=metadata.document_uid,
                    external_path=None,
                    source_tag=source_tag,
                    tags=[folder_id],
                    profile=profile,
                    processed_by=user,
                ),
                metadata=metadata,
                accept_memory_storage=True,
            )
        except Exception:
            if existing is None and metadata is not None:
                # Nothing was there before this call, so nothing of it should
                # survive the failure. An update is left alone on purpose:
                # discarding it would destroy a document the caller asked to
                # replace, not to remove, and its next write converges anyway.
                await self._discard(user.uid, metadata.document_uid)
            raise
        finally:
            await asyncio.to_thread(cleanup_uploaded_temp_file, input_file)

        logger.info(
            "[LIBRARY SYNC] library=%s key=%s created=%s by=%s",
            library_id,
            source_key,
            existing is None,
            user.uid,
        )
        return DocumentWritten(
            source_key=source_key,
            path=path,
            document_version=document_version,
            created=existing is None,
        )

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

        for tag_id in list(existing.tags.tag_ids or []):
            await self._metadata_service.remove_tag_id_from_document(user, existing, tag_id)
        logger.info("[LIBRARY SYNC] library=%s key=%s removed by=%s", library_id, source_key, user.uid)
        return DocumentRemoved(source_key=source_key, removed=True)

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

    # ---------- internals ----------

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
