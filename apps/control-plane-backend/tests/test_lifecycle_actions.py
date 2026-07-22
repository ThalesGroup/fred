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


class _NoopTaskService:
    """Records nothing; the worker's erasure-task bookkeeping is best-effort and
    not under test here (no active task → no transitions)."""

    async def record(self, *_a: Any, **_k: Any) -> None:
        return None

    async def list_tasks(self, *_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(tasks=[])


def _deps(
    *,
    queue_store: _FakeQueueStore,
    erase_session: Any,
    bearer: str = "Bearer svc-token",
    task_service: Any = None,
) -> LifecycleActionDependencies:
    async def _get_bearer() -> str:
        return bearer

    return LifecycleActionDependencies(
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: queue_store),
        erase_session=erase_session,
        get_service_bearer=_get_bearer,
        get_task_service=cast(Any, lambda: task_service or _NoopTaskService()),
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
        get_task_service=cast(Any, None),
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
        return SimpleNamespace(
            ok=False,
            stores=[
                SimpleNamespace(store="attachments", ok=True, error=None),
                SimpleNamespace(store="runtime_checkpoint", ok=False, error="boom"),
            ],
        )

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
        get_task_service=cast(Any, lambda: _NoopTaskService()),
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


@pytest.mark.asyncio
async def test_worker_moves_scheduled_erasure_task_to_succeeded(tmp_path) -> None:
    """CTRLP-12: the lifecycle worker flips the scheduled erasure task
    running → succeeded as it erases, so the schedule item completes for admins."""
    from datetime import timedelta

    from control_plane_backend.sessions.erasure_tasks import schedule_erasure_task
    from fred_core.common import PostgresStoreConfig
    from fred_core.models.base import Base as CoreBase
    from fred_core.sql import create_async_engine_from_config
    from fred_core.tasks import ErasureReason
    from fred_core.tasks.bus import MemoryEventBus
    from fred_core.tasks.service import TaskService
    from fred_core.tasks.store import TaskStore
    from fred_core.tasks.workflow_control import NoopWorkflowControl

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    task_service = TaskService(
        store=TaskStore(engine), bus=MemoryEventBus(), control=NoopWorkflowControl()
    )

    # A conversation was deferred-deleted: its erasure task is scheduled.
    await schedule_erasure_task(
        task_service,
        session_id="s-2",
        team_id="northbridge",
        user_id="alice",
        title="Q3 pricing",
        due_at=datetime.now(UTC) + timedelta(days=1),
        reason=ErasureReason.user_deleted,
    )

    async def _erase(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            ok=True, stores=[SimpleNamespace(ok=True), SimpleNamespace(ok=True)]
        )

    queue = _FakeQueueStore()
    result = await delete_conversation_and_mark_done(
        event=_event(session_id="s-2", team_id="northbridge", user_id="alice"),
        deps=_deps(queue_store=queue, erase_session=_erase, task_service=task_service),
    )

    assert result.ok is True
    tasks = (await task_service.list_tasks(kind="erasure", team_id="northbridge")).tasks
    assert len(tasks) == 1
    assert tasks[0].state.value == "succeeded"
    assert queue.marked == ["s-2"]


@pytest.mark.asyncio
async def test_repeatedly_failing_erasure_flags_stalled_but_keeps_retrying(
    tmp_path,
) -> None:
    """CTRLP-12 (async#1): a permanently-failing store must not retry *invisibly*
    forever. Erasure never auto-fails (RGPD), but after N attempts the still-running
    task is flagged ``stalled`` so an admin can intervene — and a later good erase
    still closes it succeeded (the retry is never abandoned)."""
    from datetime import timedelta

    from control_plane_backend.sessions.erasure_tasks import (
        ERASURE_STALL_AFTER_ATTEMPTS,
        ERASURE_STEP_STALLED,
        schedule_erasure_task,
    )
    from fred_core.common import PostgresStoreConfig
    from fred_core.models.base import Base as CoreBase
    from fred_core.sql import create_async_engine_from_config
    from fred_core.tasks import ErasureReason
    from fred_core.tasks.bus import MemoryEventBus
    from fred_core.tasks.service import TaskService
    from fred_core.tasks.store import TaskStore
    from fred_core.tasks.workflow_control import NoopWorkflowControl

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    task_service = TaskService(
        store=TaskStore(engine), bus=MemoryEventBus(), control=NoopWorkflowControl()
    )

    await schedule_erasure_task(
        task_service,
        session_id="s-3",
        team_id="northbridge",
        user_id="alice",
        title="stuck",
        due_at=datetime.now(UTC) + timedelta(days=1),
        reason=ErasureReason.user_deleted,
    )

    async def _erase_partial(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            ok=False,
            stores=[
                SimpleNamespace(store="attachments", ok=True, error=None),
                SimpleNamespace(
                    store="runtime_checkpoint", ok=False, error="unresolved runtime"
                ),
            ],
        )

    queue = _FakeQueueStore()
    deps = _deps(
        queue_store=queue, erase_session=_erase_partial, task_service=task_service
    )
    for _ in range(ERASURE_STALL_AFTER_ATTEMPTS):
        result = await delete_conversation_and_mark_done(
            event=_event(session_id="s-3", team_id="northbridge", user_id="alice"),
            deps=deps,
        )
        assert result.ok is False

    task = (await task_service.list_tasks(kind="erasure", team_id="northbridge")).tasks[
        0
    ]
    assert task.state.value == "running"  # never auto-failed (RGPD)
    assert task.step == ERASURE_STEP_STALLED  # but no longer silent
    run = await task_service.get_run(task.task_id)
    assert run is not None
    assert run.detail is not None
    assert run.detail["attempts"] >= ERASURE_STALL_AFTER_ATTEMPTS
    assert queue.marked == []  # still queued → still retrying

    # A later fully-ok erase still closes it succeeded.
    async def _erase_ok(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            ok=True, stores=[SimpleNamespace(ok=True), SimpleNamespace(ok=True)]
        )

    await delete_conversation_and_mark_done(
        event=_event(session_id="s-3", team_id="northbridge", user_id="alice"),
        deps=_deps(
            queue_store=queue, erase_session=_erase_ok, task_service=task_service
        ),
    )
    task = (await task_service.list_tasks(kind="erasure", team_id="northbridge")).tasks[
        0
    ]
    assert task.state.value == "succeeded"
    assert queue.marked == ["s-3"]
