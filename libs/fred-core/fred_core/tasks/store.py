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

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.sql import make_session_factory, use_session
from fred_core.tasks.models import (
    ErasureDetail,
    EvaluationDetail,
    IngestionDetail,
    MigrationDetail,
    TaskEvent,
    TaskLogDetail,
    TaskState,
    TaskSummary,
    TaskTarget,
)
from fred_core.tasks.orm_models import TaskEventLogRow, TaskRunRow

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)

# kind → the Detail model it persists, mirroring TaskEvent's per-kind `detail`
# shape (service.py::_build_terminal_event uses the same kind set for the
# event side). `log` has no persisted-summary detail model; an unrecognised
# future kind falls back to None rather than guessing a shape.
_DETAIL_MODEL_BY_KIND: dict[str, type] = {
    "ingestion": IngestionDetail,
    "evaluation": EvaluationDetail,
    "migration": MigrationDetail,
    "erasure": ErasureDetail,
    "log": TaskLogDetail,
}


def _parse_task_detail(
    kind: str, detail: dict[str, Any] | None
) -> (
    IngestionDetail
    | EvaluationDetail
    | TaskLogDetail
    | MigrationDetail
    | ErasureDetail
    | None
):
    if detail is None:
        return None
    model = _DETAIL_MODEL_BY_KIND.get(kind)
    if model is None:
        return None
    return model(**detail)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskNotFoundError(Exception):
    pass


class TaskStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    def new_task_id(self) -> str:
        return str(uuid.uuid4())

    async def create(
        self,
        *,
        task_id: str,
        kind: str,
        created_by: str | None,
        team_id: str | None = None,
        target: TaskTarget | None = None,
        scheduled_for: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        # Persist `target` at creation so GET /tasks resolves it even before any
        # worker emits an event. Without this the inline indicator on the target's
        # row (e.g. a document) would vanish on reload whenever no worker is running.
        # `scheduled_for` makes a future-dated task (erasure at expiry) show up in
        # the schedule immediately, before any worker touches it.
        row = TaskRunRow(
            task_id=task_id,
            kind=kind,
            state=TaskState.pending,
            seq=0,
            created_by=created_by,
            team_id=team_id,
            target=target.model_dump() if target is not None else None,
            scheduled_for=scheduled_for,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)

    async def record_event(
        self,
        event: TaskEvent,
        session: AsyncSession | None = None,
    ) -> int:
        detail = event.detail.model_dump() if event.detail is not None else None
        async with use_session(self._sessions, session) as s:
            run = await s.get(TaskRunRow, event.task_id)
            if run is None:
                raise TaskNotFoundError(event.task_id)
            next_seq = run.seq + 1
            run.state = event.state
            run.seq = next_seq
            # Preserve last-known progress/step/detail when a sparse event omits them
            # (same rule already applied to target below): a running event that
            # carries no progress means "unchanged", not "reset to indeterminate".
            # Terminal/updating events set these explicitly and still overwrite.
            # `error` is written directly so a later event can *clear* a transient
            # error (e.g. a retry that recovers) rather than let it stick.
            if event.progress is not None:
                run.progress = event.progress
            if event.step is not None:
                run.step = event.step
            if detail is not None:
                run.detail = detail
            run.error = event.error
            run.updated_at = _utcnow()

            target = event.target.model_dump() if event.target is not None else None
            if target is not None:
                run.target = target
            log_row = TaskEventLogRow(
                task_id=event.task_id,
                kind=event.kind,
                seq=next_seq,
                state=event.state,
                progress=event.progress,
                step=event.step,
                detail=detail,
                error=event.error,
                target=target,
                owner=event.owner,
                emitted_at=_utcnow(),
            )
            s.add(log_row)
        return next_seq

    async def get_run(
        self,
        task_id: str,
        session: AsyncSession | None = None,
    ) -> TaskRunRow | None:
        async with use_session(self._sessions, session) as s:
            return await s.get(TaskRunRow, task_id)

    async def set_execution(
        self,
        task_id: str,
        *,
        execution_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Bind a task to the Temporal workflow id that backs it.

        Writes only ``execution_id``; it never touches state/seq/progress, so it
        cannot clobber a concurrent ``record_event`` from the worker.
        """
        async with use_session(self._sessions, session) as s:
            run = await s.get(TaskRunRow, task_id)
            if run is None:
                raise TaskNotFoundError(task_id)
            run.execution_id = execution_id

    async def list_stale_non_terminal(
        self,
        *,
        older_than: datetime,
        limit: int,
        session: AsyncSession | None = None,
    ) -> list[TaskRunRow]:
        """Non-terminal tasks that carry an execution binding and have not been
        updated since ``older_than`` — the reconciliation sweeper's work-list."""
        terminal = [
            TaskState.succeeded.value,
            TaskState.failed.value,
            TaskState.cancelled.value,
        ]
        q = (
            select(TaskRunRow)
            .where(TaskRunRow.state.notin_(terminal))
            .where(TaskRunRow.execution_id.is_not(None))
            .where(TaskRunRow.updated_at < older_than)
            .order_by(TaskRunRow.updated_at)
            .limit(limit)
        )
        async with use_session(self._sessions, session) as s:
            result = await s.execute(q)
            return list(result.scalars().all())

    async def replay_events(
        self,
        task_id: str,
        after_seq: int,
        session: AsyncSession | None = None,
    ) -> list[TaskEvent]:
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(TaskEventLogRow)
                .where(TaskEventLogRow.task_id == task_id)
                .where(TaskEventLogRow.seq > after_seq)
                .order_by(TaskEventLogRow.seq)
            )
            rows = result.scalars().all()

        events: list[TaskEvent] = []
        for row in rows:
            payload = {
                "task_id": row.task_id,
                "kind": row.kind,
                "seq": row.seq,
                "state": row.state,
                "timestamp": row.emitted_at.isoformat(),
                "progress": row.progress,
                "step": row.step,
                "detail": row.detail,
                "error": row.error,
                "target": row.target,
                "owner": row.owner,
            }
            events.append(_EVENT_ADAPTER.validate_python(payload))
        return events

    async def list_tasks(
        self,
        *,
        team_id: str | None = None,
        kind: str | None = None,
        state: str | None = None,
        created_by: str | None = None,
        exclude_terminal: bool = False,
        session: AsyncSession | None = None,
    ) -> list[TaskSummary]:
        _TERMINAL = {TaskState.succeeded, TaskState.failed, TaskState.cancelled}
        q = select(TaskRunRow)
        if team_id is not None:
            q = q.where(TaskRunRow.team_id == team_id)
        if kind is not None:
            q = q.where(TaskRunRow.kind == kind)
        if state is not None:
            q = q.where(TaskRunRow.state == state)
        if created_by is not None:
            q = q.where(TaskRunRow.created_by == created_by)
        if exclude_terminal:
            q = q.where(TaskRunRow.state.notin_([s.value for s in _TERMINAL]))
        q = q.order_by(TaskRunRow.created_at.desc())
        async with use_session(self._sessions, session) as s:
            result = await s.execute(q)
            rows = result.scalars().all()
        return [
            TaskSummary(
                task_id=row.task_id,
                kind=row.kind,
                state=TaskState(row.state),
                progress=row.progress,
                step=row.step,
                error=row.error,
                target=TaskTarget(**row.target) if row.target else None,
                created_by=row.created_by,
                team_id=row.team_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                scheduled_for=row.scheduled_for,
                detail=_parse_task_detail(row.kind, row.detail),
            )
            for row in rows
        ]
