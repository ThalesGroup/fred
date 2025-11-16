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

from fred_core import Action, DocumentPermission, KeycloakUser, RebacDisabledResult, RebacReference, Relation, RelationType, Resource, TagPermission, authorize

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


class MetadataService:
    """
    Service for managing metadata operations.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.config = context.get_config()
        self.metadata_store = context.get_metadata_store()
        self.catalog_store = context.get_catalog_store()
        self.csv_input_store = None
        self.vector_store = None
        self.rebac = context.get_rebac_engine()

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_documents_metadata(self, user: KeycloakUser, filters_dict: dict) -> list[DocumentMetadata]:
        authorized_doc_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)

        try:
            docs = self.metadata_store.get_all_metadata(filters_dict)

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
            docs = self.metadata_store.get_metadata_in_tag(tag_id)

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
            metadata = self.metadata_store.get_metadata_by_uid(document_uid)
        except Exception as e:
            logger.error(f"Error retrieving metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to get metadata: {e}")

        if metadata is None:
            raise MetadataNotFound(f"No document found with UID {document_uid}")

        return metadata

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
            docs = self.metadata_store.get_all_metadata({})
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
                        # Use a lightweight COUNT(*) query to avoid loading full tables
                        df = csv_store.execute_sql_query(f'SELECT COUNT(*) AS n FROM "{table_name}"')
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
            docs = self.metadata_store.get_all_metadata({})
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
                self.metadata_store.save_metadata(metadata)
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

                self.metadata_store.delete_metadata(metadata.document_uid)
                # TODO: remove all rebac relations for this document

            else:
                metadata.identity.modified = datetime.now(timezone.utc)
                metadata.identity.last_modified_by = user.uid
                self.metadata_store.save_metadata(metadata)
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
            metadata = self.metadata_store.get_metadata_by_uid(document_uid)
            if not metadata:
                raise MetadataNotFound(f"Document '{document_uid}' not found.")

            # 1) Update metadata-store view of retrievability
            metadata.source.retrievable = value
            metadata.identity.modified = datetime.now(timezone.utc)
            metadata.identity.last_modified_by = modified_by

            self.metadata_store.save_metadata(metadata)
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
            self.metadata_store.save_metadata(metadata)
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
            old_document = self.metadata_store.get_metadata_by_uid(document_uid)
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
            from knowledge_flow_backend.features.tag.service import TagService

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

    def _get_tag_as_parent_relation(self, tag_id: str, document_uid: str) -> Relation:
        return Relation(subject=RebacReference(Resource.TAGS, tag_id), relation=RelationType.PARENT, resource=RebacReference(Resource.DOCUMENTS, document_uid))
