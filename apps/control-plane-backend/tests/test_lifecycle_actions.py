from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, cast

import pytest

from control_plane_backend.scheduler.dependencies import (
    LifecycleActionDependencies,
)
from control_plane_backend.scheduler.lifecycle_actions import (
    delete_conversation_and_mark_done,
    list_due_conversation_candidates,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)


@pytest.mark.asyncio
async def test_list_due_conversation_candidates_supports_explicit_dependencies() -> (
    None
):
    """
    Verify lifecycle candidate listing can run with injected store dependencies.

    Why this test exists:
    - Slice 4 moves lifecycle actions away from direct singleton access, so the
      explicit dependency seam needs one offline regression test

    How to use it:
    - run with the default offline control-plane test suite

    Example:
    - `pytest tests/test_lifecycle_actions.py -q`
    """

    created_at = datetime(2026, 4, 25, 7, 30, tzinfo=UTC)

    class _QueueItem:
        def __init__(self) -> None:
            self.session_id = "session-1"
            self.team_id = "team-1"
            self.created_at = created_at

    class _FakeQueueStore:
        async def list_due(self, *, limit: int) -> list[_QueueItem]:
            assert limit == 10
            return [_QueueItem()]

    deps = LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: _FakeQueueStore()),
    )

    batch = await list_due_conversation_candidates(limit=10, deps=deps)

    assert len(batch.candidates) == 1
    assert batch.candidates[0].conversation_id == "session-1"
    assert batch.candidates[0].team_id == "team-1"
    assert batch.candidates[0].trigger == LifecycleTrigger.MEMBER_REMOVED
    assert batch.candidates[0].created_at == created_at


@pytest.mark.asyncio
async def test_delete_conversation_and_mark_done_supports_explicit_dependencies() -> (
    None
):
    """
    Verify lifecycle deletion can run with injected store dependencies.

    Why this test exists:
    - Slice 4 introduces explicit lifecycle-action collaborators and we want a
      direct offline check of the new deletion seam

    How to use it:
    - run with the default offline control-plane test suite

    Example:
    - `pytest tests/test_lifecycle_actions.py -q`
    """

    deleted_sessions: list[str] = []
    marked_sessions: list[str] = []

    class _FakeSessionStore:
        async def delete(self, session_id: str) -> None:
            deleted_sessions.append(session_id)

    class _FakeQueueStore:
        async def mark_done(self, *, session_id: str) -> None:
            marked_sessions.append(session_id)

    deps = LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: _FakeSessionStore()),
        get_purge_queue_store=cast(Any, lambda: _FakeQueueStore()),
    )
    result = await delete_conversation_and_mark_done(
        event=ConversationLifecycleEvent(
            conversation_id="session-2",
            team_id="team-9",
            trigger=LifecycleTrigger.MEMBER_REMOVED,
            created_at=datetime(2026, 4, 25, 8, 0, tzinfo=UTC),
            last_activity_at=datetime(2026, 4, 25, 8, 0, tzinfo=UTC),
        ),
        deps=deps,
    )

    assert result.ok is True
    assert result.action == "deleted"
    assert result.conversation_id == "session-2"
    assert deleted_sessions == ["session-2"]
    assert marked_sessions == ["session-2"]
