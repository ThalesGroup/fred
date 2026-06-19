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

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession


class WritableDocumentsDisabledError(RuntimeError):
    """Raised when writable-document persistence is not configured."""

    def __init__(self) -> None:
        super().__init__("Writable documents are not enabled in this environment.")


class WritableDocumentNotFoundError(LookupError):
    """Raised when a writable document does not exist for a session."""

    def __init__(self, session_id: str, document_id: str) -> None:
        self.session_id = session_id
        self.document_id = document_id
        super().__init__(
            f"Writable document {document_id} not found for session {session_id}."
        )


class WritableDocumentAuthor(str, Enum):
    """Who last touched a writable document.

    Used by edit-detection: a document is "user-edited" since the previous turn
    when ``updated_by == user`` and its ``updated_at`` is newer than the last
    message of the prior exchange.
    """

    agent = "agent"
    user = "user"


@dataclass
class WritableDocumentRecord:
    """A collaborative markdown document scoped to one chat session.

    Co-authored over time by the agent (via the ``write_document`` tool) and the
    user (via the editor pane). Only the last author is tracked (``updated_by``).
    """

    session_id: str
    document_id: str
    title: str
    content_md: str
    updated_by: WritableDocumentAuthor = WritableDocumentAuthor.agent
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BaseWritableDocumentStore(ABC):
    """Persistence contract for session-scoped writable documents."""

    @abstractmethod
    async def upsert(
        self, record: WritableDocumentRecord, session: AsyncSession | None = None
    ) -> WritableDocumentRecord:  # pragma: no cover - interface
        """Create or update a document; returns the stored record (with timestamps)."""
        pass

    @abstractmethod
    async def get(
        self, session_id: str, document_id: str, session: AsyncSession | None = None
    ) -> Optional[WritableDocumentRecord]:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def list_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> List[WritableDocumentRecord]:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete(
        self, session_id: str, document_id: str, session: AsyncSession | None = None
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> None:  # pragma: no cover - interface
        pass
