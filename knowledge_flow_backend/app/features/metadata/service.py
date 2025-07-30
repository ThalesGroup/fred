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

from app.common.document_structures import DocumentMetadata
from app.common.structures import Status
from app.core.stores.metadata.base_metadata_store import MetadataDeserializationError
from app.features.metadata.structures import UpdateDocumentMetadataResponse
from app.application_context import ApplicationContext

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
        self.config = ApplicationContext.get_instance().get_config()
        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        self.catalog_store = ApplicationContext.get_instance().get_catalog_store()

    def get_documents_metadata(self, filters_dict: dict) -> list[DocumentMetadata]:
        try:
            return self.metadata_store.get_all_metadata(filters_dict)
        except MetadataDeserializationError as e:
            logger.error(f"[Metadata] Deserialization error: {e}")
            raise MetadataUpdateError(f"Invalid metadata encountered: {e}")

        except Exception as e:
            logger.error(f"Error retrieving document metadata: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata: {e}")

    def get_document_metadata_in_tag(self, tag_id: str) -> list[DocumentMetadata]:
        """
        Return all metadata entries associated with a specific tag.
        """
        try:
            return self.metadata_store.get_metadata_in_tag(tag_id)
        except Exception as e:
            logger.error(f"Error retrieving metadata for tag {tag_id}: {e}")
            raise MetadataUpdateError(f"Failed to retrieve metadata for tag {tag_id}: {e}")

    def delete_document_metadata(self, document_uid: str) -> None:
        metadata = self.metadata_store.get_metadata_by_uid(document_uid)
        if not metadata:
            raise MetadataNotFound(f"No document found with UID {document_uid}")
        try:
            self.metadata_store.delete_metadata(metadata)
        except Exception as e:
            logger.error(f"Error deleting metadata: {e}")
            raise MetadataUpdateError(f"Failed to delete metadata for {document_uid}: {e}")

    def get_document_metadata(self, document_uid: str) -> DocumentMetadata:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        try:
            metadata = self.metadata_store.get_metadata_by_uid(document_uid)
        except Exception as e:
            logger.error(f"Error retrieving metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to get metadata: {e}")

        if metadata is None:
            raise MetadataNotFound(f"No document found with UID {document_uid}")

        return metadata

    def update_document_retrievable(self, document_uid: str, update) -> UpdateDocumentMetadataResponse:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        try:
            result = self.metadata_store.update_metadata_field(document_uid=document_uid, field="retrievable", value=update.retrievable)
            return UpdateDocumentMetadataResponse(status=Status.SUCCESS, metadata=result)
        except Exception as e:
            logger.error(f"Error updating retrievable flag for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update retrievable flag: {e}")

    def update_document_metadata(self, document_uid: str, update_fields: dict) -> UpdateDocumentMetadataResponse:
        if not document_uid:
            raise InvalidMetadataRequest("Document UID cannot be empty")
        if not update_fields:
            raise InvalidMetadataRequest("No metadata fields provided for update")
        try:
            logger.info(f"Updating metadata for {document_uid} with {update_fields}")

            # if tags are changed, update `updated_at` timestamp for each tag
            if "tags" in update_fields:
                self._handle_tag_timestamp_updates(document_uid, update_fields["tags"])

            result = None
            for field, value in update_fields.items():
                result = self.metadata_store.update_metadata_field(document_uid=document_uid, field=field, value=value)
            return UpdateDocumentMetadataResponse(status=Status.SUCCESS, metadata=result)
        except Exception as e:
            logger.error(f"Error updating metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update metadata: {e}")

    def save_document_metadata(self, metadata: DocumentMetadata) -> None:
        """
        Save document metadata and update tag timestamps for any assigned tags.
        """
        try:
            # Save the metadata first
            self.metadata_store.save_metadata(metadata)

            # Update tag timestamps for any tags assigned to this document
            if metadata.tags:
                self._update_tag_timestamps(metadata.tags)

        except Exception as e:
            logger.error(f"Error saving metadata for {metadata.document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to save metadata: {e}")

    def _handle_tag_timestamp_updates(self, document_uid: str, new_tags: list[str]) -> None:
        """
        Update tag timestamps when document tags are modified.
        """
        try:
            # Get old tags from current document metadata
            old_document = self.get_document_metadata(document_uid)
            old_tags = old_document.tags or []

            # Find tags that were added or removed
            old_tags_set = set(old_tags)
            new_tags_set = set(new_tags or [])

            affected_tags = old_tags_set.symmetric_difference(new_tags_set)

            # Update timestamps for affected tags
            if affected_tags:
                self._update_tag_timestamps(list(affected_tags))

        except Exception as e:
            logger.warning(f"Failed to handle tag timestamp updates for {document_uid}: {e}")

    def _update_tag_timestamps(self, tag_ids: list[str]) -> None:
        """
        Update timestamps for a list of tag IDs.
        """
        try:
            # Import here to avoid circular imports
            from app.features.tag.service import TagService

            tag_service = TagService()

            for tag_id in tag_ids:
                try:
                    tag_service.update_tag_timestamp(tag_id)
                except Exception as tag_error:
                    logger.warning(f"Failed to update timestamp for tag {tag_id}: {tag_error}")

        except Exception as e:
            logger.warning(f"Failed to update tag timestamps: {e}")
