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
from typing import List, Optional, cast

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord
from agentic_backend.core.feedback.store.base_feedback_store import BaseFeedbackStore
from agentic_backend.core.feedback.store.feedback_models import FeedbackRow

logger = logging.getLogger(__name__)

FeedbackAdapter = TypeAdapter(FeedbackRecord)


class PostgresFeedbackStore(BaseFeedbackStore):
    """
    PostgreSQL-backed feedback store using SQLAlchemy ORM sessions.
    """

    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)

    async def list(self, session: AsyncSession | None = None) -> List[FeedbackRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(FeedbackRow).order_by(FeedbackRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            FeedbackAdapter.validate_python(row, from_attributes=True) for row in rows
        ]

    async def get(
        self, feedback_id: str, session: AsyncSession | None = None
    ) -> Optional[FeedbackRecord]:
        async with use_session(self._sessions, session) as s:
            row = await s.get(FeedbackRow, feedback_id)
        if row is None:
            return None
        return FeedbackAdapter.validate_python(row, from_attributes=True)

    async def save(
        self, feedback: FeedbackRecord, session: AsyncSession | None = None
    ) -> None:
        row = FeedbackRow(
            id=feedback.id,
            session_id=feedback.session_id,
            message_id=feedback.message_id,
            agent_id=feedback.agent_id,
            rating=feedback.rating,
            comment=feedback.comment,
            created_at=feedback.created_at,
            user_id=feedback.user_id,
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)
        logger.info("[FEEDBACK][PG] Saved feedback entry '%s'", feedback.id)

    async def delete(
        self, feedback_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            result = cast(
                CursorResult,
                await s.execute(
                    delete(FeedbackRow).where(FeedbackRow.id == feedback_id)
                ),
            )
        deleted = result.rowcount
        if deleted:
            logger.info("[FEEDBACK][PG] Deleted feedback entry '%s'", feedback_id)
        else:
            logger.warning(
                "[FEEDBACK][PG] Feedback entry '%s' not found for deletion", feedback_id
            )
