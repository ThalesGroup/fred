from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from fred_core.sql import advisory_lock_key, make_session_factory, use_session
from sqlalchemy import delete, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.agent_run_models import AgentRunRow

AGENT_RUN_LIFECYCLE_LOCK = "agent_run_registration_and_account_deletion"


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run_id: str
    person_id: str
    team_id: str | None
    agent_id: str
    agent_instance_id: str | None
    reporter_client_id: str
    reporter_subject: str
    origin_caller: str | None
    mode: str
    started_at: datetime
    run_ceiling_seconds: float
    outcome: str | None = None
    stop_reason: str | None = None
    ended_at: datetime | None = None


def _record(row: AgentRunRow) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=row.run_id,
        person_id=row.person_id,
        team_id=row.team_id,
        agent_id=row.agent_id,
        agent_instance_id=row.agent_instance_id,
        reporter_client_id=row.reporter_client_id,
        reporter_subject=row.reporter_subject,
        origin_caller=row.origin_caller,
        mode=row.mode,
        started_at=row.started_at,
        run_ceiling_seconds=row.run_ceiling_seconds,
        outcome=row.outcome,
        stop_reason=row.stop_reason,
        ended_at=row.ended_at,
    )


class AgentRunStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    async def _lock(self, session) -> None:
        if self._engine.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": advisory_lock_key(AGENT_RUN_LIFECYCLE_LOCK)},
            )

    async def create(
        self,
        record: AgentRunRecord,
        *,
        acquire_lock: bool = True,
        session: AsyncSession | None = None,
    ) -> AgentRunRecord:
        async with use_session(self._sessions, session) as active_session:
            if acquire_lock:
                await self._lock(active_session)
            existing = await active_session.get(AgentRunRow, record.run_id)
            if existing is not None:
                raise ValueError("agent_run_exists")
            active_session.add(AgentRunRow(**asdict(record)))
            await active_session.flush()
        return record

    async def get(self, run_id: str) -> AgentRunRecord | None:
        async with self._sessions() as session:
            row = await session.get(AgentRunRow, run_id)
            return _record(row) if row is not None else None

    async def end(
        self, *, run_id: str, outcome: str, reason: str | None
    ) -> AgentRunRecord | None:
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(AgentRunRow)
                .where(AgentRunRow.run_id == run_id)
                .with_for_update()
            )
            if row is None:
                return None
            if row.outcome is not None:
                if row.outcome != outcome or row.stop_reason != reason:
                    raise ValueError("agent_run_terminal_conflict")
                return _record(row)
            row.outcome = outcome
            row.stop_reason = reason
            row.ended_at = datetime.now(timezone.utc)
            await session.flush()
            return _record(row)

    async def purge_person(
        self,
        person_id: str,
        *,
        acquire_lock: bool = True,
        session: AsyncSession | None = None,
    ) -> int:
        async with use_session(self._sessions, session) as active_session:
            if acquire_lock:
                await self._lock(active_session)
            result = await active_session.execute(
                delete(AgentRunRow).where(AgentRunRow.person_id == person_id)
            )
            return int(result.rowcount or 0) if isinstance(result, CursorResult) else 0
