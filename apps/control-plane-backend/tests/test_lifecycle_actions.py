"""
Offline unit tests for session lifecycle actions (scheduler-driven).

Ref: docs/backlog/BACKLOG.md §6.4.E — session lifecycle policies, purge queue,
     due-candidate listing, and the CTRLP-12 E1 erase-at-expiry action.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
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


def _event(
    *,
    session_id: str = "session-2",
    team_id: str | None = "team-9",
    user_id: str | None = "alice",
) -> ConversationLifecycleEvent:
    return ConversationLifecycleEvent(
        conversation_id=session_id,
        team_id=team_id,
        user_id=user_id,
        trigger=LifecycleTrigger.MEMBER_REMOVED,
        created_at=datetime(2026, 4, 25, 8, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 4, 25, 8, 0, tzinfo=UTC),
    )


class _FakeQueueStore:
    def __init__(self) -> None:
        self.marked: list[str] = []

    async def mark_done(self, *, session_id: str) -> None:
        self.marked.append(session_id)


def _deps(
    *,
    queue_store: _FakeQueueStore,
    erase_session: Any,
    bearer: str = "Bearer svc-token",
) -> LifecycleActionDependencies:
    async def _get_bearer() -> str:
        return bearer

    return LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: queue_store),
        erase_session=erase_session,
        get_service_bearer=_get_bearer,
    )


@pytest.mark.asyncio
async def test_list_due_conversation_candidates_threads_user_id() -> None:
    """E1: candidate listing carries the queue row's real user_id (not dropped)."""
    due_at = datetime(2026, 4, 25, 7, 30, tzinfo=UTC)

    class _QueueItem:
        session_id = "session-1"
        team_id = "team-1"
        user_id = "owner-1"
        created_at = due_at

    class _QueueStore:
        async def list_due(self, *, limit: int) -> list[_QueueItem]:
            assert limit == 10
            return [_QueueItem()]

    deps = LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: _QueueStore()),
        erase_session=cast(Any, None),
        get_service_bearer=cast(Any, None),
    )

    batch = await list_due_conversation_candidates(limit=10, deps=deps)

    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert candidate.conversation_id == "session-1"
    assert candidate.team_id == "team-1"
    assert candidate.user_id == "owner-1"  # E1: no longer dropped
    assert candidate.created_at == due_at


@pytest.mark.asyncio
async def test_erase_at_expiry_uses_queue_identity_and_marks_done_on_ok() -> None:
    """E1: erase_session runs with the queue row's own user_id/team_id/session_id
    and the service bearer; a fully-ok receipt marks the queue entry done."""
    calls: list[dict[str, Any]] = []

    async def _erase(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(ok=True)

    queue = _FakeQueueStore()
    result = await delete_conversation_and_mark_done(
        event=_event(session_id="s-2", team_id="team-9", user_id="alice"),
        deps=_deps(queue_store=queue, erase_session=_erase),
    )

    assert result.ok is True
    assert result.action == "erased"
    # Threaded the queue row's OWN identity (not a hard-coded value) + the bearer.
    assert calls == [
        {
            "team_id": "team-9",
            "session_id": "s-2",
            "user_id": "alice",
            "authorization": "Bearer svc-token",
        }
    ]
    assert queue.marked == ["s-2"]


@pytest.mark.asyncio
async def test_erase_at_expiry_leaves_queued_on_partial_receipt() -> None:
    """E1: a partial receipt (some store failed) must NOT mark the entry done —
    the next tick retries. A hidden-but-never-erased conversation is a defect."""

    async def _erase(**_kwargs: Any) -> Any:
        return SimpleNamespace(ok=False)

    queue = _FakeQueueStore()
    result = await delete_conversation_and_mark_done(
        event=_event(),
        deps=_deps(queue_store=queue, erase_session=_erase),
    )

    assert result.ok is False
    assert result.action == "erase_incomplete"
    assert queue.marked == []  # left queued for retry


@pytest.mark.asyncio
async def test_erase_at_expiry_retryable_when_bearer_mint_fails() -> None:
    """E1: failing to mint the service bearer is retryable — leave it queued."""

    async def _erase(**_kwargs: Any) -> Any:  # pragma: no cover - never reached
        raise AssertionError("erase must not run without a bearer")

    async def _failing_bearer() -> str:
        raise RuntimeError("Missing Keycloak client secret")

    queue = _FakeQueueStore()
    deps = LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: queue),
        erase_session=cast(Any, _erase),
        get_service_bearer=_failing_bearer,
    )

    result = await delete_conversation_and_mark_done(event=_event(), deps=deps)

    assert result.ok is False
    assert result.action == "erase_failed"
    assert queue.marked == []


@pytest.mark.asyncio
async def test_erase_at_expiry_skips_event_missing_owner() -> None:
    """E1: an event with no user_id/team_id cannot be safely erased — leave it
    queued rather than guess an identity."""

    async def _erase(**_kwargs: Any) -> Any:  # pragma: no cover - never reached
        raise AssertionError("erase must not run without an owner")

    queue = _FakeQueueStore()
    result = await delete_conversation_and_mark_done(
        event=_event(user_id=None),
        deps=_deps(queue_store=queue, erase_session=_erase),
    )

    assert result.ok is False
    assert result.action == "erase_skipped"
    assert queue.marked == []
