from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord
from agentic_backend.core.feedback.store.feedback_models import FeedbackRow
from agentic_backend.core.feedback.store.postgres_feedback_store import (
    PostgresFeedbackStore,
)


def _build_feedback() -> FeedbackRecord:
    return FeedbackRecord(
        id="fb-1",
        session_id="session-1",
        message_id="message-1",
        agent_id="agent-1",
        rating=4,
        comment="useful",
        created_at=datetime(2026, 3, 11, 12, 47, tzinfo=timezone.utc),
        user_id="user-1",
    )


def _make_feedback_row(feedback: FeedbackRecord) -> FeedbackRow:
    return FeedbackRow(
        id=feedback.id,
        session_id=feedback.session_id,
        message_id=feedback.message_id,
        agent_id=feedback.agent_id,
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at,
        user_id=feedback.user_id,
    )


def test_feedback_store_methods_use_session():
    async def _run() -> None:
        feedback = _build_feedback()
        row = _make_feedback_row(feedback)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=[row, None])
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[row]))
                    )
                ),
                MagicMock(rowcount=1),
            ]
        )
        mock_session.merge = AsyncMock()

        store = cast(Any, object.__new__(PostgresFeedbackStore))
        store._sessions = None  # bypassed __init__; use_session is patched below

        with patch(
            "agentic_backend.core.feedback.store.postgres_feedback_store.use_session"
        ) as mock_use_session:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _fake_use_session(factory, session=None):
                yield mock_session

            mock_use_session.side_effect = _fake_use_session

            listed = await store.list()
            stored = await store.get(feedback.id)
            await store.save(feedback)
            await store.delete(feedback.id)
            missing = await store.get(feedback.id)

        assert [item.id for item in listed] == [feedback.id]
        assert stored is not None
        assert stored.id == feedback.id
        assert missing is None
        mock_session.merge.assert_awaited_once()

    asyncio.run(_run())
