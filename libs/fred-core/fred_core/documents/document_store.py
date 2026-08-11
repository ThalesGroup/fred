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


class BaseDocumentMetadataStore:
    """
    Abstract interface for reading and writing structured document metadata records.

    Concrete implementations may rely on PostgreSQL or an in-memory backend.
    """

    @abstractmethod
    async def count_all(self, session: AsyncSession | None = None) -> int:
        """Return the total number of document metadata records in the store."""

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

    @abstractmethod
    async def get_metadata_by_uid(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> DocumentMetadata | None:
        """
        Retrieve a metadata document by its UID.

        :raises DocumentMetadataDeserializationError: if stored data is malformed.
        """

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

    async def total_size_by_tags(
        self, tag_ids: List[str], session: AsyncSession | None = None
    ) -> dict[str, int]:
        """Sum of ``file.file_size_bytes`` across every document in each given tag.

        Deliberately NOT paginated — the folder-size UI needs an exact total
        regardless of how many documents a folder holds. This default loops per
        tag via ``get_metadata_in_tag``; SQL-backed stores should override with a
        single aggregate query (see ``PostgresDocumentMetadataStore``).
        """
        result: dict[str, int] = {}
        for tag_id in tag_ids:
            docs = await self.get_metadata_in_tag(tag_id, session=session)
            result[tag_id] = sum(
                (d.file.file_size_bytes or 0) for d in docs if d.file is not None
            )
        return result

    @abstractmethod
    async def list_by_source_tag(
        self, source_tag: str, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        """Return all metadata entries originating from a specific pull source."""

    @abstractmethod
    async def save_metadata(
        self, metadata: DocumentMetadata, session: AsyncSession | None = None
    ) -> None:
        """
        Create or update a metadata entry.

        - Overwrites existing metadata if the same UID already exists.
        - Adds a new entry otherwise.

        Use this only where creating the document is a legitimate outcome
        (registration). Anything updating a document it already read must use
        `update_metadata`, or a late writer can re-create a deleted document.

        :raises ValueError: if 'document_uid' is missing.
        """

    @abstractmethod
    async def update_metadata(
        self, metadata: DocumentMetadata, session: AsyncSession | None = None
    ) -> bool:
        """
        Update an existing metadata entry, never creating one.

        Returns True when a row was updated, False when the document no longer
        exists. Implementations MUST make that determination atomically (a
        single conditional UPDATE, not a read followed by a save) — same rule,
        and the same reason, as `delete_metadata` below.

        The caller that must not resurrect a document is a long-running writer
        that cannot be stopped: an ingestion activity runs its work in a thread
        (`asyncio.to_thread`), which Python cannot kill, so it keeps going after
        a cancellation deleted the document and then persists what it computed.
        Through `save_metadata` that write re-creates the row — stuck
        `in_progress` forever, and, because the service sees no previous
        metadata, it also re-credits storage quota, re-adds the ReBAC parent
        link and emits a document-created KPI for a document the user deleted
        (#2315). A conditional UPDATE makes the whole class impossible rather
        than narrowing its window.

        :raises ValueError: if 'document_uid' is missing.
        """

    @abstractmethod
    async def delete_metadata(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> bool:
        """
        Delete a metadata entry by its UID.

        Returns True when *this* call removed the row, False when the row was
        already gone. Implementations MUST make that determination atomically
        (a single conditional DELETE, not a read followed by a delete): callers
        use the result to decide whether to apply a side effect that must happen
        exactly once, such as releasing the document's storage quota. A
        read-then-delete lets two concurrent callers both observe the row and
        both report success, releasing the same bytes twice (#2149).

        :raises ValueError: if 'document_uid' is missing.
        """

    @abstractmethod
    async def clear(self, session: AsyncSession | None = None) -> None:
        """Delete all metadata records from the store. Destructive — dev/test only."""
