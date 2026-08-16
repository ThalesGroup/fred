# Copyright Thales 2025
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
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fred_core import (
    ORGANIZATION_ID,
    DocumentPermission,
    KeycloakUser,
    OrganizationPermission,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TagPermission,
    TeamMetadataStore,
    get_user_store,
)
from fred_core.common.team_id import TeamId
from fred_core.documents.document_store import DocumentMetadataDeserializationError as MetadataDeserializationError
from fred_core.documents.document_structures import (
    DocumentMetadata,
    ProcessingStage,
    ProcessingStatus,
)
from fred_core.sql.async_session import make_session_factory
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorStore
from knowledge_flow_backend.features.metadata.metadata_utils import normalize_labels
from knowledge_flow_backend.features.tabular.artifacts import (
    TABULAR_EXTENSION_KEY,
    TABULAR_MULTI_EXTENSION_KEY,
    document_artifact_prefix,
    read_tabular_artifact,
    read_tabular_multi_artifact,
)

logger = logging.getLogger(__name__)

# --- Domain Exceptions ---


class MetadataNotFound(Exception):
    pass


class MetadataUpdateError(Exception):
    pass


class InvalidMetadataRequest(Exception):
    pass


class DocumentNameCollisionError(Exception):
    pass


class StoreAuditFinding(BaseModel):
    document_uid: str
    document_name: str | None = None
    source_tag: str | None = None
    present_in_metadata: bool
    present_in_vector_store: bool
    present_in_content_store: bool
    vector_chunks: int | None = Field(default=None, description="Number of chunks in vector store (when available)")
    issues: list[str] = Field(default_factory=list)


class StoreAuditReport(BaseModel):
    has_anomalies: bool
    total_seen: int
    metadata_count: int
    vector_count: int
    content_count: int
    anomalies: list[StoreAuditFinding] = Field(default_factory=list)


class StoreAuditFixResponse(BaseModel):
    before: StoreAuditReport
    after: StoreAuditReport
    reset_metadata: list[str] = Field(
        default_factory=list,
        description="Documents whose lying processing stage (missing_content/missing_vectors) was reset to NOT_STARTED. Never deleted — see fix_store_anomalies.",
    )


class MetadataService:
    """
    Service for managing metadata operations.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.config = context.get_config()
        self.metadata_store = context.get_metadata_store()
        self.vector_store = None
        self.content_store = context.get_content_store()
        self.rebac = context.get_rebac_engine()

    async def filter_readable_document_uids(self, user: KeycloakUser, document_uids: list[str]) -> set[str]:
        """Return only the document UIDs the user is allowed to read (individual permission checks)."""
        if not document_uids:
            return set()
        results = await asyncio.gather(*(self.rebac.has_user_permission(user, DocumentPermission.READ, uid) for uid in document_uids))
        return {uid for uid, allowed in zip(document_uids, results) if allowed}

    async def get_documents_metadata(self, user: KeycloakUser, filters_dict: dict) -> list[DocumentMetadata]:
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        try:
            docs = await self.metadata_store.get_all_metadata(filters_dict)

            if isinstance(authorized_doc_ref, RebacDisabledResult):
                # if rebac is disabled, do not filter
                return docs

            # Filter by permission (todo: use rebac ids to filter at store (DB) level)
            authorized_doc_ids = [d.id for d in authorized_doc_ref]
            return [d for d in docs if d.identity.document_uid in authorized_doc_ids]
        except MetadataDeserializationError as e:
            logger.error(f"[Metadata] Deserialization error: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")

        except Exception as e:
            logger.error(f"Error retrieving document metadata: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

    async def get_documents_by_uids(self, user: KeycloakUser, document_uids: list[str]) -> list[DocumentMetadata]:
        """Targeted, ReBAC-filtered metadata fetch for an already-known uid
        set — the indexed sibling of `get_documents_metadata`: a single
        `document_uid IN (...)` store query (`get_metadata_by_uids`) instead
        of `get_all_metadata`'s full-table scan filtered in Python. Use this
        whenever the caller already has the uids (e.g. an authorized folder's
        item_ids, or a label resolution) and only needs their metadata."""
        if not document_uids:
            return []
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        docs = await self.metadata_store.get_metadata_by_uids(document_uids)
        if isinstance(authorized_doc_ref, RebacDisabledResult):
            return docs
        authorized_doc_ids = {d.id for d in authorized_doc_ref}
        return [d for d in docs if d.identity.document_uid in authorized_doc_ids]

    async def get_document_metadata_in_tag(self, user: KeycloakUser, tag_id: str) -> list[DocumentMetadata]:
        """
        Return all metadata entries associated with a specific tag.
        """
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        try:
            docs = await self.metadata_store.get_metadata_in_tag(tag_id)

            if isinstance(authorized_doc_ref, RebacDisabledResult):
                # if rebac is disabled, do not filter
                return docs

            # Filter by permission (todo: use rebac ids to filter at store (DB) level)
            authorized_doc_ids = [d.id for d in authorized_doc_ref]
            return [d for d in docs if d.identity.document_uid in authorized_doc_ids]
        except Exception as e:
            logger.error(f"Error retrieving metadata for tag {tag_id}: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata for tag {tag_id}: {e}")

    async def get_document_metadata(self, user: KeycloakUser, document_uid: str) -> DocumentMetadata:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        try:
            metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        except Exception as e:
            logger.error(f"Error retrieving metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to get metadata: {e}")

        if metadata is None:
            raise MetadataNotFound(f"No document found with UID {document_uid}")

        return metadata

    async def get_document_vectors(self, user: KeycloakUser, document_uid: str) -> list[dict]:
        """
        Return the list of vectors associated with the document's chunks.

        Each item contains at minimum:
          - chunk_uid: unique identifier of the chunk
          - vector: the list of floats representing the embedding
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        # Specific permission on the document
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        # Ensure the document exists (and raise 404 otherwise)
        _ = await self.get_document_metadata(user, document_uid)

        # Initialize the vector store on demand
        if self.vector_store is None:
            self.vector_store = ApplicationContext.get_instance().get_vector_store()

        store = self.vector_store
        if store is None:
            logger.warning("[MetadataService] No vector store available to retrieve vectors")
            return []

        # Optional method on Chroma store side
        if hasattr(store, "get_vectors_for_document"):
            try:
                return store.get_vectors_for_document(document_uid)  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"[MetadataService] Error retrieving vectors: {e}")
                return []

        logger.info("[MetadataService] The vector store does not support retrieving vectors by document")
        return []

    async def get_document_chunks(self, user: KeycloakUser, document_uid: str) -> list[dict]:
        """
        Return the list of chunks associated with the document.

        Each item contains at minimum:
          - chunk_uid: unique identifier of the chunk
          - text: the text content of the chunk
          - metadata: the metadata of the chunk
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        # Specific permission on the document
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        # Ensure the document exists (and raise 404 otherwise)
        _ = await self.get_document_metadata(user, document_uid)

        # Initialize the vector store on demand
        if self.vector_store is None:
            self.vector_store = ApplicationContext.get_instance().get_vector_store()

        store = self.vector_store
        if store is None:
            logger.warning("[MetadataService] No vector store available to retrieve chunks")
            return []

        # Optional method on Chroma store side
        if hasattr(store, "get_chunks_for_document"):
            try:
                return store.get_chunks_for_document(document_uid)  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"[MetadataService] Error retrieving chunks: {e}")
                return []

        logger.info("[MetadataService] The vector store does not support retrieving chunks by document")
        return []

    async def browse_documents_in_tag(self, user: KeycloakUser, tag_id: str, offset: int = 0, limit: int = 50) -> tuple[list[DocumentMetadata], int]:
        """
        Paginated fetch of documents in a given tag.
        """
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        docs, total = await self.metadata_store.browse_metadata_in_tag(tag_id, offset=offset, limit=limit)
        logger.debug(
            "[PAGINATION] browse_documents_in_tag tag=%s offset=%s limit=%s -> fetched=%s total=%s",
            tag_id,
            offset,
            limit,
            len(docs),
            total,
        )

        if isinstance(authorized_doc_ref, RebacDisabledResult):
            return docs, total

        authorized_doc_ids = {d.id for d in authorized_doc_ref}
        filtered = [d for d in docs if d.identity.document_uid in authorized_doc_ids]

        # Total reflects store count; computing an authorized-only total would require
        # scanning all authorized documents. We keep store total to preserve pagination hints.
        return filtered, total

    async def total_size_by_tags(self, user: KeycloakUser, tag_ids: list[str]) -> dict[str, int]:
        """Total bytes of the documents in each library tag (folder), reliable and
        not paginated. Like the `total` count returned by browse, the sum is
        computed store-side over the whole tag rather than per-document authz
        filtered — folders the user can browse already expose their doc count.
        """
        return await self.metadata_store.total_size_by_tags(tag_ids)

    async def get_chunk(self, user: KeycloakUser, document_uid: str, chunk_uid: str) -> dict:
        """
        Return chunk.

        item contains at minimum:
          - chunk_uid: unique identifier of the chunk
          - text: the text content of the chunk
          - metadata: the metadata of the chunk
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        if not chunk_uid:
            raise InvalidMetadataRequest("Chunk UID cannot be empty")

        # Specific permission on the document
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        # Initialize the vector store on demand
        if self.vector_store is None:
            self.vector_store = ApplicationContext.get_instance().get_vector_store()

        store = self.vector_store
        if store is None:
            logger.warning("[MetadataService] No vector store available to retrieve chunk")
            return {"chunk_uid": chunk_uid}

        # Optional method on Chroma store side
        if hasattr(store, "get_chunk"):
            try:
                return store.get_chunk(document_uid=document_uid, chunk_uid=chunk_uid)  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"[MetadataService] Error retrieving chunk: {e}")
                return {"chunk_uid": chunk_uid}

        logger.info("[MetadataService] The vector store does not support retrieving chunk")
        return {"chunk_uid": chunk_uid}

    async def delete_chunk(self, user: KeycloakUser, document_uid: str, chunk_uid: str) -> None:
        """
        Delete chunk.
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        if not chunk_uid:
            raise InvalidMetadataRequest("Chunk UID cannot be empty")

        # Specific permission on the document
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.DELETE, document_uid)

        # Initialize the vector store on demand
        if self.vector_store is None:
            self.vector_store = ApplicationContext.get_instance().get_vector_store()

        store = self.vector_store
        if store is None:
            logger.warning("[MetadataService] No vector store available to delete chunk")
            return None

        # Optional method on Chroma store side
        if hasattr(store, "delete_chunk"):
            try:
                return store.delete_chunk(document_uid=document_uid, chunk_uid=chunk_uid)  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"[MetadataService] Error deleting chunk: {e}")
                return None

        logger.info("[MetadataService] The vector store does not support retrieving chunk")
        return None

    async def add_tag_id_to_document(self, user: KeycloakUser, metadata: DocumentMetadata, new_tag_id: str, consistency_token: str | None = None) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, new_tag_id, consistency_token=consistency_token)

        try:
            if metadata.tags is None:
                raise MetadataUpdateError("DocumentMetadata.tags is not initialized")

            # Avoid duplicate tags
            tag_ids = metadata.tags.tag_ids or []
            if new_tag_id not in tag_ids:
                previous_tag_ids = set(tag_ids)
                tag_ids.append(new_tag_id)
                metadata.tags.tag_ids = tag_ids
                metadata.identity.modified = datetime.now(timezone.utc)
                metadata.identity.last_modified_by = user.uid
                # Save the tag and move the charge to the newly owning team/user in
                # ONE transaction. Without the charge the document is free for its
                # new owner and deleting it later decrements a counter that was
                # never charged; doing it in a second transaction let the tag land
                # while the charge silently failed (#2149 review findings).
                await self._save_and_move_storage(metadata, old_tags=previous_tag_ids, new_tags=set(tag_ids), user=user)
                await self._set_tag_as_parent_in_rebac(new_tag_id, metadata.document_uid, actor_uid=user.uid)

                logger.info(f"[METADATA] Added tag '{new_tag_id}' to document '{metadata.document_name}' by '{user.uid}'")
            else:
                # The tag is already on the document, but the ReBAC parent write
                # may not have happened: it runs after the metadata+quota
                # transaction commits, so an OpenFGA failure leaves the tag stored
                # with no relation, and this branch is where the client's retry
                # lands. Short-circuiting here made that state permanent — the
                # document stayed inaccessible and charged, with no way to repair
                # it (#2149 review finding). The write is idempotent, so redoing
                # it costs nothing and makes a retry actually converge.
                logger.info(f"[METADATA] Tag '{new_tag_id}' already present on document '{metadata.document_name}' — reasserting its ReBAC parent.")
                await self._set_tag_as_parent_in_rebac(new_tag_id, metadata.document_uid, actor_uid=user.uid)

        except Exception as e:
            logger.error(f"Error updating retrievable flag for {metadata.document_name}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    async def remove_tag_id_from_document(self, user: KeycloakUser, metadata: DocumentMetadata, tag_id_to_remove: str) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id_to_remove)

        try:
            if not metadata.tags or not metadata.tags.tag_ids or tag_id_to_remove not in metadata.tags.tag_ids:
                logger.info(f"[METADATA] Tag '{tag_id_to_remove}' not found on document '{metadata.document_name}' — nothing to remove.")
                return

            # Snapshot the tags before mutating them: if this removal deletes the
            # document, storage ownership has to be resolved from the tags it had,
            # and the branch below leaves `tag_ids` empty.
            original_tag_ids = set(metadata.tags.tag_ids)

            # Remove tag
            new_ids = [t for t in metadata.tags.tag_ids if t != tag_id_to_remove]
            metadata.tags.tag_ids = new_ids

            if not new_ids:
                if ProcessingStage.VECTORIZED in metadata.processing.stages:
                    if self.vector_store is None:
                        self.vector_store = ApplicationContext.get_instance().get_vector_store()
                    try:
                        self.vector_store.delete_vectors_for_document(document_uid=metadata.document_uid)
                        logger.info(f"[METADATA] Deleted document '{metadata.document_name}' because no tags remain (last removed by '{user.uid}')")
                    except Exception as e:
                        logger.warning(f"Could not delete vector of'{metadata.document_name}': {e}")

                if ProcessingStage.SQL_INDEXED in metadata.processing.stages:
                    await self._delete_tabular_artifacts(metadata.document_uid, metadata=metadata)

                # Promote an alternate version (version=1) to base if present
                if getattr(metadata.identity, "version", 0) == 0:
                    try:
                        promoted = await self._promote_alternate_version(
                            canonical_name=metadata.identity.canonical_name or metadata.document_name,
                            source_tag=metadata.source.source_tag,
                            removed_tag_id=tag_id_to_remove,
                            actor=user.uid,
                        )
                        if promoted:
                            logger.info(
                                "[METADATA] Promoted draft version '%s' to base for canonical '%s' after removing '%s'.",
                                promoted.identity.document_uid,
                                promoted.identity.canonical_name,
                                tag_id_to_remove,
                            )
                    except Exception as e:
                        logger.warning("Failed to promote alternate version for '%s': %s", metadata.document_name, e)
                if self.content_store is not None:
                    try:
                        self.content_store.delete_content(metadata.document_uid)
                        logger.info(f"[CONTENT] Deleted content for document '{metadata.document_name}'")
                    except Exception as e:
                        logger.warning(f"[CONTENT] Could not delete content for '{metadata.document_name}': {e}")

                # Delete and release in one transaction: only the caller whose
                # conditional DELETE matched a row releases (so a concurrent
                # remover cannot credit the same bytes), and the counters commit
                # with the delete rather than in a transaction that can fail
                # separately and strand the bytes.
                await self._delete_and_release(metadata, tag_ids=original_tag_ids, user_id=user.uid)
                try:
                    from fred_core.kpi import KPIActor

                    tag_store = ApplicationContext.get_instance().get_tag_store()
                    removed_tag = await tag_store.get_tag_by_id(tag_id_to_remove)
                    team_id = removed_tag.owner_id if removed_tag else ""
                    kpi = ApplicationContext.get_instance().get_kpi_writer()
                    kpi.count(
                        "document.deleted_total",
                        1,
                        dims={
                            "source_type": metadata.source.source_type.value,
                            "file_type": metadata.file.file_type.value if metadata.file else "other",
                            "team_id": team_id,
                        },
                        actor=KPIActor(type="human", user_id=user.uid),
                    )
                except Exception as kpi_exc:  # noqa: BLE001
                    logger.warning("[METADATA][KPI] Failed to emit document.deleted_total: %s", kpi_exc)
                # TODO: remove all rebac relations for this document

            else:
                metadata.identity.modified = datetime.now(timezone.utc)
                metadata.identity.last_modified_by = user.uid
                # Save and release the tag owner that no longer holds this document,
                # in ONE transaction. Without the release a document shared across
                # two libraries left the losing team charged forever; in a separate
                # transaction the tag could move while the release failed silently
                # (#2149 review findings).
                await self._save_and_move_storage(metadata, old_tags=original_tag_ids, new_tags=set(new_ids), user=user)
                logger.info(f"[METADATA] Removed tag '{tag_id_to_remove}' from document '{metadata.document_name}' by '{user.uid}'")

            await self._remove_tag_as_parent_in_rebac(tag_id_to_remove, metadata.document_uid)

        except Exception as e:
            logger.error(f"Failed to remove tag '{tag_id_to_remove}' from document '{metadata.document_name}': {e}")
            raise MetadataUpdateError(f"Failed to remove tag: {e}")

    async def _delete_tabular_artifacts(self, document_uid: str, *, metadata: DocumentMetadata | None = None) -> None:
        """
        Delete dataset-centric tabular artifacts linked to one document.

        Why this exists:
        - Removing the last visible tag from a document must also remove its
          queryable Parquet revisions from the shared content store.

        How to use:
        - Call during destructive metadata cleanup paths only.
        - `metadata` is an optimization, not a requirement: with it, a document
          carrying no tabular payload skips the listing entirely. Without it
          (the row is already gone) the prefix is derived from the uid alone
          and listed unconditionally — an empty prefix simply deletes nothing.
        """

        if metadata is not None:
            artifact = read_tabular_artifact(metadata)
            multi_artifact = read_tabular_multi_artifact(metadata)
            if artifact is None and multi_artifact is None:
                logger.info("[TABULAR] No %s/%s payload found for '%s'", TABULAR_EXTENSION_KEY, TABULAR_MULTI_EXTENSION_KEY, metadata.document_name)
                return

        label = metadata.document_name if metadata else document_uid
        prefix = document_artifact_prefix(
            artifacts_prefix=self.config.storage.tabular_store.artifacts_prefix,
            document_uid=document_uid,
        )

        try:
            for stored_object in self.content_store.list_objects(prefix):
                self.content_store.delete_object(stored_object.key)
            logger.info("[TABULAR] Deleted tabular artifacts linked to '%s'", label)
        except Exception as e:
            logger.warning("Could not delete tabular artifacts for '%s': %s", label, e)

    async def delete_document_and_artifacts(
        self,
        user: KeycloakUser,
        document_uid: str,
    ) -> None:
        """
        Strong-delete one document plus all derived artifacts.

        Why this exists:
        - chat attachments ingested through fast-ingest must be removable later
          without depending on the "remove last tag" flow
        - the cleanup must remove vectors, stored content, tabular artifacts,
          and the metadata row in one explicit path

        How to use:
        - call with the authenticated user and the target `document_uid`
        - the method raises `MetadataNotFound` when the document no longer
          exists and `MetadataUpdateError` when cleanup fails unexpectedly
        """

        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.DELETE, document_uid)
        await self._delete_document_and_artifacts(actor_uid=user.uid, document_uid=document_uid)

    async def delete_document_and_artifacts_trusted(self, actor_uid: str, document_uid: str) -> None:
        """Same as `delete_document_and_artifacts`, but skips the per-document
        `DocumentPermission.DELETE` check — same trust convention as
        `save_document_metadata_trusted`.

        Why this exists: the cancel-an-ingestion cleanup
        (`features/scheduler/document_failure.py`) is a system obligation, not a
        user action. Authorization already happened at the cancel endpoint
        (`authorize_task_mutation`), and by the time the cleanup runs the
        uploader's ReBAC state may have moved on — they left the team, the
        tuple went with them — which must not strand a half-built document plus
        its content and vectors on disk.

        `actor_uid` is the real uploader, so the storage quota is released from
        the account it was charged to; it is an attribution, not a permission.
        Never call this from a router or any other user-facing service.
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        await self._delete_document_and_artifacts(actor_uid=actor_uid, document_uid=document_uid)

    async def purge_document_artifacts(self, document_uid: str, *, metadata: DocumentMetadata | None = None) -> None:
        """Delete everything a document produced outside its metadata row.

        Vectors, tabular Parquet revisions and stored content — the one
        definition of "the document's artifacts", so a new artifact kind is
        added here and every caller gets it.

        Addressed by uid, and callable when the metadata row is already gone:
        that is the case of a writer compensating for a document deleted under
        it (its thread could not be stopped, see
        `IngestionService.persist_progress`). Pass `metadata` when it is known
        so each delete can be skipped for a stage the document never reached;
        without it every store is asked, which is the safe default.

        Best-effort per store and never raises: a document whose row is already
        gone must not be blocked from having its bytes reclaimed because one
        store is briefly unavailable.
        """
        stages = metadata.processing.stages if metadata else {}
        label = metadata.document_name if metadata else document_uid

        if not metadata or ProcessingStage.VECTORIZED in stages:
            try:
                await asyncio.to_thread(self._vector_store().delete_vectors_for_document, document_uid=document_uid)
                logger.info("[METADATA] Deleted vectors for document '%s'", label)
            except Exception as exc:
                logger.warning("Could not delete vectors for '%s': %s", label, exc)

        if not metadata or ProcessingStage.SQL_INDEXED in stages:
            await self._delete_tabular_artifacts(document_uid, metadata=metadata)

        try:
            await asyncio.to_thread(self.content_store.delete_content, document_uid)
            logger.info("[CONTENT] Deleted content for document '%s'", label)
        except Exception as exc:
            logger.warning("[CONTENT] Could not delete content for '%s': %s", label, exc)

    def _vector_store(self) -> BaseVectorStore:
        """Resolve the vector store in whichever process is running.

        `get_vector_store` only returns an already-built instance and raises
        otherwise — true in a worker that has not vectorized anything yet, which
        is exactly where cancelled-ingestion cleanup runs. Fall back to the
        build-on-demand accessor every scheduler activity uses, or the delete
        would be skipped and the vectors silently orphaned.
        """
        context = ApplicationContext.get_instance()
        if self.vector_store is None:
            try:
                self.vector_store = context.get_vector_store()
            except ValueError:
                self.vector_store = context.get_create_vector_store(context.get_embedder())
        return self.vector_store

    async def _delete_document_and_artifacts(self, *, actor_uid: str, document_uid: str) -> None:
        try:
            metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
            if metadata is None:
                raise MetadataNotFound(f"No document found with UID {document_uid}")

            deleted_tag_ids = set(metadata.tags.tag_ids or []) if metadata.tags else set()
            # The row goes first, and that ordering is load-bearing: it is the
            # fence a writer racing this deletion tests against. Purging
            # artifacts first would leave the row alive for the seconds that
            # takes, so a late `update_metadata` would report success, the
            # writer would believe it won, and the bytes it wrote after the
            # purge would survive with no row pointing at them (#2315). With the
            # row gone first, every later writer is guaranteed to see "deleted"
            # and discard its own output.
            await self._delete_and_release(metadata, tag_ids=deleted_tag_ids, user_id=actor_uid)
            await self.purge_document_artifacts(document_uid, metadata=metadata)

            for tag_id in deleted_tag_ids:
                await self._remove_tag_as_parent_in_rebac(tag_id, metadata.document_uid)
        except MetadataNotFound:
            raise
        except Exception as exc:
            logger.error(
                "Failed to delete document and artifacts for %s: %s",
                document_uid,
                exc,
            )
            raise MetadataUpdateError(f"Failed to delete document and artifacts: {exc}") from exc

    async def update_document_retrievable(self, user: KeycloakUser, document_uid: str, value: bool, modified_by: str) -> None:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        try:
            metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
            if not metadata:
                raise MetadataNotFound(f"Document '{document_uid}' not found.")

            # 1) Update metadata-store view of retrievability
            metadata.source.retrievable = value
            metadata.identity.modified = datetime.now(timezone.utc)
            metadata.identity.last_modified_by = modified_by

            await self.metadata_store.save_metadata(metadata)
            logger.info(f"[METADATA] Set retrievable={value} for document '{document_uid}' by '{modified_by}'")

            # 2) If the document was vectorized, reflect the toggle in the vector index
            # to make the change effective immediately in search results, without deleting vectors.
            try:
                if ProcessingStage.VECTORIZED in metadata.processing.stages:
                    if self.vector_store is None:
                        self.vector_store = ApplicationContext.get_instance().get_vector_store()
                    try:
                        self.vector_store.set_document_retrievable(document_uid=document_uid, value=value)
                        logger.info(
                            "[VECTOR] Updated retrievable=%s in vector index for document '%s'.",
                            value,
                            document_uid,
                        )
                    except NotImplementedError:
                        logger.info(
                            "[VECTOR] Vector store does not support retrievable toggling; vectors unchanged for document '%s'.",
                            document_uid,
                        )
            except Exception as ve:
                logger.warning(f"[VECTOR] Could not reflect retrievable toggle in vector index for '{document_uid}': {ve}")
        except Exception as e:
            logger.error(f"Error updating retrievable flag for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    async def rename_document(self, user: KeycloakUser, document_uid: str, new_name: str, modified_by: str) -> DocumentMetadata:
        """Real rename: changes `identity.document_name` (the actual file name),
        not just the cosmetic `identity.title` `update_document_title` edits.
        `document_uid`, storage keys, and embeddings never change (DOCUMENT-RENAME-RFC.md
        §4) — only the display name, everywhere it's stored as metadata: Postgres and,
        best-effort, the vector index's copy of it on each chunk. Existing chat/session
        citations are historical snapshots and are intentionally left untouched.
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        new_name = new_name.strip()
        if not new_name:
            raise InvalidMetadataRequest("New name cannot be empty")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        if not metadata:
            raise MetadataNotFound(f"Document '{document_uid}' not found.")

        old_name = metadata.identity.document_name
        if new_name == old_name:
            return metadata

        # A rename may not change the extension — it reflects the ingested content
        # type; changing it here would mislead downstream readers without
        # re-processing the file (DOCUMENT-RENAME-RFC.md §4/§7 decision 2).
        old_ext = Path(old_name).suffix.lower()
        new_ext = Path(new_name).suffix.lower()
        if new_ext != old_ext:
            raise InvalidMetadataRequest(f"Renaming cannot change the file extension ('{old_ext}' -> '{new_ext}').")

        # Reject a name already used by a sibling in any of this document's own
        # folders/tags — a deliberate, user-driven rename should keep the user in
        # control of the final name rather than silently auto-suffixing
        # (DOCUMENT-RENAME-RFC.md §5/§7 decision 3). Fetched concurrently: each
        # tag's sibling list is independent of the others, no ordering dependency.
        siblings_by_tag = await asyncio.gather(*(self.get_document_metadata_in_tag(user, tag_id) for tag_id in metadata.tags.tag_ids))
        for siblings in siblings_by_tag:
            if any(d.identity.document_uid != document_uid and d.identity.document_name == new_name for d in siblings):
                raise DocumentNameCollisionError(f"A document named '{new_name}' already exists in this folder.")

        # `title` is a cosmetic override (`update_document_title`) that, per
        # documentDisplayName()'s "title || document_name" fallback in the
        # frontend, would otherwise keep masking the new name forever — a real
        # rename supersedes it.
        metadata.identity.document_name = new_name
        metadata.identity.title = None
        metadata.identity.modified = datetime.now(timezone.utc)
        metadata.identity.last_modified_by = modified_by

        await self.metadata_store.save_metadata(metadata)
        logger.info(f"[METADATA] Renamed document '{document_uid}' from '{old_name}' to '{new_name}' by '{modified_by}'")

        # Best-effort vector sync, same shape as update_document_retrievable above:
        # the Postgres write is authoritative and already succeeded; a vector store
        # that can't (or doesn't need to) reflect the change never fails the request.
        # Offloaded to a thread: every concrete store's set_document_name is a
        # synchronous, blocking client call (opensearchpy/chromadb/clickhouse_connect/
        # a sync SQLAlchemy engine) — the ClickHouse implementation in particular
        # issues one blocking round-trip per chunk, not one for the whole document,
        # so this can run for a while on documents with many chunks and must not
        # stall the event loop for unrelated concurrent requests to this backend.
        try:
            if ProcessingStage.VECTORIZED in metadata.processing.stages:
                if self.vector_store is None:
                    self.vector_store = ApplicationContext.get_instance().get_vector_store()
                try:
                    await asyncio.to_thread(self.vector_store.set_document_name, document_uid=document_uid, document_name=new_name)
                    logger.info("[VECTOR] Updated document_name in vector index for document '%s'.", document_uid)
                except NotImplementedError:
                    logger.info(
                        "[VECTOR] Vector store does not support renaming; vectors unchanged for document '%s'.",
                        document_uid,
                    )
        except Exception as ve:
            logger.warning(f"[VECTOR] Could not reflect rename in vector index for '{document_uid}': {ve}")

        return metadata

    async def update_document_title(self, user: KeycloakUser, document_uid: str, title: str, modified_by: str) -> None:
        """Rename a document in the browser (cosmetic only — does not touch ingestion,
        vectorization, or citation text, which keep using the original file name)."""
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        if not title or not title.strip():
            raise InvalidMetadataRequest("Title cannot be empty")

        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        try:
            metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
            if not metadata:
                raise MetadataNotFound(f"Document '{document_uid}' not found.")

            metadata.identity.title = title.strip()
            metadata.identity.modified = datetime.now(timezone.utc)
            metadata.identity.last_modified_by = modified_by

            await self.metadata_store.save_metadata(metadata)
            logger.info(f"[METADATA] Set title='{title}' for document '{document_uid}' by '{modified_by}'")
        except MetadataNotFound:
            raise
        except Exception as e:
            logger.error(f"Error updating title for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update title: {e}")

    # === Business labels (descriptive) =========================================
    # Labels carry NO scope/permission meaning, so there is no ReBAC check on the
    # label itself; only the DOCUMENT's update/read access is enforced (you may
    # label documents you can already edit, and resolve over documents you can
    # read). `document_labels` is the sole persisted source of truth (see
    # PostgresDocumentMetadataStore) — this is the ONLY method that mutates it;
    # every route (old path-segment and new PATCH body) calls through here.

    async def mutate_document_labels(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
        modified_by: str,
    ) -> list[str]:
        """Add and/or remove descriptive labels on one document in a single
        transaction. Returns the canonical stored set (never client-computed).

        A value present in both `add` and `remove` ends up absent: `remove`
        wins on conflict. Normalization (trim, drop empty, dedupe) is the same
        `normalize_labels` contract used everywhere else. An empty request
        (nothing to add or remove, after normalization) is a no-op that still
        returns the current stored set — idempotent, not an error.
        """
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        to_remove = set(normalize_labels(remove or []))
        to_add = set(normalize_labels(add or [])) - to_remove

        engine = ApplicationContext.get_instance().get_pg_async_engine()
        sessions = make_session_factory(engine)
        async with sessions() as s:
            async with s.begin():
                exists = await self.metadata_store.get_metadata_by_uid(document_uid, session=s)
                if exists is None:
                    raise MetadataNotFound(f"Document '{document_uid}' not found.")
                for label in to_add:
                    await self.metadata_store.add_label(document_uid, label, session=s)
                for label in to_remove:
                    await self.metadata_store.remove_label(document_uid, label, session=s)
                # A genuinely empty request (nothing to add/remove after
                # normalization) is a no-op that must not touch the audit
                # trail; a requested add/remove does, even when it turns out
                # to be idempotent (label already present/absent) — matching
                # the pre-relational-table behavior on `identity.modified`/
                # `last_modified_by`.
                if to_add or to_remove:
                    await self.metadata_store.touch_label_mutation_audit_fields(
                        document_uid,
                        modified=datetime.now(timezone.utc),
                        modified_by=modified_by,
                        session=s,
                    )
                labels = await self.metadata_store.get_labels_for_document(document_uid, session=s)

        if to_add or to_remove:
            logger.info(f"[METADATA] Labels add={sorted(to_add)} remove={sorted(to_remove)} on document '{document_uid}' by '{modified_by}'")
        return labels

    async def add_label_to_document(self, user: KeycloakUser, document_uid: str, label: str, modified_by: str) -> list[str]:
        """Legacy single-label adapter (`POST /documents/{uid}/labels/{label}`).
        Returns the stored set."""
        return await self.mutate_document_labels(user, document_uid, add=[label], modified_by=modified_by)

    async def remove_label_from_document(self, user: KeycloakUser, document_uid: str, label: str, modified_by: str) -> list[str]:
        """Legacy single-label adapter (`DELETE /documents/{uid}/labels/{label}`).
        Returns the stored set."""
        return await self.mutate_document_labels(user, document_uid, remove=[label], modified_by=modified_by)

    async def get_documents_with_label(self, user: KeycloakUser, label: str) -> list[DocumentMetadata]:
        """Resolve a label to the readable documents carrying it — an indexed
        lookup narrowed to the caller's authorized documents, not a full-corpus
        scan filtered in Python."""
        uids = await self.get_document_uids_with_any_label(user, [label])
        if not uids:
            return []
        return await self.metadata_store.get_metadata_by_uids(list(uids))

    async def get_documents_with_label_page(self, user: KeycloakUser, label: str, *, offset: int = 0, limit: int = 50) -> tuple[list[DocumentMetadata], int]:
        """Paginated resolution of one label to its readable documents — the
        flat, deterministic sibling of `get_documents_with_label`, for a
        caller that needs an exhaustive, page-by-page result rather than
        everything in one response (e.g. an agent tool answering "give me
        every document with label X"). Ordered by document_uid for a stable
        page boundary; hydrates ONLY the requested page's documents.

        Pushes `offset`/`limit` into the store query
        (`get_document_uids_with_any_label_page`) rather than fetching every
        matching uid and slicing in Python — enumerating many pages does not
        repeat a full, unbounded label scan on each call. The one thing that
        IS still per-call is the ReBAC `lookup_user_resources` resolution
        (same cost every other authorized/paginated listing in this service
        pays per call; there is no cross-call authorization cache here).
        """
        targets = set(normalize_labels([label]))
        if not targets:
            return [], 0

        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        if isinstance(authorized_doc_ref, RebacDisabledResult):
            page_uids, total = await self.metadata_store.get_document_uids_with_any_label_page(targets, offset=offset, limit=limit)
        else:
            authorized_ids = {d.id for d in authorized_doc_ref}
            if not authorized_ids:
                return [], 0
            page_uids, total = await self.metadata_store.get_document_uids_with_any_label_page(targets, document_uids=authorized_ids, offset=offset, limit=limit)
        docs = await self.metadata_store.get_metadata_by_uids(page_uids) if page_uids else []
        return docs, total

    async def get_document_uids_with_any_label(self, user: KeycloakUser, labels: list[str]) -> set[str]:
        """Resolve the union of readable document uids carrying ANY of
        `labels` (OR semantics) — ONE ReBAC resolution, ONE indexed
        `label IN (...)` query. UID-only: callers that need document
        metadata should hydrate afterward (e.g. via `get_documents_by_uids`),
        never call this label-by-label."""
        targets = set(normalize_labels(labels))
        if not targets:
            return set()

        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        if isinstance(authorized_doc_ref, RebacDisabledResult):
            uids = await self.metadata_store.get_document_uids_with_any_label(targets)
        else:
            authorized_ids = {d.id for d in authorized_doc_ref}
            if not authorized_ids:
                return set()
            uids = await self.metadata_store.get_document_uids_with_any_label(targets, document_uids=authorized_ids)
        return set(uids)

    async def list_document_labels(self, user: KeycloakUser) -> list[str]:
        """Return the distinct labels used across the user's readable documents
        (UI vocabulary) — an indexed distinct query narrowed to the caller's
        authorized documents, never revealing a label used only on documents
        the caller cannot read."""
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        if isinstance(authorized_doc_ref, RebacDisabledResult):
            return await self.metadata_store.get_distinct_labels()

        authorized_ids = {d.id for d in authorized_doc_ref}
        if not authorized_ids:
            return []
        return await self.metadata_store.get_distinct_labels(document_uids=authorized_ids)

    async def save_document_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        """
        Save document metadata, then finalize follow-up document maintenance.

        Why this exists:
        - Ingestion and document updates need one shared persistence path for
          metadata, ReBAC parent links, and tag timestamps.
        - Tabular re-ingestion must only prune superseded Parquet revisions
          after the new metadata payload has been saved successfully.

        How to use:
        - Call from services that create or update one document metadata record.
        - The method persists metadata first, then runs best-effort cleanup for
          stale tabular artifacts linked to the saved document.
        """
        # Check if user has permissions to add document in all specified tags
        if metadata.tags:
            for tag_id in metadata.tags.tag_ids:
                await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
        await self._persist_metadata_and_follow_up(user, metadata)

    async def save_document_metadata_trusted(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        """
        Same as `save_document_metadata`, but skips the per-tag `TagPermission.UPDATE`
        check.

        Why this exists:
        - the corpus-revectorize migration path
          (`features/scheduler/activities.py::output_process_trusted`) is
          authorized once, at the platform level, by
          `corpus_manager_controller._authorize_scope` (`CAN_MANAGE_PLATFORM`)
          before the whole workflow starts — re-checking `TagPermission.UPDATE`
          per document here would reject a root/platform admin who is not
          individually a member of every team the migration touches, the same
          class of gap `mark_document_vectorized`
          (`features/scheduler/activities.py`) already works around for the
          `VECTORIZED` stage.
        - every other follow-up (Parquet pruning, storage-quota adjustment,
          tag timestamps, ReBAC parent link) still runs unchanged — this must
          never become a silent metadata write that skips them, only the
          permission check.

        Never call this from a router or any other user-facing service —
        reachable only from the already-platform-authorized migration/
        corpus-revectorize activity path.
        """
        await self._persist_metadata_and_follow_up(user, metadata)

    async def update_document_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> bool:
        """Persist a document the caller already read, never creating one.

        Returns False when the document was deleted meanwhile — the write and
        every follow-up (quota, ReBAC, tag timestamps, KPI) are then skipped.

        Use this from anything that updates a document in flight, ingestion
        activities above all: their work runs in a thread Python cannot kill, so
        a cancelled activity keeps computing and would otherwise resurrect the
        document its cancellation just deleted (#2315, see
        `BaseDocumentMetadataStore.update_metadata`).
        """
        if metadata.tags:
            for tag_id in metadata.tags.tag_ids:
                await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
        return await self._persist_metadata_and_follow_up(user, metadata, update_only=True)

    async def update_document_metadata_trusted(self, user: KeycloakUser, metadata: DocumentMetadata) -> bool:
        """`update_document_metadata` without the per-tag permission check —
        same trust rationale as `save_document_metadata_trusted`."""
        return await self._persist_metadata_and_follow_up(user, metadata, update_only=True)

    async def _persist_metadata_and_follow_up(self, user: KeycloakUser, metadata: DocumentMetadata, *, update_only: bool = False) -> bool:
        """Persist metadata and run every follow-up that must accompany it.

        Returns True when the document was persisted. Only an `update_only`
        call can return False, meaning the document no longer exists: nothing
        was written and no follow-up ran, which is the point — crediting quota
        or re-linking ReBAC for a deleted document is exactly the damage the
        conditional UPDATE prevents.
        """
        try:
            prev_metadata = None
            try:
                prev_metadata = await self.metadata_store.get_metadata_by_uid(metadata.document_uid)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not load previous metadata for '%s' before save; storage deltas will be recomputed without it: %s",
                    metadata.document_uid,
                    exc,
                )

            # `metadata.labels` is never written into `doc` (see
            # PostgresDocumentMetadataStore._to_dict) and this generic save
            # never touches `document_labels` either — `mutate_document_labels`
            # is the ONLY label mutation path (see its docstring). A caller
            # holding a stale in-memory snapshot whose `.labels` no longer
            # matches the table (e.g. a long-running revectorize activity that
            # loaded a document before a label was removed from it) must not
            # be able to reintroduce, drop, or otherwise affect a label by
            # calling this method — that was the exact lost-update path this
            # single-mutator invariant closes.
            if update_only:
                if not await self.metadata_store.update_metadata(metadata):
                    logger.info(
                        "[METADATA] document_uid=%s no longer exists; update and follow-ups skipped",
                        metadata.document_uid,
                    )
                    return False
            else:
                await self.metadata_store.save_metadata(metadata)
            if prev_metadata is None:
                try:
                    from fred_core.kpi import KPIActor

                    tag_store = ApplicationContext.get_instance().get_tag_store()
                    first_tag_id = metadata.tags.tag_ids[0] if metadata.tags and metadata.tags.tag_ids else None
                    first_tag = await tag_store.get_tag_by_id(first_tag_id) if first_tag_id else None
                    team_id = first_tag.owner_id if first_tag else ""
                    kpi = ApplicationContext.get_instance().get_kpi_writer()
                    kpi.count(
                        "document.created_total",
                        1,
                        dims={
                            "source_type": metadata.source.source_type.value,
                            "file_type": metadata.file.file_type.value if metadata.file else "other",
                            "team_id": team_id,
                        },
                        actor=KPIActor(type="human", user_id=user.uid),
                    )
                except Exception as kpi_exc:  # noqa: BLE001
                    logger.warning("[METADATA][KPI] Failed to emit document.created_total: %s", kpi_exc)

            if metadata.tags and metadata.tags.tag_ids:
                for tag_id in metadata.tags.tag_ids:
                    await self._set_tag_as_parent_in_rebac(tag_id, metadata.document_uid, actor_uid=user.uid)

            old_size = prev_metadata.file.file_size_bytes or 0 if prev_metadata and prev_metadata.file else 0
            new_size = metadata.file.file_size_bytes or 0 if metadata.file else 0
            old_tags = set(prev_metadata.tags.tag_ids or []) if prev_metadata and prev_metadata.tags else set()
            new_tags = set(metadata.tags.tag_ids or []) if metadata.tags else set()

            await self._adjust_team_storage(
                old_size=old_size,
                new_size=new_size,
                old_tags=old_tags,
                new_tags=new_tags,
                user_id=user.uid,
            )

            # Update tag timestamps for any tags assigned to this document
            if metadata.tags:
                await self._update_tag_timestamps(user, metadata.tags.tag_ids)
            await self._prune_stale_tabular_artifacts(metadata)
            return True

        except Exception as e:
            logger.error(f"Error saving metadata for {metadata.document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to save metadata: {e}")

    async def _prune_stale_tabular_artifacts(self, metadata: DocumentMetadata) -> None:
        """
        Keep only the saved tabular artifact revision for one document.

        Why this exists:
        - Re-ingestion should not delete the previous dataset revision before
          the new metadata record has been persisted successfully.
        - Running the cleanup after `save_metadata(...)` preserves the previous
          readable dataset if metadata persistence fails mid-request.

        How to use:
        - Call only after the latest document metadata has been durably saved.
        - Cleanup is best-effort and logs warnings instead of failing the save.
        """

        artifact = read_tabular_artifact(metadata)
        multi_artifact = read_tabular_multi_artifact(metadata)
        if artifact is not None:
            current_keys = {artifact.object_key}
        elif multi_artifact is not None:
            current_keys = {table.object_key for table in multi_artifact.tables}
        else:
            return
        if not current_keys:
            return

        prefix = document_artifact_prefix(
            artifacts_prefix=self.config.storage.tabular_store.artifacts_prefix,
            document_uid=metadata.document_uid,
        )
        try:
            for stored_object in self.content_store.list_objects(prefix):
                if stored_object.key not in current_keys:
                    self.content_store.delete_object(stored_object.key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not prune stale tabular artifacts for '%s': %s",
                metadata.document_uid,
                exc,
            )

    async def _save_and_move_storage(
        self,
        metadata: DocumentMetadata,
        *,
        old_tags: set[str],
        new_tags: set[str],
        user: KeycloakUser,
    ) -> None:
        """
        Persist a document's new tag set and move its storage between owners,
        atomically.

        Why this exists:
        - the tags decide *who* is charged, so changing them without accounting
          left a document shared into a second library never charged to it, a
          document removed from a library charged to it forever, and — once the
          delete-time release existed — a delete crediting a team that never paid
        - saving and adjusting in two transactions was not enough: the tag change
          committed first, and `_adjust_team_storage` swallows its own errors, so a
          failed counter update left the tag moved and the charge behind with no
          signal. Both now commit together or not at all (#2149 review findings)

        How to use:
        - call with the tag sets from before and after the change; the size is
          unchanged, so only ownership moves
        - ReBAC parent writes stay OUTSIDE this transaction: OpenFGA is a separate
          system that cannot join it, and holding a DB transaction across a network
          call is what deadlocked the connection pool on the delete path
        """
        size = metadata.file.file_size_bytes or 0 if metadata.file else 0
        if not size or old_tags == new_tags:
            await self.metadata_store.save_metadata(metadata)
            return

        # Resolve before opening the transaction — resolution reads the tag store
        # and calls ReBAC, and holding a pooled connection while asking for another
        # exhausts the pool under a concurrent fan-out.
        team_deltas, user_deltas = await self._resolve_storage_deltas(
            old_size=size,
            new_size=size,
            old_tags=old_tags,
            new_tags=new_tags,
            user_id=user.uid,
        )

        engine = ApplicationContext.get_instance().get_pg_async_engine()
        sessions = make_session_factory(engine)
        async with sessions() as s:
            async with s.begin():
                await self.metadata_store.save_metadata(metadata, session=s)
                await self._apply_storage_deltas(team_deltas, user_deltas, session=s)

    async def _delete_and_release(
        self,
        metadata: DocumentMetadata,
        *,
        tag_ids: set[str],
        user_id: str,
    ) -> None:
        """
        Remove a document's metadata row and release its storage, atomically.

        Why this exists:
        - the two are one operation, not two. Splitting them let a concurrent
          deleter release bytes it did not remove, and let a counter failure
          strand bytes whose document was already gone — neither recoverable
          once the row is deleted (#2149 review findings)
        - the conditional DELETE is the exactly-once gate: only the caller whose
          statement matched a row releases, and its row lock is held until the
          counters commit alongside it

        How to use:
        - call with the tags the document had *before* any removal mutated them
        - deltas are resolved before the transaction opens, so no DB transaction
          is held across the ReBAC lookups ownership resolution performs
        """
        # Resolve BEFORE opening the transaction. Resolution reads the tag store
        # and calls ReBAC, so doing it inside would hold one pooled connection
        # while asking for another; a concurrent delete fan-out then exhausts the
        # pool, and because accounting errors used to be swallowed the metadata
        # delete still committed — releasing nothing and recreating the very
        # phantom-quota drift this fix exists to remove (#2149).
        team_deltas, user_deltas = await self._resolve_storage_deltas(
            old_size=metadata.file.file_size_bytes or 0 if metadata.file else 0,
            new_size=0,
            old_tags=tag_ids,
            new_tags=set(),
            user_id=user_id,
        )

        engine = ApplicationContext.get_instance().get_pg_async_engine()
        sessions = make_session_factory(engine)
        # Failures propagate: the transaction rolls back, so the row survives and
        # can be deleted again, rather than vanishing with its quota still charged.
        async with sessions() as s:
            async with s.begin():
                if await self.metadata_store.delete_metadata(metadata.document_uid, session=s):
                    await self._apply_storage_deltas(team_deltas, user_deltas, session=s)

    async def _adjust_team_storage(
        self,
        *,
        old_size: int,
        new_size: int,
        old_tags: set[str],
        new_tags: set[str],
        user_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Compare old and new document properties (tags and size) and apply deltas
        to the storage sizes of the associated teams or users (personal spaces).

        Resolution and application are separate: this method does both, for
        callers holding no transaction of their own. A caller that already has
        one MUST instead call `_resolve_storage_deltas` first and pass the result
        to `_apply_storage_deltas` inside its transaction — resolving while a
        transaction is open borrows a second pooled connection for the tag
        lookup, and a concurrent fan-out then exhausts the pool and deadlocks
        (`QueuePool limit of size 2 reached`, observed deleting a 10-document
        library against a live stack).
        """
        try:
            team_deltas, user_deltas = await self._resolve_storage_deltas(
                old_size=old_size,
                new_size=new_size,
                old_tags=old_tags,
                new_tags=new_tags,
                user_id=user_id,
            )
            await self._apply_storage_deltas(team_deltas, user_deltas, session=session)
        except Exception:
            logger.exception(
                "Failed to update team or user storage size (old_size=%d, new_size=%d, old_tags=%s, new_tags=%s)",
                old_size,
                new_size,
                sorted(old_tags),
                sorted(new_tags),
            )

    async def _resolve_storage_deltas(
        self,
        *,
        old_size: int,
        new_size: int,
        old_tags: set[str],
        new_tags: set[str],
        user_id: str | None = None,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """
        Work out which team and personal counters move, and by how much.

        Why this exists:
        - resolving ownership reads the tag store and calls ReBAC, each needing
          its own connection. Doing that while the caller's transaction is open
          holds one pooled connection while asking for another, so a concurrent
          delete fan-out exhausts the pool and every removal times out. Resolve
          first, then open the transaction.

        How to use:
        - call before starting a transaction, then hand both dicts to
          `_apply_storage_deltas` inside it

        Returns `(team_deltas, user_deltas)`, each mapping an owner id to a byte
        delta; both empty when nothing moves.
        """
        team_deltas: dict[str, int] = {}
        user_deltas: dict[str, int] = {}

        all_tags = old_tags | new_tags
        if not all_tags:
            # An untagged document is deliberately NOT accounted for here.
            # It has no ReBAC parent (permissions derive from a tag), so its
            # own uploader cannot read, tag or delete it — charging it would
            # consume quota that no route can ever release. Giving untagged
            # documents a real personal owner needs an authorization-model
            # change and is tracked separately (#2150 + RFC).
            return team_deltas, user_deltas

        tag_store = ApplicationContext.get_instance().get_tag_store()

        for tag_id in all_tags:
            tag = await tag_store.get_tag_by_id(tag_id)
            if not tag or not tag.owner_id:
                continue

            owner_id = tag.owner_id
            if owner_id == "personal" and user_id:
                owner_id = str(user_id)

            team_ids = []
            try:
                from fred_core import RebacDisabledResult, RebacReference, RelationType, Resource

                subjects = await self.rebac.lookup_subjects(RebacReference(type=Resource.TAGS, id=tag.id), RelationType.OWNER, Resource.TEAM)
                if not isinstance(subjects, RebacDisabledResult) and subjects:
                    for sub in subjects:
                        if sub.id != "personal" and not sub.id.startswith("personal-"):
                            team_ids.append(sub.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not resolve team owners via ReBAC for tag '%s'; falling back to team metadata lookup: %s",
                    tag.id,
                    exc,
                )

            if not team_ids and not owner_id.startswith("personal-"):
                try:
                    engine = ApplicationContext.get_instance().get_pg_async_engine()
                    store = TeamMetadataStore(engine)
                    meta = await store.get_by_team_id(TeamId(owner_id))
                    if meta is not None:
                        team_ids.append(owner_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Could not confirm team ownership for tag '%s' via team metadata lookup: %s",
                        tag.id,
                        exc,
                    )

            is_old = tag_id in old_tags
            is_new = tag_id in new_tags

            if is_new and not is_old:
                delta = new_size
            elif is_new and is_old:
                delta = new_size - old_size
            else:  # is_old and not is_new
                delta = -old_size

            if team_ids:
                for team_id in team_ids:
                    team_deltas[team_id] = team_deltas.get(team_id, 0) + delta
            else:
                resolved_user_id = owner_id
                if resolved_user_id.startswith("personal-"):
                    resolved_user_id = resolved_user_id[len("personal-") :]
                user_deltas[resolved_user_id] = user_deltas.get(resolved_user_id, 0) + delta

        return team_deltas, user_deltas

    async def _apply_storage_deltas(
        self,
        team_deltas: dict[str, int],
        user_deltas: dict[str, int],
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Apply already-resolved storage deltas to team and personal counters.

        Why this exists:
        - every counter a single document touches must move together or not at
          all. Applying them one transaction at a time meant a failure partway
          through left team A decremented and team B still charged, with the
          metadata row already gone and no way to reconstruct the remainder
          (#2149 review finding)
        - ownership resolution calls ReBAC over the network, so it stays in
          `_adjust_team_storage` and only these writes run inside the caller's
          transaction — a DB transaction is never held open across OpenFGA

        How to use:
        - pass the caller's `session` so the counters commit atomically with the
          metadata delete that triggered them; omit it for a standalone
          adjustment, which then gets its own transaction
        """
        if not team_deltas and not user_deltas:
            return

        engine = ApplicationContext.get_instance().get_pg_async_engine()
        team_store = TeamMetadataStore(engine)
        user_store = get_user_store()

        async def _apply(s: AsyncSession) -> None:
            for team_id, delta in team_deltas.items():
                if delta != 0:
                    await team_store.increment_current_storage_size(TeamId(team_id), delta, session=s)
            for user_id_str, delta in user_deltas.items():
                if delta == 0:
                    continue
                try:
                    user_uuid = UUID(user_id_str)
                except ValueError:
                    logger.warning("Invalid user_id format during storage adjustment: '%s'", user_id_str)
                    continue
                await user_store.increment_current_storage_size(user_uuid, delta, session=s)

        if session is not None:
            await _apply(session)
            return
        sessions = make_session_factory(engine)
        async with sessions() as s:
            async with s.begin():
                await _apply(s)

    async def _handle_tag_timestamp_updates(self, user: KeycloakUser, document_uid: str, new_tags: list[str]) -> None:
        """
        Update tag timestamps when document tags are modified.
        """
        try:
            # Get old tags from current document metadata
            old_document = await self.metadata_store.get_metadata_by_uid(document_uid)
            old_tags = (old_document.tags.tag_ids if old_document and old_document.tags else []) or []

            # Find tags that were added or removed
            old_tags_set = set(old_tags)
            new_tags_set = set(new_tags or [])

            affected_tags = old_tags_set.symmetric_difference(new_tags_set)

            # Update timestamps for affected tags
            if affected_tags:
                await self._update_tag_timestamps(user, list(affected_tags))

        except Exception as e:
            logger.warning(f"Failed to handle tag timestamp updates for {document_uid}: {e}")

    async def _update_tag_timestamps(self, user: KeycloakUser, tag_ids: list[str]) -> None:
        """
        Update timestamps for a list of tag IDs.
        """
        try:
            # Import here to avoid circular imports
            from knowledge_flow_backend.features.tag.tag_service import TagService

            tag_service = TagService()

            for tag_id in tag_ids:
                try:
                    await tag_service.update_tag_timestamp(tag_id, user)
                except Exception as tag_error:
                    logger.warning(f"Failed to update timestamp for tag {tag_id}: {tag_error}")

        except Exception as e:
            logger.warning(f"Failed to update tag timestamps: {e}")

    async def _set_tag_as_parent_in_rebac(self, tag_id: str, document_uid: str, *, actor_uid: str | None = None) -> None:
        """
        Add a relation in the ReBAC engine between a tag and a document.
        """
        await self.rebac.add_relation(self._get_tag_as_parent_relation(tag_id, document_uid), actor_uid=actor_uid)

    async def _remove_tag_as_parent_in_rebac(self, tag_id: str, document_uid: str) -> None:
        """
        Remove a relation in the ReBAC engine between a tag and a document.
        """
        await self.rebac.delete_relation(self._get_tag_as_parent_relation(tag_id, document_uid))

    async def _promote_alternate_version(self, canonical_name: str, source_tag: str | None, removed_tag_id: str, actor: str) -> DocumentMetadata | None:
        """
        Find a version=1 sibling with the same canonical_name and tag, promote it to version=0, and save.
        """
        filters: dict[str, Any] = {"canonical_name": canonical_name}
        if removed_tag_id:
            filters.setdefault("tags", {})["tag_ids"] = [removed_tag_id]
        if source_tag:
            filters.setdefault("source", {})["source_tag"] = source_tag

        siblings = await self.metadata_store.get_all_metadata(filters)
        candidate = next((d for d in siblings if getattr(d.identity, "version", 0) == 1), None)
        if not candidate:
            return None

        candidate.identity.version = 0
        candidate.identity.document_name = candidate.identity.canonical_name or candidate.identity.document_name
        candidate.identity.modified = datetime.now(timezone.utc)
        candidate.identity.last_modified_by = actor
        await self.metadata_store.save_metadata(candidate)
        return candidate

    def _get_tag_as_parent_relation(self, tag_id: str, document_uid: str) -> Relation:
        return Relation(subject=RebacReference(Resource.TAGS, tag_id), relation=RelationType.PARENT, resource=RebacReference(Resource.DOCUMENTS, document_uid))

    # ------------------------------------------------------------------
    # Store consistency audit (metadata/content/vector)
    # ------------------------------------------------------------------

    def _ensure_vector_store(self):
        if self.vector_store is None:
            try:
                self.vector_store = ApplicationContext.get_instance().get_vector_store()
            except Exception as e:
                logger.warning("[AUDIT] Could not initialize vector store: %s", e)
                return None
        return self.vector_store

    def _list_vector_document_uids(self) -> set[str]:
        store = self._ensure_vector_store()
        if store is None:
            return set()

        try:
            if hasattr(store, "list_document_uids"):
                return set(store.list_document_uids())  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("[AUDIT] Failed to list vector document_uids: %s", e)
        return set()

    def _list_content_document_uids(self) -> set[str]:
        if self.content_store is None:
            return set()

        try:
            if hasattr(self.content_store, "list_document_uids"):
                return set(self.content_store.list_document_uids())  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("[AUDIT] Failed to list content document_uids: %s", e)
        return set()

    def _get_vector_chunk_count(self, document_uid: str) -> int | None:
        store = self._ensure_vector_store()
        if store is None or not hasattr(store, "get_document_chunk_count"):
            return None

        try:
            return int(store.get_document_chunk_count(document_uid=document_uid))  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("[AUDIT] Failed to count vectors for %s: %s", document_uid, e)
            return None

    async def audit_stores(self, user: KeycloakUser) -> StoreAuditReport:
        """
        Scan metadata, content, and vector stores to surface orphan or partial data.
        """
        await self.rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
        try:
            docs = await self.metadata_store.get_all_metadata({})
        except MetadataDeserializationError as e:
            logger.error(f"[AUDIT] Deserialization error while building audit report: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")
        except Exception as e:
            logger.error(f"[AUDIT] Failed to retrieve metadata for audit: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

        metadata_map = {md.document_uid: md for md in docs}
        metadata_ids = set(metadata_map.keys())
        vector_ids = self._list_vector_document_uids()
        content_ids = self._list_content_document_uids()
        all_ids = sorted(metadata_ids | vector_ids | content_ids)

        anomalies: list[StoreAuditFinding] = []
        for doc_uid in all_ids:
            md = metadata_map.get(doc_uid)
            in_metadata = md is not None
            in_vector = doc_uid in vector_ids
            in_content = doc_uid in content_ids
            issues: list[str] = []

            if not in_metadata:
                if in_vector:
                    issues.append("orphan_vectors")
                if in_content:
                    issues.append("orphan_content")
            else:
                raw_ready = md.processing.stages.get(ProcessingStage.RAW_AVAILABLE) == ProcessingStatus.DONE
                if raw_ready and not in_content:
                    issues.append("missing_content")

                vec_done = md.processing.stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE
                if vec_done and not in_vector:
                    issues.append("missing_vectors")

            vector_chunks = self._get_vector_chunk_count(doc_uid) if in_vector else None

            if issues:
                anomalies.append(
                    StoreAuditFinding(
                        document_uid=doc_uid,
                        document_name=md.document_name if md else None,
                        source_tag=md.source_tag if md else None,
                        present_in_metadata=in_metadata,
                        present_in_vector_store=in_vector,
                        present_in_content_store=in_content,
                        vector_chunks=vector_chunks,
                        issues=issues,
                    )
                )

        return StoreAuditReport(
            has_anomalies=bool(anomalies),
            total_seen=len(all_ids),
            metadata_count=len(metadata_ids),
            vector_count=len(vector_ids),
            content_count=len(content_ids),
            anomalies=anomalies,
        )

    async def fix_store_anomalies(self, user: KeycloakUser) -> StoreAuditFixResponse:
        """
        Run the audit and repair what it found. Never deletes anything.

        - `orphan_vectors`/`orphan_content`: data with no metadata row to
          attach to. Left alone — a platform admin decides by hand whether to
          delete or investigate first (was the metadata row lost by mistake?
          is the write half-finished?). This service reports them; it does
          not act on them.
        - `missing_vectors`/`missing_content`: a metadata row whose own
          processing stage lies (claims DONE when the store disagrees).
          Repair means resetting the stage(s) back to NOT_STARTED so the
          platform stops lying and the document becomes honestly
          re-processable (re-vectorize for missing_vectors, MIGR-07;
          re-ingest for missing_content) — the metadata row itself is never
          touched beyond its stage flags.
        """
        await self.rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
        before = await self.audit_stores(user)
        reset_metadata: list[str] = []

        for finding in before.anomalies:
            issues = set(finding.issues)
            doc_uid = finding.document_uid
            needs_stage_reset = finding.present_in_metadata and ("missing_content" in issues or "missing_vectors" in issues)

            if needs_stage_reset:
                try:
                    md = await self.metadata_store.get_metadata_by_uid(doc_uid)
                    if md is not None:
                        if "missing_content" in issues:
                            # Content is gone (or not yet mirrored): every downstream
                            # stage's DONE claim is equally unearned.
                            for stage in (
                                ProcessingStage.RAW_AVAILABLE,
                                ProcessingStage.PREVIEW_READY,
                                ProcessingStage.VECTORIZED,
                                ProcessingStage.SQL_INDEXED,
                            ):
                                if md.processing.stages.get(stage) == ProcessingStatus.DONE:
                                    md.set_stage_status(stage, ProcessingStatus.NOT_STARTED)
                        if "missing_vectors" in issues:
                            md.set_stage_status(ProcessingStage.VECTORIZED, ProcessingStatus.NOT_STARTED)
                        await self.metadata_store.save_metadata(md)
                        reset_metadata.append(doc_uid)
                except Exception as e:
                    logger.warning("[AUDIT] Failed to reset processing stage for %s: %s", doc_uid, e)

        after = await self.audit_stores(user)
        return StoreAuditFixResponse(
            before=before,
            after=after,
            reset_metadata=reset_metadata,
        )
