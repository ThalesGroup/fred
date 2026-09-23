from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fred_core.sql import make_session_factory, use_session
from fred_core.tasks.agent_run import AgentRunAdmissionRecord
from fred_core.tasks.models import TaskState
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.agent_run_task_models import (
    AgentRunAdmissionRow,
    AgentRunScheduleRow,
)
from control_plane_backend.models.task_models import CpTaskRunRow


class AgentRunTaskStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)
        self._occurrence_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._occurrence_locks_guard = asyncio.Lock()

    async def create(
        self,
        *,
        task_id: str,
        workflow_id: str,
        occurrence_key: str | None = None,
        runtime_client_id: str,
        runtime_subject: str,
        record: AgentRunAdmissionRecord,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as active_session:
            active_session.add(
                AgentRunAdmissionRow(
                    task_id=task_id,
                    workflow_id=workflow_id,
                    occurrence_key=occurrence_key,
                    person_id=record.person_id,
                    runtime_client_id=runtime_client_id,
                    runtime_subject=runtime_subject,
                    payload_json=record.model_dump_json(),
                )
            )
            await active_session.flush()

    async def get(self, task_id: str) -> AgentRunAdmissionRow | None:
        async with self._sessions() as session:
            return await session.get(AgentRunAdmissionRow, task_id)

    async def get_by_workflow(self, workflow_id: str) -> AgentRunAdmissionRow | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(AgentRunAdmissionRow).where(
                    AgentRunAdmissionRow.workflow_id == workflow_id
                )
            )

    async def get_by_occurrence(
        self, occurrence_key: str, *, session: AsyncSession | None = None
    ) -> AgentRunAdmissionRow | None:
        async with use_session(self._sessions, session) as active_session:
            return await active_session.scalar(
                select(AgentRunAdmissionRow).where(
                    AgentRunAdmissionRow.occurrence_key == occurrence_key
                )
            )

    @asynccontextmanager
    async def lock_occurrence(self, occurrence_key: str) -> AsyncIterator[AsyncSession]:
        async with self._occurrence_locks_guard:
            local_lock, users = self._occurrence_locks.get(
                occurrence_key, (asyncio.Lock(), 0)
            )
            self._occurrence_locks[occurrence_key] = (local_lock, users + 1)
        try:
            async with local_lock:
                async with self._sessions.begin() as session:
                    bind = session.get_bind()
                    if bind.dialect.name == "postgresql":
                        await session.execute(
                            text(
                                "SELECT pg_advisory_xact_lock("
                                "hashtextextended(:key, 0))"
                            ),
                            {"key": occurrence_key},
                        )
                    yield session
        finally:
            async with self._occurrence_locks_guard:
                current_lock, users = self._occurrence_locks[occurrence_key]
                if users == 1:
                    del self._occurrence_locks[occurrence_key]
                else:
                    self._occurrence_locks[occurrence_key] = (
                        current_lock,
                        users - 1,
                    )

    async def is_matching_task(
        self,
        *,
        task_id: str,
        person_id: str,
        team_id: str,
        session: AsyncSession | None = None,
    ) -> bool:
        async with use_session(self._sessions, session) as active_session:
            row = await active_session.get(CpTaskRunRow, task_id)
            return bool(
                row is not None
                and row.kind == "agent_run"
                and row.created_by == person_id
                and row.team_id == team_id
                and not TaskState(row.state).is_terminal
            )

    async def delete_task_if_unadmitted(self, task_id: str) -> bool:
        async with self._sessions.begin() as session:
            admission = await session.get(AgentRunAdmissionRow, task_id)
            if admission is not None:
                return False
            result = await session.execute(
                delete(CpTaskRunRow).where(CpTaskRunRow.task_id == task_id)
            )
            return bool(getattr(result, "rowcount", 0))

    async def create_schedule(
        self, row: AgentRunScheduleRow, *, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as active_session:
            active_session.add(row)
            await active_session.flush()

    async def get_schedule(self, schedule_id: str) -> AgentRunScheduleRow | None:
        async with self._sessions() as session:
            return await session.get(AgentRunScheduleRow, schedule_id)

    async def list_schedules(self, team_id: str) -> list[AgentRunScheduleRow]:
        async with self._sessions() as session:
            return list(
                await session.scalars(
                    select(AgentRunScheduleRow)
                    .where(AgentRunScheduleRow.team_id == team_id)
                    .order_by(AgentRunScheduleRow.created_at)
                )
            )

    async def list_schedules_by_creator(
        self, person_id: str, *, session: AsyncSession | None = None
    ) -> list[AgentRunScheduleRow]:
        async with use_session(self._sessions, session) as active_session:
            return list(
                await active_session.scalars(
                    select(AgentRunScheduleRow).where(
                        AgentRunScheduleRow.created_by == person_id
                    )
                )
            )

    async def delete_schedule(
        self, schedule_id: str, *, session: AsyncSession | None = None
    ) -> bool:
        async with use_session(self._sessions, session) as active_session:
            result = await active_session.execute(
                delete(AgentRunScheduleRow).where(
                    AgentRunScheduleRow.schedule_id == schedule_id
                )
            )
            return bool(getattr(result, "rowcount", 0))

    async def purge_person(
        self, person_id: str, *, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as active_session:
            await active_session.execute(
                delete(AgentRunAdmissionRow).where(
                    AgentRunAdmissionRow.person_id == person_id
                )
            )
            await active_session.execute(
                delete(AgentRunScheduleRow).where(
                    AgentRunScheduleRow.created_by == person_id
                )
            )
