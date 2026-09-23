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
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.sql import make_session_factory, use_session
from fred_core.tasks.models import (
    AgentRunDetail,
    AgentRunTaskEvent,
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
from fred_core.tasks.orm_models import TaskRunColumns, TaskTables

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)

# kind → the Detail model it persists, mirroring TaskEvent's per-kind `detail`
# shape (service.py::_build_terminal_event uses the same kind set for the
# event side). `log` has no persisted-summary detail model; an unrecognised
# future kind falls back to None rather than guessing a shape.
_DETAIL_MODEL_BY_KIND: dict[str, type] = {
    "agent_run": AgentRunDetail,
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
    | AgentRunDetail
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


def _summary_from_run(row: TaskRunColumns) -> TaskSummary:
    return TaskSummary(
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
        acknowledged_at=row.acknowledged_at,
        acknowledged_by=row.acknowledged_by,
    )


class TaskNotFoundError(Exception):
    pass


class TaskAlreadyExistsError(Exception):
    """The caller-supplied durable task id is already registered."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"task {task_id!r} already exists")
        self.task_id = task_id


class TaskStore:
    """Persistence for one backend's task pair.

    *tables* names the concrete `<prefix>task_run`/`<prefix>task_event_log` the
    calling backend owns (#2170) — control-plane and knowledge-flow share the
    `fred` database, so the table names, not the connection, are what keeps one
    backend's `GET /tasks` from returning the other's rows.
    """

    def __init__(self, engine: AsyncEngine, tables: TaskTables) -> None:
        self._sessions = make_session_factory(engine)
        self._run = tables.run
        self._event_log = tables.event_log

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
        values = {
            "task_id": task_id,
            "kind": kind,
            "state": TaskState.pending,
            "seq": 0,
            "created_by": created_by,
            "team_id": team_id,
            "target": target.model_dump() if target is not None else None,
            "scheduled_for": scheduled_for,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        async with use_session(self._sessions, session) as s:
            # Expected duplicate ids must leave the caller's transaction usable.
            # A conflict-safe insert also preserves outer rollback on SQLite.
            dialect = s.get_bind().dialect.name
            if dialect == "postgresql":
                insert_stmt = pg_insert(self._run)
            elif dialect == "sqlite":
                insert_stmt = sqlite_insert(self._run)
            else:  # TaskStore's supported engines are PostgreSQL and local SQLite.
                raise ValueError(f"Unsupported task-store dialect: {dialect}")
            stmt = (
                insert_stmt.values(**values)
                .on_conflict_do_nothing(index_elements=[self._run.task_id])
                .returning(self._run.task_id)
            )
            inserted_task_id = await s.scalar(stmt)
            if inserted_task_id is None:
                raise TaskAlreadyExistsError(task_id)

    async def record_event(
        self,
        event: TaskEvent,
        session: AsyncSession | None = None,
    ) -> tuple[int, TaskState] | None:
        """Atomically append an event; ignore late events for settled ingestion tasks."""
        detail = event.detail.model_dump() if event.detail is not None else None
        target = event.target.model_dump() if event.target is not None else None
        values: dict[str, Any] = {
            "state": event.state,
            "error": event.error,
            "updated_at": _utcnow(),
        }
        # Sparse events preserve known context; an omitted error clears a transient failure.
        for key, value in (
            ("progress", event.progress),
            ("step", event.step),
            ("detail", detail),
            ("target", target),
        ):
            if value is not None:
                values[key] = value
        async with use_session(self._sessions, session) as s:
            if not event.state.is_terminal:
                # A non-terminal event must not pull an agent run out of cancelling.
                values["state"] = case(
                    (
                        and_(
                            self._run.kind == "agent_run",
                            self._run.state == TaskState.cancelling.value,
                        ),
                        TaskState.cancelling.value,
                    ),
                    else_=event.state.value,
                )
            result = await s.execute(
                update(self._run)
                .where(
                    self._run.task_id == event.task_id,
                    or_(
                        self._run.kind != "ingestion",
                        self._run.state.notin_(
                            [state.value for state in TaskState if state.is_terminal]
                        ),
                    ),
                )
                .values(**values, seq=self._run.seq + 1)
                .returning(self._run.seq, self._run.state)
            )
            row = result.one_or_none()
            if row is None:
                if await s.get(self._run, event.task_id) is None:
                    raise TaskNotFoundError(event.task_id)
                return None
            next_seq, stored_state = row
            effective_state = TaskState(stored_state)
            log_row = self._event_log(
                task_id=event.task_id,
                kind=event.kind,
                seq=next_seq,
                state=effective_state,
                progress=event.progress,
                step=event.step,
                detail=detail,
                error=event.error,
                target=target,
                owner=event.owner,
                emitted_at=_utcnow(),
            )
            s.add(log_row)
        return next_seq, effective_state

    async def request_cancellation(
        self, task_id: str
    ) -> tuple[str | None, AgentRunTaskEvent | None]:
        """Persist agent-run cancellation before its execution is available."""
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(self._run).where(self._run.task_id == task_id).with_for_update()
            )
            if run is None:
                raise TaskNotFoundError(task_id)
            state = TaskState(run.state)
            if run.kind != "agent_run" or state.is_terminal:
                return run.execution_id, None
            if state == TaskState.cancelling:
                return run.execution_id, None

            emitted_at = _utcnow()
            next_seq = run.seq + 1
            run.state = TaskState.cancelling
            run.seq = next_seq
            run.updated_at = emitted_at
            session.add(
                self._event_log(
                    task_id=task_id,
                    kind="agent_run",
                    seq=next_seq,
                    state=TaskState.cancelling,
                    progress=None,
                    step=None,
                    detail=None,
                    error=None,
                    target=None,
                    owner=run.created_by,
                    emitted_at=emitted_at,
                )
            )
            event = AgentRunTaskEvent(
                task_id=task_id,
                state=TaskState.cancelling,
                seq=next_seq,
                timestamp=emitted_at,
                owner=run.created_by,
            )
            return run.execution_id, event

    async def fail_agent_run_submission(
        self, task_id: str, message: str
    ) -> AgentRunTaskEvent | None:
        """Atomically fail submission unless cancellation or a terminal event won."""
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(self._run).where(self._run.task_id == task_id).with_for_update()
            )
            if run is None or run.kind != "agent_run":
                return None
            state = TaskState(run.state)
            if state.is_terminal or state == TaskState.cancelling:
                return None

            emitted_at = _utcnow()
            next_seq = run.seq + 1
            detail = AgentRunDetail(reason="execution_failed")
            target = TaskTarget(**run.target) if run.target is not None else None
            run.state = TaskState.failed
            run.seq = next_seq
            run.detail = detail.model_dump()
            run.error = message
            run.updated_at = emitted_at
            session.add(
                self._event_log(
                    task_id=task_id,
                    kind="agent_run",
                    seq=next_seq,
                    state=TaskState.failed,
                    progress=None,
                    step=None,
                    detail=detail.model_dump(),
                    error=message,
                    target=run.target,
                    owner=run.created_by,
                    emitted_at=emitted_at,
                )
            )
            return AgentRunTaskEvent(
                task_id=task_id,
                state=TaskState.failed,
                seq=next_seq,
                timestamp=emitted_at,
                error=message,
                target=target,
                owner=run.created_by,
                detail=detail,
            )

    async def get_run(
        self,
        task_id: str,
        session: AsyncSession | None = None,
    ) -> TaskRunColumns | None:
        async with use_session(self._sessions, session) as s:
            return await s.get(self._run, task_id)

    async def get_task(
        self,
        task_id: str,
        session: AsyncSession | None = None,
    ) -> TaskSummary | None:
        run = await self.get_run(task_id, session=session)
        return _summary_from_run(run) if run is not None else None

    async def set_execution(
        self,
        task_id: str,
        *,
        execution_id: str,
        session: AsyncSession | None = None,
    ) -> TaskRunColumns:
        """Bind a task to the Temporal workflow id that backs it.

        Writes only ``execution_id``; it never touches state/seq/progress, so it
        cannot clobber a concurrent ``record_event`` from the worker.
        """
        async with use_session(self._sessions, session) as s:
            run = await s.scalar(
                select(self._run)
                .where(self._run.task_id == task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if run is None:
                raise TaskNotFoundError(task_id)
            if run.kind == "agent_run" and TaskState(run.state).is_terminal:
                return run
            run.execution_id = execution_id
            await s.flush()
            return run

    async def list_stale_non_terminal(
        self,
        *,
        older_than: datetime,
        limit: int,
        session: AsyncSession | None = None,
    ) -> list[TaskRunColumns]:
        """Non-terminal tasks that carry an execution binding and have not been
        updated since ``older_than`` — the reconciliation sweeper's work-list."""
        terminal = [
            TaskState.succeeded.value,
            TaskState.failed.value,
            TaskState.cancelled.value,
        ]
        q = (
            select(self._run)
            .where(self._run.state.notin_(terminal))
            .where(self._run.execution_id.is_not(None))
            .where(self._run.updated_at < older_than)
            .order_by(self._run.updated_at)
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
                select(self._event_log)
                .where(self._event_log.task_id == task_id)
                .where(self._event_log.seq > after_seq)
                .order_by(self._event_log.seq)
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
        exclude_kind: str | None = None,
        state: str | None = None,
        created_by: str | None = None,
        exclude_terminal: bool = False,
        session: AsyncSession | None = None,
    ) -> list[TaskSummary]:
        _TERMINAL = {TaskState.succeeded, TaskState.failed, TaskState.cancelled}
        q = select(self._run)
        if team_id is not None:
            q = q.where(self._run.team_id == team_id)
        if kind is not None:
            q = q.where(self._run.kind == kind)
        if exclude_kind is not None:
            q = q.where(self._run.kind != exclude_kind)
        if state is not None:
            q = q.where(self._run.state == state)
        if created_by is not None:
            q = q.where(self._run.created_by == created_by)
        if exclude_terminal:
            q = q.where(self._run.state.notin_([s.value for s in _TERMINAL]))
        q = q.order_by(self._run.created_at.desc())
        async with use_session(self._sessions, session) as s:
            result = await s.execute(q)
            rows = result.scalars().all()
        return [_summary_from_run(row) for row in rows]

    async def acknowledge(
        self,
        task_id: str,
        *,
        by: str,
        session: AsyncSession | None = None,
    ) -> TaskRunColumns:
        """Stamp `acknowledged_at`/`acknowledged_by` on a task (rev. 3 §2.10).

        The "needs attention" gate is the CALLER's responsibility
        (`TaskService.acknowledge`, using `needs_attention()`) — this method
        only ever writes the two columns, unconditionally, so it stays a pure
        persistence primitive with no business rule duplicated here.
        """
        async with use_session(self._sessions, session) as s:
            run = await s.get(self._run, task_id)
            if run is None:
                raise TaskNotFoundError(task_id)
            run.acknowledged_at = _utcnow()
            run.acknowledged_by = by
        return run
