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

from fred_core.documents.document_structures import DocumentMetadata


class DocumentMetadataDeserializationError(Exception):
    """Raised when document metadata cannot be parsed correctly due to invalid fields or enum mismatches."""

    pass


class BaseDocumentMetadataStore:
    """
    Abstract interface for reading and writing structured document metadata records.

    Concrete implementations may rely on PostgreSQL or an in-memory backend.
    """

    @abstractmethod
    async def count_all(self, session: AsyncSession | None = None) -> int:
        """Return the total number of document metadata records in the store."""
        pass

    @abstractmethod
    async def get_all_metadata(
        self, filters: dict, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        """
        Return all metadata documents matching the given filters.

        Filters should be a dictionary where:
        - Keys are metadata field names (e.g., "source_tag", "tags")
        - Values are filter values (exact match). Lists are interpreted as 'terms'.
        """
        pass

    @abstractmethod
    async def get_metadata_by_uid(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> DocumentMetadata | None:
        """
        Retrieve a metadata document by its UID.

        :raises DocumentMetadataDeserializationError: if stored data is malformed.
        """
        pass

    async def get_metadata_by_uids(
        self, document_uids: list[str], session: AsyncSession | None = None
    ) -> list[DocumentMetadata]:
        """
        Return metadata documents for one targeted document uid list.

        Concrete stores should override this with a single batch query when possible.
        """
        unique_uids = list(dict.fromkeys(document_uids))
        if not unique_uids:
            return []

        documents = await asyncio.gather(
            *(
                self.get_metadata_by_uid(document_uid, session=session)
                for document_uid in unique_uids
            )
        )
        return [document for document in documents if document is not None]

    @abstractmethod
    async def get_metadata_in_tag(
        self, tag_id: str, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        """Return all metadata entries that are tagged with a specific tag ID."""
        pass

    async def browse_metadata_in_tag(
        self,
        tag_id: str,
        offset: int = 0,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> tuple[List[DocumentMetadata], int]:
        """Return a paginated list of metadata entries tagged with a specific tag ID."""
        all_docs = await self.get_metadata_in_tag(tag_id, session=session)
        total = len(all_docs)
        return all_docs[offset : offset + limit], total

    @abstractmethod
    async def list_by_source_tag(
        self, source_tag: str, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        """Return all metadata entries originating from a specific pull source."""
        pass

    @abstractmethod
    async def save_metadata(
        self, metadata: DocumentMetadata, session: AsyncSession | None = None
    ) -> None:
        """
        Create or update a metadata entry.

        - Overwrites existing metadata if the same UID already exists.
        - Adds a new entry otherwise.

        :raises ValueError: if 'document_uid' is missing.
        """
        pass

    @abstractmethod
    async def delete_metadata(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> None:
        """
        Delete a metadata entry by its UID.

        :raises ValueError: if 'document_uid' is missing.
        """
        pass

    @abstractmethod
    async def clear(self, session: AsyncSession | None = None) -> None:
        """Delete all metadata records from the store. Destructive — dev/test only."""
        pass
