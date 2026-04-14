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
from abc import abstractmethod
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_flow_backend.common.document_structures import DocumentMetadata


class MetadataDeserializationError(Exception):
    """Raised when document metadata cannot be parsed correctly due to invalid fields or enum mismatches."""

    pass


class BaseMetadataStore:
    """
    Abstract interface for reading and writing structured metadata records
    (typically associated with ingested documents).

    Concrete implementations may rely on OpenSearch, a local store, or other backends.
    """

    @abstractmethod
    async def get_all_metadata(self, filters: dict, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        """
        Return all metadata documents matching the given filters.

        Filters should be a dictionary where:
        - Keys are metadata field names (e.g., "source_tag", "tags")
        - Values are filter values (exact match). Lists are interpreted as 'terms'.

        :param filters: dict of metadata field filters.
        :param session: optional SQLAlchemy async session.
        :return: list of metadata documents matching the query.
        """
        pass

    @abstractmethod
    async def get_metadata_by_uid(self, document_uid: str, session: AsyncSession | None = None) -> DocumentMetadata | None:
        """
        Retrieve a metadata document by its UID.

        :param document_uid: the unique identifier of the document.
        :param session: optional SQLAlchemy async session.
        :return: the metadata if found, or None.
        :raises MetadataDeserializationError: if stored data is malformed.
        """
        pass

    async def get_metadata_by_uids(self, document_uids: list[str], session: AsyncSession | None = None) -> list[DocumentMetadata]:
        """
        Return metadata documents for one targeted document uid list.

        Why this exists:
        - Callers such as tabular authorization already know the candidate
          document ids from ReBAC and should not have to scan the full metadata
          catalog to resolve them.

        How to use:
        - Pass the document uids needed for one request.
        - Concrete stores should override this method with one backend-native
          batch query when they can do so efficiently.

        Example:
        - `docs = await metadata_store.get_metadata_by_uids(["doc-1", "doc-2"])`
        """
        unique_uids = list(dict.fromkeys(document_uids))
        if not unique_uids:
            return []

        documents = await asyncio.gather(*(self.get_metadata_by_uid(document_uid, session=session) for document_uid in unique_uids))
        return [document for document in documents if document is not None]

    @abstractmethod
    async def get_metadata_in_tag(self, tag_id: str, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        """
        Return all metadata entries that are tagged with a specific tag ID.

        :param tag_id: tag to filter by (exact match).
        :param session: optional SQLAlchemy async session.
        :return: list of matching metadata documents.
        :raises MetadataDeserializationError: if any document is malformed.
        """
        pass

    async def browse_metadata_in_tag(self, tag_id: str, offset: int = 0, limit: int = 50, session: AsyncSession | None = None) -> tuple[List[DocumentMetadata], int]:
        """
        Return a paginated list of metadata entries tagged with a specific tag ID.

        The second element of the tuple is the total number of documents that match
        the tag (ignoring pagination).
        """
        # Default fallback implementation: load all then slice.
        all_docs = await self.get_metadata_in_tag(tag_id, session=session)
        total = len(all_docs)
        return all_docs[offset : offset + limit], total

    @abstractmethod
    async def list_by_source_tag(self, source_tag: str, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        """
        Return all metadata entries originating from a specific pull source.

        :param source_tag: source identifier used during ingestion (e.g., "github", "fred").
        :param session: optional SQLAlchemy async session.
        :return: list of metadata entries associated with that source.
        """
        pass

    @abstractmethod
    async def save_metadata(self, metadata: DocumentMetadata, session: AsyncSession | None = None) -> None:
        """
        Create or update a metadata entry.

        - Overwrites existing metadata if the same UID already exists.
        - Adds a new entry otherwise.

        :param metadata: metadata to save.
        :param session: optional SQLAlchemy async session.
        :raises ValueError: if 'document_uid' is missing.
        :raises RuntimeError: if the save operation fails.
        """
        pass

    @abstractmethod
    async def delete_metadata(self, document_uid: str, session: AsyncSession | None = None) -> None:
        """
        Delete a metadata entry by its UID.

        :param document_uid: the unique identifier of the document.
        :param session: optional SQLAlchemy async session.
        :raises ValueError: if 'document_uid' is missing.
        :raises RuntimeError: if the delete operation fails.
        """
        pass

    @abstractmethod
    async def clear(self, session: AsyncSession | None = None) -> None:
        """
        Delete all metadata records from the store.

        ⚠️ This operation is destructive and typically only used in test or dev mode.

        :param session: optional SQLAlchemy async session.
        :raises Exception: if the operation fails.
        """
        pass
