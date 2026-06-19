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

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.core.session.stores.base_writable_document_store import (
    BaseWritableDocumentStore,
    WritableDocumentAuthor,
    WritableDocumentRecord,
)
from agentic_backend.core.session.stores.writable_document_models import (
    WritableDocumentRow,
)

logger = logging.getLogger(__name__)


def _to_record(row: WritableDocumentRow) -> WritableDocumentRecord:
    return WritableDocumentRecord(
        session_id=row.session_id,
        document_id=row.document_id,
        title=row.title,
        content_md=row.content_md,
        updated_by=WritableDocumentAuthor(row.updated_by),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresWritableDocumentStore(BaseWritableDocumentStore):
    """PostgreSQL-backed storage for session writable documents (ORM sessions)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert(
        self, record: WritableDocumentRecord, session: AsyncSession | None = None
    ) -> WritableDocumentRecord:
        now = datetime.now(timezone.utc)
        async with use_session(self._sessions, session) as s:
            existing = await s.get(
                WritableDocumentRow, (record.session_id, record.document_id)
            )
            if existing is None:
                row = WritableDocumentRow(
                    session_id=record.session_id,
                    document_id=record.document_id,
                    title=record.title,
                    content_md=record.content_md,
                    updated_by=record.updated_by.value,
                    created_at=record.created_at or now,
                    updated_at=record.updated_at or now,
                )
                row = await s.merge(row)
            else:
                existing.title = record.title
                existing.content_md = record.content_md
                existing.updated_by = record.updated_by.value
                existing.updated_at = record.updated_at or now
                row = existing
            await s.flush()
            return _to_record(row)

    async def get(
        self, session_id: str, document_id: str, session: AsyncSession | None = None
    ) -> Optional[WritableDocumentRecord]:
        async with use_session(self._sessions, session) as s:
            row = await s.get(WritableDocumentRow, (session_id, document_id))
            return _to_record(row) if row is not None else None

    async def list_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> List[WritableDocumentRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(WritableDocumentRow)
                        .where(WritableDocumentRow.session_id == session_id)
                        .order_by(WritableDocumentRow.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
        return [_to_record(row) for row in rows]

    async def delete(
        self, session_id: str, document_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(WritableDocumentRow).where(
                    WritableDocumentRow.session_id == session_id,
                    WritableDocumentRow.document_id == document_id,
                )
            )

    async def delete_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(WritableDocumentRow).where(
                    WritableDocumentRow.session_id == session_id
                )
            )
