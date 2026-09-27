# Copyright Thales 2026
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

"""In-memory fake of the writable-document store for offline tests.

Substituted for the Postgres-backed store through `set_store_provider`, so the
chat-time middleware and the router run fully offline: no engine, no real
Postgres, no `ApplicationContext`.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from fred_capability_writable_document.store import (
    WritableDocumentRecord,
    WritableDocumentStore,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FakeWritableDocumentStore(WritableDocumentStore):
    """Dict-backed store keyed by ``(session_id, document_id)``."""

    def __init__(self) -> None:
        self._rows: Dict[Tuple[str, str], WritableDocumentRecord] = {}
        self.notified_calls: List[Tuple[str, str, datetime]] = []

    async def upsert(self, record: WritableDocumentRecord) -> WritableDocumentRecord:
        key = (record.session_id, record.document_id)
        now = _utcnow()
        stored = copy.copy(record)
        existing = self._rows.get(key)
        # Preserve created_at on update; bump updated_at every write.
        stored.created_at = (existing.created_at if existing else None) or (
            record.created_at or now
        )
        stored.updated_at = now
        self._rows[key] = stored
        return copy.copy(stored)

    async def get(
        self, session_id: str, document_id: str
    ) -> WritableDocumentRecord | None:
        row = self._rows.get((session_id, document_id))
        return copy.copy(row) if row is not None else None

    async def list_for_session(self, session_id: str) -> list[WritableDocumentRecord]:
        return [
            copy.copy(row) for (sid, _), row in self._rows.items() if sid == session_id
        ]

    async def list_user_edited_unnotified(
        self, session_id: str
    ) -> list[WritableDocumentRecord]:
        return [
            copy.copy(row)
            for (sid, _), row in self._rows.items()
            if sid == session_id
            and row.updated_by == "user"
            and row.agent_notified_at is None
        ]

    async def mark_agent_notified(
        self, session_id: str, document_id: str, ts: datetime
    ) -> None:
        self.notified_calls.append((session_id, document_id, ts))
        row = self._rows.get((session_id, document_id))
        if row is not None:
            row.agent_notified_at = ts
