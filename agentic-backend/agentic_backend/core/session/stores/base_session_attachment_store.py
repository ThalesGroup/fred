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
from typing import List, Optional


@dataclass
class SessionAttachmentRecord(ABC):
    session_id: str
    attachment_id: str
    name: str
    summary_md: str
    document_uid: Optional[str] = None
    mime: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BaseSessionAttachmentStore:
    """
    Persistence contract for session-scoped attachment summaries.
    """

    @abstractmethod
    async def save(
        self, record: SessionAttachmentRecord
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def list_for_session(
        self, session_id: str
    ) -> List[SessionAttachmentRecord]:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete(
        self, session_id: str, attachment_id: str
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete_for_session(
        self, session_id: str
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def count_for_sessions(
        self, session_ids: List[str]
    ) -> int:  # pragma: no cover - interface
        pass
