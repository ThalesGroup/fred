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
import logging
from datetime import datetime, timezone
from typing import Any

from fred_core import Action, DocumentPermission, KeycloakUser, RebacDisabledResult, RebacReference, Relation, RelationType, Resource, TagPermission, authorize
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    ProcessingGraph,
    ProcessingGraphEdge,
    ProcessingGraphNode,
    ProcessingStage,
    ProcessingStatus,
    ProcessingSummary,
)
from knowledge_flow_backend.common.structures import (
    OpenSearchVectorIndexConfig,
    PgVectorStorageConfig,
)
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import MetadataDeserializationError

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
        self.csv_input_store = None
        self.vector_store = None
        self.content_store = context.get_content_store()
        self.rebac = context.get_rebac_engine()

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.DELETE, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
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

        def ensure_tabular_store():
            if self.csv_input_store is None:
                try:
                    self.csv_input_store = ApplicationContext.get_instance().get_csv_input_store()
                except Exception as e:
                    logger.warning(f"[GRAPH] Could not initialize tabular store for graph: {e}")
            return self.csv_input_store

        nodes: list[ProcessingGraphNode] = []
        edges: list[ProcessingGraphEdge] = []

        # Pre-cache existing tables to avoid repeated roundtrips
        csv_store = ensure_tabular_store()
        existing_tables: set[str] = set()
        if csv_store is not None:
            try:
                existing_tables = set(csv_store.list_tables())
            except Exception as e:
                logger.warning(f"[GRAPH] Failed to list tables from tabular store: {e}")

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
            if stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE and csv_store is not None:
                table_name = sanitize_sql_name(metadata.document_name.rsplit(".", 1)[0])
                row_count: int | None = None

                if table_name in existing_tables:
                    try:
                        # Use a lightweight COUNT(*) query to avoid loading full tables.
                        # table_name is sanitized via sanitize_sql_name, so this is safe from SQL injection.
                        df = csv_store.execute_sql_query(f'SELECT COUNT(*) AS n FROM "{table_name}"')  # nosec B608
                        if not df.empty and "n" in df.columns:
                            row_count = int(df["n"].iloc[0])
                    except Exception as e:
                        logger.warning(f"[GRAPH] Failed to count rows for table '{table_name}': {e}")

                table_node_id = f"table:{table_name}"
                nodes.append(
                    ProcessingGraphNode(
                        id=table_node_id,
                        kind="table",
                        label=table_name,
                        document_uid=doc_uid,
                        table_name=table_name,
                        row_count=row_count,
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

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_processing_summary(self, user: KeycloakUser) -> ProcessingSummary:
        """
        Compute a consolidated processing summary across all documents visible to the user.
        """
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        try:
            docs = await self.metadata_store.get_all_metadata({})
        except MetadataDeserializationError as e:
            logger.error(f"[Metadata] Deserialization error while building processing summary: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")
        except Exception as e:
            logger.error(f"Error retrieving metadata for processing summary: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

        if isinstance(authorized_doc_ref, RebacDisabledResult):
            visible_docs = docs
        else:
            authorized_doc_ids = {d.id for d in authorized_doc_ref}
            visible_docs = [d for d in docs if d.identity.document_uid in authorized_doc_ids]

        total_documents = len(visible_docs)
        fully_processed = 0
        in_progress = 0
        failed = 0
        not_started = 0

        for metadata in visible_docs:
            stages = metadata.processing.stages or {}
            if not stages:
                not_started += 1
                continue

            has_failed = any(status == ProcessingStatus.FAILED for status in stages.values())
            any_in_progress = any(status == ProcessingStatus.IN_PROGRESS for status in stages.values())

            # Mirror the scheduler logic: a document is considered fully processed
            # when either the VECTOR or SQL_INDEXED stages are DONE.
            preview_done = stages.get(ProcessingStage.PREVIEW_READY) == ProcessingStatus.DONE
            vectorized_done = stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE
            sql_indexed_done = stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE
            fully_processed_doc = vectorized_done or sql_indexed_done

            # Has *any* work started (at least one stage DONE) without being fully processed?
            any_done = any(status == ProcessingStatus.DONE for status in stages.values())

            if has_failed:
                failed += 1
            elif fully_processed_doc:
                fully_processed += 1
            elif any_in_progress:
                in_progress += 1
            elif any_done or preview_done:
                # Some work has been completed (e.g. preview) but the document
                # is not yet fully processed or failed.
                in_progress += 1
            else:
                not_started += 1

        return ProcessingSummary(
            total_documents=total_documents,
            fully_processed=fully_processed,
            in_progress=in_progress,
            failed=failed,
            not_started=not_started,
        )

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
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

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
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
                    if self.csv_input_store is None:
                        self.csv_input_store = ApplicationContext.get_instance().get_csv_input_store()
                    table_name = sanitize_sql_name(metadata.document_name.rsplit(".", 1)[0])
                    try:
                        self.csv_input_store.delete_table(table_name)
                        logger.info(f"[TABULAR] Deleted SQL table '{table_name}' linked to '{metadata.document_name}'")
                    except Exception as e:
                        logger.warning(f"Could not delete SQL table '{table_name}': {e}")

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

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
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

    @authorize(Action.CREATE, Resource.DOCUMENTS)
    async def save_document_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        """
        Save document metadata and update tag timestamps for any assigned tags.
        This is an internal method only called by other services
        """
        # Check if user has permissions to add document in all specified tags
        if metadata.tags:
            for tag_id in metadata.tags.tag_ids:
                await self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        try:
            # Save the metadata first
            await self.metadata_store.save_metadata(metadata)
            for tag_id in metadata.tags.tag_ids:
                await self._set_tag_as_parent_in_rebac(tag_id, metadata.document_uid)

            # Update tag timestamps for any tags assigned to this document
            if metadata.tags:
                await self._update_tag_timestamps(user, metadata.tags.tag_ids)

        except Exception as e:
            logger.error(f"Error saving metadata for {metadata.document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to save metadata: {e}")

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

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def audit_stores(self, user: KeycloakUser) -> StoreAuditReport:
        """
        Scan metadata, content, and vector stores to surface orphan or partial data.
        """
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

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def fix_store_anomalies(self, user: KeycloakUser) -> StoreAuditFixResponse:
        """
        Run the audit and delete orphan/partial data from all stores.
        """
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
