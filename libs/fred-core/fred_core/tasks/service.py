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

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncEngine

from fred_core.scheduler import SchedulerBackend, TemporalClientProvider
from fred_core.tasks.bus import IEventBus, MemoryEventBus, PostgresEventBus
from fred_core.tasks.models import (
    IngestionTaskEvent,
    MigrationTaskEvent,
    StartTaskRequest,
    StartTaskResponse,
    TaskEvent,
    TaskListResponse,
    TaskLogDetail,
    TaskLogEvent,
    TaskState,
    TaskTarget,
)
from fred_core.tasks.orm_models import TaskRunRow
from fred_core.tasks.store import TaskNotFoundError, TaskStore
from fred_core.tasks.workflow_control import (
    ExecutionStatus,
    NoopWorkflowControl,
    TemporalWorkflowControl,
    WorkflowControl,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskService:
    def __init__(
        self,
        store: TaskStore,
        bus: IEventBus,
        control: WorkflowControl,
    ) -> None:
        self.store = store
        self.bus = bus
        self._control = control

    @classmethod
    def build(
        cls,
        engine: AsyncEngine,
        backend: SchedulerBackend,
        temporal_client_provider: TemporalClientProvider | None = None,
        postgres_dsn: str | None = None,
    ) -> "TaskService":
        store = TaskStore(engine)
        if backend == SchedulerBackend.TEMPORAL:
            if temporal_client_provider is None:
                raise ValueError(
                    "temporal_client_provider required for TEMPORAL backend"
                )
            bus: IEventBus = PostgresEventBus(postgres_dsn or "")
            control: WorkflowControl = TemporalWorkflowControl(temporal_client_provider)
        else:
            bus = MemoryEventBus()
            control = NoopWorkflowControl()
        return cls(store=store, bus=bus, control=control)

    async def start(
        self,
        request: StartTaskRequest,
        created_by: str | None,
        team_id: str | None = None,
        target: TaskTarget | None = None,
    ) -> StartTaskResponse:
        task_id = self.store.new_task_id()
        await self.store.create(
            task_id=task_id,
            kind=request.kind,
            created_by=created_by,
            team_id=team_id,
            target=target,
        )
        logger.info("[TaskService] starting task_id=%s kind=%s", task_id, request.kind)
        return StartTaskResponse(task_id=task_id)

    async def cancel(self, task_id: str) -> None:
        run = await self.store.get_run(task_id)
        if run is None:
            raise TaskNotFoundError(task_id)
        if run.execution_id:
            await self._control.cancel(run.execution_id)

    async def get_run(self, task_id: str) -> TaskRunRow | None:
        return await self.store.get_run(task_id)

    async def replay(self, task_id: str, after_seq: int) -> list[TaskEvent]:
        return await self.store.replay_events(task_id, after_seq)

    async def record(self, event: TaskEvent) -> None:
        assigned_seq = await self.store.record_event(event)
        await self.bus.publish(event.model_copy(update={"seq": assigned_seq}))

    async def list_tasks(
        self,
        *,
        team_id: str | None = None,
        kind: str | None = None,
        state: str | None = None,
        created_by: str | None = None,
        exclude_terminal: bool = False,
    ) -> TaskListResponse:
        summaries = await self.store.list_tasks(
            team_id=team_id,
            kind=kind,
            state=state,
            created_by=created_by,
            exclude_terminal=exclude_terminal,
        )
        return TaskListResponse(tasks=summaries)

    # ── execution binding + reconciliation ───────────────────────────────────

    async def bind_execution(self, task_id: str, *, execution_id: str) -> None:
        """Record the Temporal workflow id that backs a task, so it can be reconciled
        against that workflow later. The submitter calls this right after starting the
        workflow. Writes only ``execution_id`` → safe against concurrent worker writes."""
        await self.store.set_execution(task_id, execution_id=execution_id)

    async def fail_task(self, task_id: str, message: str) -> bool:
        """Drive a non-terminal task to ``failed`` with a message (durable + SSE).

        For the submitter to call when work could not be scheduled at all (e.g. the
        executor was unreachable), so the task never stays pending with no execution
        behind it. No-op if the task is gone or already terminal.
        """
        run = await self.store.get_run(task_id)
        if run is None or TaskState(run.state).is_terminal:
            return False
        await self.record(self._build_failed_event(run, message))
        return True

    @staticmethod
    def _reconciled_terminal(
        status: ExecutionStatus | None,
    ) -> tuple[TaskState, str] | None:
        """Decide the terminal outcome for a still-pending task from its executor status.

        Returns ``(state, message)`` to record, or ``None`` to leave the task as-is.
        Only *reflects* the executor's verdict — no fred-side timeouts/retries.
        A user/admin cancellation maps to ``cancelled`` (not ``failed``) so it never
        reads as an error; everything else non-success maps to ``failed``.
        """
        if status is None or status == ExecutionStatus.running:
            return None  # unknown/unreachable or still running → never false-fail
        if status.is_cancellation:
            return (TaskState.cancelled, "Execution canceled")
        if status.is_terminal_failure:
            return (TaskState.failed, f"Execution {status.value}")
        if status == ExecutionStatus.completed:
            return (TaskState.failed, "Execution finished without completing the task")
        return None

    def _build_terminal_event(
        self, run: TaskRunRow, state: TaskState, message: str
    ) -> TaskEvent:
        target = TaskTarget(**run.target) if run.target else None
        # cancellations are an expected outcome, not an error → log at info level.
        level = "error" if state == TaskState.failed else "info"
        if run.kind == "log":
            return TaskLogEvent(
                task_id=run.task_id,
                state=state,
                seq=0,  # reassigned by record()
                timestamp=_utcnow(),
                error=message,
                target=target,
                owner=run.created_by,
                detail=TaskLogDetail(level=level, message=message),
            )
        if run.kind == "migration":
            return MigrationTaskEvent(
                task_id=run.task_id,
                state=state,
                seq=0,  # reassigned by record()
                timestamp=_utcnow(),
                error=message,
                target=target,
                owner=run.created_by,
            )
        # ingestion (and any future progress-counter kind) — detail is optional
        return IngestionTaskEvent(
            task_id=run.task_id,
            state=state,
            seq=0,  # reassigned by record()
            timestamp=_utcnow(),
            error=message,
            target=target,
            owner=run.created_by,
        )

    def _build_failed_event(self, run: TaskRunRow, message: str) -> TaskEvent:
        """Build a ``failed`` terminal event (thin wrapper over the general builder)."""
        return self._build_terminal_event(run, TaskState.failed, message)

    async def _emit_terminal_if_diverged(
        self, task_id: str, status: ExecutionStatus | None
    ) -> bool:
        decision = self._reconciled_terminal(status)
        if decision is None:
            return False
        state, message = decision
        # Re-fetch for a fresh terminal check: the worker may have finished the task
        # between listing it and here. Never overwrite a terminal state.
        run = await self.store.get_run(task_id)
        if run is None or TaskState(run.state).is_terminal:
            return False
        await self.record(self._build_terminal_event(run, state, message))
        logger.info(
            "[TaskService] reconciled task_id=%s → %s (%s)",
            task_id,
            state.value,
            message,
        )
        return True

    async def reconcile_task(self, task_id: str) -> bool:
        """Reconcile one task against its executor. Returns True if it was driven terminal.

        For a non-terminal task with an execution binding, ask the executor for the
        real status and, if the execution is gone/failed/timed-out/cancelled (or finished
        without completing the task), drive the task terminal via a normal TaskEvent —
        so the durable log, SSE replay, and live bus all update through the usual path.
        A user-requested cancellation lands as ``cancelled``, not ``failed``.
        """
        run = await self.store.get_run(task_id)
        if run is None or TaskState(run.state).is_terminal or not run.execution_id:
            return False
        status = await self._control.get_status(run.execution_id)
        return await self._emit_terminal_if_diverged(task_id, status)

    async def reconcile_stale(self, *, grace_seconds: float, limit: int = 100) -> int:
        """Sweep non-terminal tasks not updated for ``grace_seconds`` and reconcile
        each against its executor. Returns the number driven terminal (failed or
        cancelled).

        One executor status query per distinct ``execution_id`` (many per-file tasks
        can share one parent workflow), so a flooded backlog costs few describe calls.
        """
        cutoff = _utcnow() - timedelta(seconds=grace_seconds)
        runs = await self.store.list_stale_non_terminal(older_than=cutoff, limit=limit)
        status_cache: dict[str, ExecutionStatus | None] = {}
        reconciled_count = 0
        for run in runs:
            execution_id = run.execution_id
            if execution_id is None:
                continue
            if execution_id not in status_cache:
                try:
                    status_cache[execution_id] = await self._control.get_status(
                        execution_id
                    )
                except Exception:
                    logger.warning(
                        "[TaskService] get_status failed for execution_id=%s",
                        execution_id,
                        exc_info=True,
                    )
                    status_cache[execution_id] = None
            try:
                if await self._emit_terminal_if_diverged(
                    run.task_id, status_cache[execution_id]
                ):
                    reconciled_count += 1
            except Exception:
                logger.warning(
                    "[TaskService] reconcile failed for task_id=%s",
                    run.task_id,
                    exc_info=True,
                )
        return reconciled_count


async def run_reconcile_sweeper(
    service: TaskService,
    *,
    interval_seconds: float = 120.0,
    grace_seconds: float = 300.0,
    limit: int = 200,
) -> None:
    """Periodically reconcile stale non-terminal tasks against their executors.

    The backstop for tasks no client is watching (read-time reconcile on the SSE
    subscribe path covers watched ones). Start it as a background task in the app
    lifespan and cancel it on shutdown. It only ever reflects the executor's verdict.
    """
    while True:
        try:
            failed = await service.reconcile_stale(
                grace_seconds=grace_seconds, limit=limit
            )
            if failed:
                logger.info(
                    "[reconcile-sweeper] drove %d abandoned task(s) to a terminal state",
                    failed,
                )
        except Exception:
            logger.warning("[reconcile-sweeper] sweep iteration failed", exc_info=True)
        await asyncio.sleep(interval_seconds)
