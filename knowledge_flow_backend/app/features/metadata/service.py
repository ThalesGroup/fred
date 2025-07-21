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

from app.common.structures import DocumentMetadata, Status
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
            result = self.metadata_store.update_metadata_field(
                document_uid=document_uid,
                field="retrievable",
                value=update.retrievable
            )
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
            result = None
            for field, value in update_fields.items():
                result = self.metadata_store.update_metadata_field(
                    document_uid=document_uid,
                    field=field,
                    value=value
                )
            return UpdateDocumentMetadataResponse(status=Status.SUCCESS, metadata=result)
        except Exception as e:
            logger.error(f"Error updating metadata for {document_uid}: {e}")
            raise MetadataUpdateError(f"Failed to update metadata: {e}")

