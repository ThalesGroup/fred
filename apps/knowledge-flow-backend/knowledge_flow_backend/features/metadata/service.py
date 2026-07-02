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
from typing import Any, Callable

from fred_core import ORGANIZATION_ID, DocumentPermission, KeycloakUser, OrganizationPermission, RebacDisabledResult, RebacReference, Relation, RelationType, Resource, TagPermission, TeamMetadataStore
from fred_core.common.team_id import TeamId
from fred_core.documents.document_store import DocumentMetadataDeserializationError as MetadataDeserializationError
from fred_core.documents.document_structures import (
    DocumentMetadata,
    ProcessingGraph,
    ProcessingGraphEdge,
    ProcessingGraphNode,
    ProcessingStage,
    ProcessingStatus,
)
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import (
    ClickHouseVectorStorageConfig,
    OpenSearchVectorIndexConfig,
    PgVectorStorageConfig,
)
from knowledge_flow_backend.features.metadata.metadata_utils import normalize_labels, with_label_added, with_label_removed
from knowledge_flow_backend.features.tabular.artifacts import (
    TABULAR_EXTENSION_KEY,
    document_artifact_prefix,
    read_tabular_artifact,
)

logger = logging.getLogger(__name__)

# --- Domain Exceptions ---


class MetadataNotFound(Exception):
    pass


class MetadataUpdateError(Exception):
    pass


class InvalidMetadataRequest(Exception):
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
    deleted_metadata: list[str] = Field(default_factory=list)
    deleted_vectors: list[str] = Field(default_factory=list)
    deleted_content: list[str] = Field(default_factory=list)


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

    async def get_processing_graph(self, user: KeycloakUser) -> ProcessingGraph:
        """
        Build a lightweight processing graph for all documents visible to the user.

        The graph connects:
        - document nodes to vector_index nodes when the document has been vectorized
        - document nodes to table nodes when the document has been SQL indexed
        """
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        try:
            docs = await self.metadata_store.get_all_metadata({})
        except MetadataDeserializationError as e:
            logger.error(f"[Metadata] Deserialization error while building processing graph: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")
        except Exception as e:
            logger.error(f"Error retrieving metadata for processing graph: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

        if isinstance(authorized_doc_ref, RebacDisabledResult):
            visible_docs = docs
        else:
            authorized_doc_ids = {d.id for d in authorized_doc_ref}
            visible_docs = [d for d in docs if d.identity.document_uid in authorized_doc_ids]

        # Lazy-load optional stores only if needed
        def ensure_vector_store():
            if self.vector_store is None:
                try:
                    self.vector_store = ApplicationContext.get_instance().get_vector_store()
                except Exception as e:
                    logger.warning(f"[GRAPH] Could not initialize vector store for graph: {e}")
            return self.vector_store

        nodes: list[ProcessingGraphNode] = []
        edges: list[ProcessingGraphEdge] = []

        # Vector backend info (for UI diagnostics)
        vector_backend: str | None = None
        vector_detail: str | None = None
        embedding_model_name: str | None = getattr(self.config.embedding_model, "name", None)
        try:
            vs_cfg = self.config.storage.vector_store
            if isinstance(vs_cfg, OpenSearchVectorIndexConfig):
                vector_backend = "opensearch"
                vector_detail = f"index={vs_cfg.index}"
            elif isinstance(vs_cfg, PgVectorStorageConfig):
                vector_backend = "pgvector"
                vector_detail = f"collection={vs_cfg.collection_name}"
            elif isinstance(vs_cfg, ClickHouseVectorStorageConfig):
                vector_backend = "clickhouse"
                vector_detail = f"table={vs_cfg.table}"
            else:
                vector_backend = type(vs_cfg).__name__
                vector_detail = None
        except Exception as e:
            logger.debug("[GRAPH] Unable to resolve vector backend info: %s", e)

        for metadata in visible_docs:
            doc_uid = metadata.document_uid
            doc_node_id = f"doc:{doc_uid}"

            nodes.append(
                ProcessingGraphNode(
                    id=doc_node_id,
                    kind="document",
                    label=metadata.document_name,
                    document_uid=doc_uid,
                    file_type=metadata.file.file_type,
                    source_tag=metadata.source.source_tag,
                    version=getattr(metadata.identity, "version", 0),
                )
            )

            stages = metadata.processing.stages or {}

            # --- Vector index node (per-document) ---------------------------------
            if stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE:
                vector_store = ensure_vector_store()
                vector_count: int | None = None
                if vector_store is not None and hasattr(vector_store, "get_document_chunk_count"):
                    try:
                        vector_count = int(vector_store.get_document_chunk_count(document_uid=doc_uid))  # type: ignore[attr-defined]
                    except Exception as e:
                        logger.warning(f"[GRAPH] Failed to count vectors for document '{doc_uid}': {e}")

                vec_node_id = f"vec:{doc_uid}"
                nodes.append(
                    ProcessingGraphNode(
                        id=vec_node_id,
                        kind="vector_index",
                        label=f"Vectors for {metadata.document_name}",
                        document_uid=doc_uid,
                        vector_count=vector_count,
                        backend=vector_backend,
                        backend_detail=vector_detail,
                        embedding_model=embedding_model_name,
                    )
                )
                edges.append(
                    ProcessingGraphEdge(
                        source=doc_node_id,
                        target=vec_node_id,
                        kind="vectorized",
                    )
                )

            # --- SQL table node (per-document) ------------------------------------
            artifact = read_tabular_artifact(metadata)
            if stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE and artifact is not None:
                table_name = artifact.dataset_uid
                table_node_id = f"table:{table_name}"
                nodes.append(
                    ProcessingGraphNode(
                        id=table_node_id,
                        kind="table",
                        label=table_name,
                        document_uid=doc_uid,
                        table_name=table_name,
                        row_count=artifact.row_count,
                    )
                )
                edges.append(
                    ProcessingGraphEdge(
                        source=doc_node_id,
                        target=table_node_id,
                        kind="sql_indexed",
                    )
                )

        return ProcessingGraph(nodes=nodes, edges=edges)

    async def add_tag_id_to_document(self, user: KeycloakUser, metadata: DocumentMetadata, new_tag_id: str, consistency_token: str | None = None) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, new_tag_id, consistency_token=consistency_token)

        try:
            if metadata.tags is None:
                raise MetadataUpdateError("DocumentMetadata.tags is not initialized")

            # Avoid duplicate tags
            tag_ids = metadata.tags.tag_ids or []
            if new_tag_id not in tag_ids:
                tag_ids.append(new_tag_id)
                metadata.tags.tag_ids = tag_ids
                metadata.identity.modified = datetime.now(timezone.utc)
                metadata.identity.last_modified_by = user.uid
                await self.metadata_store.save_metadata(metadata)
                await self._set_tag_as_parent_in_rebac(new_tag_id, metadata.document_uid)

                logger.info(f"[METADATA] Added tag '{new_tag_id}' to document '{metadata.document_name}' by '{user.uid}'")
            else:
                logger.info(f"[METADATA] Tag '{new_tag_id}' already present on document '{metadata.document_name}' — no change.")

        except Exception as e:
            logger.error(f"Error updating retrievable flag for {metadata.document_name}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    async def remove_tag_id_from_document(self, user: KeycloakUser, metadata: DocumentMetadata, tag_id_to_remove: str) -> None:
        await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id_to_remove)

        try:
            if not metadata.tags or not metadata.tags.tag_ids or tag_id_to_remove not in metadata.tags.tag_ids:
                logger.info(f"[METADATA] Tag '{tag_id_to_remove}' not found on document '{metadata.document_name}' — nothing to remove.")
                return

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
                    await self._delete_tabular_artifacts(metadata)

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

                await self.metadata_store.delete_metadata(metadata.document_uid)
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
                await self.metadata_store.save_metadata(metadata)
                logger.info(f"[METADATA] Removed tag '{tag_id_to_remove}' from document '{metadata.document_name}' by '{user.uid}'")

            await self._remove_tag_as_parent_in_rebac(tag_id_to_remove, metadata.document_uid)

        except Exception as e:
            logger.error(f"Failed to remove tag '{tag_id_to_remove}' from document '{metadata.document_name}': {e}")
            raise MetadataUpdateError(f"Failed to remove tag: {e}")

    async def _delete_tabular_artifacts(self, metadata: DocumentMetadata) -> None:
        """
        Delete dataset-centric tabular artifacts linked to one document.

        Why this exists:
        - Removing the last visible tag from a document must also remove its
          queryable Parquet revisions from the shared content store.

        How to use:
        - Call during destructive metadata cleanup paths only.
        """

        artifact = read_tabular_artifact(metadata)
        if artifact is None:
            logger.info("[TABULAR] No %s payload found for '%s'", TABULAR_EXTENSION_KEY, metadata.document_name)
            return

        prefix = document_artifact_prefix(
            artifacts_prefix=self.config.storage.tabular_store.artifacts_prefix,
            document_uid=metadata.document_uid,
        )

        try:
            for stored_object in self.content_store.list_objects(prefix):
                self.content_store.delete_object(stored_object.key)
            logger.info("[TABULAR] Deleted tabular artifacts linked to '%s'", metadata.document_name)
        except Exception as e:
            logger.warning("Could not delete tabular artifacts for '%s': %s", metadata.document_name, e)

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

        try:
            metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
            if metadata is None:
                raise MetadataNotFound(f"No document found with UID {document_uid}")

            if ProcessingStage.VECTORIZED in metadata.processing.stages:
                if self.vector_store is None:
                    self.vector_store = ApplicationContext.get_instance().get_vector_store()
                try:
                    self.vector_store.delete_vectors_for_document(document_uid=metadata.document_uid)
                    logger.info(
                        "[METADATA] Deleted vectors for document '%s'",
                        metadata.document_name,
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not delete vectors for '%s': %s",
                        metadata.document_name,
                        exc,
                    )

            if ProcessingStage.SQL_INDEXED in metadata.processing.stages:
                await self._delete_tabular_artifacts(metadata)

            if self.content_store is not None:
                try:
                    self.content_store.delete_content(metadata.document_uid)
                    logger.info(
                        "[CONTENT] Deleted content for document '%s'",
                        metadata.document_name,
                    )
                except Exception as exc:
                    logger.warning(
                        "[CONTENT] Could not delete content for '%s': %s",
                        metadata.document_name,
                        exc,
                    )

            await self.metadata_store.delete_metadata(metadata.document_uid)

            if metadata.tags and metadata.tags.tag_ids:
                for tag_id in metadata.tags.tag_ids:
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

    # === Business labels (descriptive — DOCUMENT-TAGS-RFC) ====================
    # Labels carry NO scope/permission meaning, so there is no ReBAC check on the
    # label itself; only the DOCUMENT's update/read access is enforced (you may
    # label documents you can already edit, and resolve over documents you can read).

    async def _mutate_document_labels(self, user: KeycloakUser, document_uid: str, transform: Callable[[list[str]], list[str]], modified_by: str) -> list[str]:
        """Fetch a document, apply ``transform`` to its labels, persist, and return them."""
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        if not metadata:
            raise MetadataNotFound(f"Document '{document_uid}' not found.")

        metadata.labels = transform(metadata.labels)
        metadata.identity.modified = datetime.now(timezone.utc)
        metadata.identity.last_modified_by = modified_by
        await self.metadata_store.save_metadata(metadata)
        logger.info(f"[METADATA] Labels {metadata.labels} on document '{document_uid}' by '{modified_by}'")
        return metadata.labels

    async def add_label_to_document(self, user: KeycloakUser, document_uid: str, label: str, modified_by: str) -> list[str]:
        """Add a descriptive label to a document (idempotent). Returns the stored set."""
        return await self._mutate_document_labels(user, document_uid, lambda labels: with_label_added(labels, label), modified_by)

    async def remove_label_from_document(self, user: KeycloakUser, document_uid: str, label: str, modified_by: str) -> list[str]:
        """Remove a descriptive label from a document. Returns the stored set."""
        return await self._mutate_document_labels(user, document_uid, lambda labels: with_label_removed(labels, label), modified_by)

    async def get_documents_with_label(self, user: KeycloakUser, label: str) -> list[DocumentMetadata]:
        """Resolve a label to the readable documents carrying it (search resolve-then-target)."""
        target = (label or "").strip()
        if not target:
            return []
        docs = await self.get_documents_metadata(user, {})
        return [doc for doc in docs if target in (doc.labels or [])]

    async def list_document_labels(self, user: KeycloakUser) -> list[str]:
        """Return the distinct labels used across the user's readable documents (UI vocabulary)."""
        docs = await self.get_documents_metadata(user, {})
        return normalize_labels([label for doc in docs for label in (doc.labels or [])])

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

            # Save the metadata first
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
                    await self._set_tag_as_parent_in_rebac(tag_id, metadata.document_uid)

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
        if artifact is None:
            return

        prefix = document_artifact_prefix(
            artifacts_prefix=self.config.storage.tabular_store.artifacts_prefix,
            document_uid=metadata.document_uid,
        )
        try:
            for stored_object in self.content_store.list_objects(prefix):
                if stored_object.key != artifact.object_key:
                    self.content_store.delete_object(stored_object.key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not prune stale tabular artifacts for '%s': %s",
                metadata.document_uid,
                exc,
            )

    async def _adjust_team_storage(
        self,
        *,
        old_size: int,
        new_size: int,
        old_tags: set[str],
        new_tags: set[str],
        user_id: str | None = None,
    ) -> None:
        """
        Compare old and new document properties (tags and size) and apply deltas
        to the storage sizes of the associated teams or users (personal spaces).
        """
        try:
            all_tags = old_tags | new_tags
            if not all_tags:
                return

            tag_store = ApplicationContext.get_instance().get_tag_store()
            team_deltas = {}
            user_deltas = {}

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

            if team_deltas:
                engine = ApplicationContext.get_instance().get_pg_async_engine()
                store = TeamMetadataStore(engine)
                for team_id, delta in team_deltas.items():
                    if delta != 0:
                        await store.increment_current_storage_size(TeamId(team_id), delta)

            if user_deltas:
                from uuid import UUID

                from fred_core import get_user_store

                try:
                    user_store = get_user_store()
                    for user_id_str, delta in user_deltas.items():
                        if delta != 0:
                            try:
                                user_uuid = UUID(user_id_str)
                                await user_store.increment_current_storage_size(user_uuid, delta)
                            except ValueError:
                                logger.warning(f"Invalid user_id format during storage adjustment: '{user_id_str}'")
                except Exception as ue:
                    logger.warning(f"Failed to increment user personal space storage: {ue}")
        except Exception:
            logger.exception("Failed to update team or user storage size")

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

    async def _set_tag_as_parent_in_rebac(self, tag_id: str, document_uid: str) -> None:
        """
        Add a relation in the ReBAC engine between a tag and a document.
        """
        await self.rebac.add_relation(self._get_tag_as_parent_relation(tag_id, document_uid))

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
        Run the audit and delete orphan/partial data from all stores.
        """
        await self.rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
        before = await self.audit_stores(user)
        deleted_metadata: list[str] = []
        deleted_vectors: list[str] = []
        deleted_content: list[str] = []

        vector_store = self._ensure_vector_store()
        content_store = self.content_store

        for finding in before.anomalies:
            issues = set(finding.issues)
            doc_uid = finding.document_uid

            remove_vectors = "orphan_vectors" in issues or "missing_content" in issues or "missing_vectors" in issues
            remove_content = "orphan_content" in issues or "missing_content" in issues or "missing_vectors" in issues
            remove_metadata = finding.present_in_metadata and ("missing_content" in issues or "missing_vectors" in issues)

            if remove_vectors and vector_store is not None and finding.present_in_vector_store:
                try:
                    vector_store.delete_vectors_for_document(document_uid=doc_uid)
                    deleted_vectors.append(doc_uid)
                except Exception as e:
                    logger.warning("[AUDIT] Failed to delete vectors for %s: %s", doc_uid, e)

            if remove_content and content_store is not None and finding.present_in_content_store:
                try:
                    content_store.delete_content(doc_uid)
                    deleted_content.append(doc_uid)
                except Exception as e:
                    logger.warning("[AUDIT] Failed to delete content for %s: %s", doc_uid, e)

            if remove_metadata:
                try:
                    await self.metadata_store.delete_metadata(doc_uid)
                    deleted_metadata.append(doc_uid)
                except Exception as e:
                    logger.warning("[AUDIT] Failed to delete metadata for %s: %s", doc_uid, e)

        after = await self.audit_stores(user)
        return StoreAuditFixResponse(
            before=before,
            after=after,
            deleted_metadata=deleted_metadata,
            deleted_vectors=deleted_vectors,
            deleted_content=deleted_content,
        )
