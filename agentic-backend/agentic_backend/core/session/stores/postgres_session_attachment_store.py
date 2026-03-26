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
from typing import List

from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)
from agentic_backend.core.session.stores.session_attachment_models import (
    SessionAttachmentRow,
)

logger = logging.getLogger(__name__)


class PostgresSessionAttachmentStore(BaseSessionAttachmentStore):
    """
    PostgreSQL-backed storage for session attachments (ORM sessions).
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def save(
        self, record: SessionAttachmentRecord, session: AsyncSession | None = None
    ) -> None:
        now = datetime.now(timezone.utc)
        row = SessionAttachmentRow(
            session_id=record.session_id,
            attachment_id=record.attachment_id,
            name=record.name,
            mime=record.mime,
            size_bytes=record.size_bytes,
            summary_md=record.summary_md,
            document_uid=record.document_uid,
            created_at=record.created_at or now,
            updated_at=record.updated_at or now,
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)

    async def list_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> List[SessionAttachmentRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(SessionAttachmentRow)
                        .where(SessionAttachmentRow.session_id == session_id)
                        .order_by(SessionAttachmentRow.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            SessionAttachmentRecord(
                session_id=row.session_id,
                attachment_id=row.attachment_id,
                name=row.name,
                mime=row.mime,
                size_bytes=row.size_bytes,
                summary_md=row.summary_md,
                document_uid=row.document_uid,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def delete(
        self, session_id: str, attachment_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(SessionAttachmentRow).where(
                    SessionAttachmentRow.session_id == session_id,
                    SessionAttachmentRow.attachment_id == attachment_id,
                )
            )

    async def delete_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(SessionAttachmentRow).where(
                    SessionAttachmentRow.session_id == session_id
                )
            )

    async def count_for_sessions(
        self, session_ids: List[str], session: AsyncSession | None = None
    ) -> int:
        if not session_ids:
            return 0
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(func.count())
                .select_from(SessionAttachmentRow)
                .where(SessionAttachmentRow.session_id.in_(session_ids))
            )
            return result.scalar() or 0
