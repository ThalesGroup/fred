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

from abc import abstractmethod
from typing import List, Optional

from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.core.stores.metadata.base_catalog_store import BaseCatalogStore


class MetadataDeserializationError(Exception):
    """Raised when document metadata cannot be parsed correctly due to invalid fields or enum mismatches."""

    pass


class BaseMetadataStore(BaseCatalogStore):
    """
    Abstract interface for reading and writing structured metadata records
    (typically associated with ingested documents).

    Concrete implementations may rely on OpenSearch, a local store, or other backends.
    """

    @abstractmethod
    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Return all metadata documents matching the given filters.

        Filters should be a dictionary where:
        - Keys are metadata field names (e.g., "source_tag", "tags")
        - Values are filter values (exact match). Lists are interpreted as 'terms'.

        :param filters: dict of metadata field filters.
        :return: list of metadata documents matching the query.
        """
        pass

    @abstractmethod
    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        """
        Retrieve a metadata document by its UID.

        :param document_uid: the unique identifier of the document.
        :return: the metadata if found, or None.
        :raises MetadataDeserializationError: if stored data is malformed.
        """
        pass

    @abstractmethod
    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Return all metadata entries that are tagged with a specific tag ID.

        :param tag_id: tag to filter by (exact match).
        :return: list of matching metadata documents.
        :raises MetadataDeserializationError: if any document is malformed.
        """
        pass

    @abstractmethod
    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        """
        Return all metadata entries originating from a specific pull source.

        :param source_tag: source identifier used during ingestion (e.g., "github", "uploads").
        :return: list of metadata entries associated with that source.
        """
        pass

    @abstractmethod
    def save_metadata(self, metadata: DocumentMetadata) -> None:
        """
        Create or update a metadata entry.

        - Overwrites existing metadata if the same UID already exists.
        - Adds a new entry otherwise.

        :param metadata: metadata to save.
        :raises ValueError: if 'document_uid' is missing.
        :raises RuntimeError: if the save operation fails.
        """
        pass

    @abstractmethod
    def delete_metadata(self, metadata: DocumentMetadata) -> bool:
        """
        Remove a metadata entry by UID.

        :param metadata: metadata containing the UID to delete.
        :return: True if deletion succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def update_processing_stage(self, document_uid: str, stage: ProcessingStage, status: str) -> None:
        """
        Update the processing stage status for a specific document.

        :param document_uid: the document to update.
        :param stage: a predefined processing stage (enum).
        :param status: new value for the stage (e.g., "done", "failed").
        :raises Exception: if the update fails.
        """
        pass

    @abstractmethod
    def set_retrievable_flag(self, document_uid: str, value: bool) -> None:
        """
        Set whether this document should be exposed to retrieval (e.g., in AI chat).

        :param document_uid: the document to update.
        :param value: True to mark as retrievable, False to exclude from search.
        :raises Exception: if update fails.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Delete all metadata records from the store.

        ⚠️ This operation is destructive and typically only used in test or dev mode.

        :raises Exception: if the operation fails.
        """
        pass
