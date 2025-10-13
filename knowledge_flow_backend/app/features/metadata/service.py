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

from fred_core import Action, DocumentPermission, KeycloakUser, RebacReference, Relation, RelationType, Resource, TagPermission, authorize

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.common.utils import sanitize_sql_name
from app.core.stores.metadata.base_metadata_store import MetadataDeserializationError

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
    def get_documents_metadata(self, user: KeycloakUser, filters_dict: dict) -> list[DocumentMetadata]:
        authorized_doc_ids = [d.id for d in self.rebac.lookup_user_resources(user, DocumentPermission.READ)]

        try:
            docs = self.metadata_store.get_all_metadata(filters_dict)
            # Filter by permission (todo: use rebac ids to filter at store (DB) level)
            return [d for d in docs if d.identity.document_uid in authorized_doc_ids]
        except MetadataDeserializationError as e:
            logger.error(f"[Metadata] Deserialization error: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")

        except Exception as e:
            logger.error(f"Error retrieving document metadata: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

    @authorize(Action.READ, Resource.DOCUMENTS)
    def get_document_metadata_in_tag(self, user: KeycloakUser, tag_id: str) -> list[DocumentMetadata]:
        """
        Return all metadata entries associated with a specific tag.
        """
        authorized_doc_ids = [d.id for d in self.rebac.lookup_user_resources(user, DocumentPermission.READ)]

        try:
            docs = self.metadata_store.get_metadata_in_tag(tag_id)
            # Filter by permission (todo: use rebac ids to filter at store (DB) level)
            return [d for d in docs if d.identity.document_uid in authorized_doc_ids]
        except Exception as e:
            logger.error(f"Error retrieving metadata for tag {tag_id}: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata for tag {tag_id}: {e}")

    @authorize(Action.READ, Resource.DOCUMENTS)
    def get_document_metadata(self, user: KeycloakUser, document_uid: str) -> DocumentMetadata:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

        try:
            metadata = self.metadata_store.get_metadata_by_uid(document_uid)
        except Exception as e:
            logger.error(f"Error retrieving metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to get metadata: {e}")

        if metadata is None:
            raise MetadataNotFound(f"No document found with UID {document_uid}")

        return metadata

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    def add_tag_id_to_document(self, user: KeycloakUser, metadata: DocumentMetadata, new_tag_id: str, consistency_token=None) -> None:
        self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, new_tag_id, consistency_token=consistency_token)

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
                self._set_tag_as_parent_in_rebac(new_tag_id, metadata.document_uid)

                logger.info(f"[METADATA] Added tag '{new_tag_id}' to document '{metadata.document_name}' by '{user.uid}'")
            else:
                logger.info(f"[METADATA] Tag '{new_tag_id}' already present on document '{metadata.document_name}' — no change.")

        except Exception as e:
            logger.error(f"Error updating retrievable flag for {metadata.document_name}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    def remove_tag_id_from_document(self, user: KeycloakUser, metadata: DocumentMetadata, tag_id_to_remove: str) -> None:
        self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id_to_remove)

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

            self._remove_tag_as_parent_in_rebac(tag_id_to_remove, metadata.document_uid)

        except Exception as e:
            logger.error(f"Failed to remove tag '{tag_id_to_remove}' from document '{metadata.document_name}': {e}")
            raise MetadataUpdateError(f"Failed to remove tag: {e}")

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    def update_document_retrievable(self, user: KeycloakUser, document_uid: str, value: bool, modified_by: str) -> None:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")

        self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, document_uid)

        try:
            metadata = self.metadata_store.get_metadata_by_uid(document_uid)
            if not metadata:
                raise MetadataNotFound(f"Document '{document_uid}' not found.")

            metadata.source.retrievable = value
            metadata.identity.modified = datetime.now(timezone.utc)
            metadata.identity.last_modified_by = modified_by

            self.metadata_store.save_metadata(metadata)
            logger.info(f"[METADATA] Set retrievable={value} for document '{document_uid}' by '{modified_by}'")

        except Exception as e:
            logger.error(f"Error updating retrievable flag for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    @authorize(Action.CREATE, Resource.DOCUMENTS)
    def save_document_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        """
        Save document metadata and update tag timestamps for any assigned tags.
        This is an internal method only called by other services
        """
        # Check if user has permissions to add document in all specified tags
        if metadata.tags:
            for tag_id in metadata.tags.tag_ids:
                self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        try:
            # Save the metadata first
            self.metadata_store.save_metadata(metadata)
            for tag_id in metadata.tags.tag_ids:
                self._set_tag_as_parent_in_rebac(tag_id, metadata.document_uid)

            # Update tag timestamps for any tags assigned to this document
            if metadata.tags:
                self._update_tag_timestamps(user, metadata.tags.tag_ids)

        except Exception as e:
            logger.error(f"Error saving metadata for {metadata.document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to save metadata: {e}")

    def _handle_tag_timestamp_updates(self, user: KeycloakUser, document_uid: str, new_tags: list[str]) -> None:
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
                self._update_tag_timestamps(user, list(affected_tags))

        except Exception as e:
            logger.warning(f"Failed to handle tag timestamp updates for {document_uid}: {e}")

    def _update_tag_timestamps(self, user: KeycloakUser, tag_ids: list[str]) -> None:
        """
        Update timestamps for a list of tag IDs.
        """
        try:
            # Import here to avoid circular imports
            from app.features.tag.service import TagService

            tag_service = TagService()

            for tag_id in tag_ids:
                try:
                    tag_service.update_tag_timestamp(tag_id, user)
                except Exception as tag_error:
                    logger.warning(f"Failed to update timestamp for tag {tag_id}: {tag_error}")

        except Exception as e:
            logger.warning(f"Failed to update tag timestamps: {e}")

    def _set_tag_as_parent_in_rebac(self, tag_id: str, document_uid: str) -> None:
        """
        Add a relation in the ReBAC engine between a tag and a document.
        """
        self.rebac.add_relation(self._get_tag_as_parent_relation(tag_id, document_uid))

    def _remove_tag_as_parent_in_rebac(self, tag_id: str, document_uid: str) -> None:
        """
        Remove a relation in the ReBAC engine between a tag and a document.
        """
        self.rebac.delete_relation(self._get_tag_as_parent_relation(tag_id, document_uid))

    def _get_tag_as_parent_relation(self, tag_id: str, document_uid: str) -> Relation:
        return Relation(subject=RebacReference(Resource.TAGS, tag_id), relation=RelationType.PARENT, resource=RebacReference(Resource.DOCUMENTS, document_uid))
