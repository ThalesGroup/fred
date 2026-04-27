from __future__ import annotations

from datetime import datetime, timezone
import logging

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_instance_models import AgentInstanceRow

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return a stable UTC timestamp for local DB writes.

    Why this helper exists:
    - local SQLite dev setups must not rely on backend-specific SQL functions
      such as `now()` for managed-agent timestamps

    How to use it:
    - call when creating or updating DB-backed managed agent instance rows

    Example:
    - `created_at = _utcnow()`
    """

    return datetime.now(timezone.utc).replace(microsecond=0)


class AgentInstanceRecord:
    """In-memory projection of one DB agent_instance row."""

    def __init__(
        self,
        *,
        agent_instance_id: str,
        team_id: TeamId,
        template_id: str,
        source_runtime_id: str,
        source_agent_id: str,
        display_name: str,
        description: str | None,
        enabled: bool,
        created_by: str | None,
        tuning: ManagedAgentTuning,
        created_at=None,
        updated_at=None,
    ) -> None:
        self.agent_instance_id = agent_instance_id
        self.team_id = team_id
        self.template_id = template_id
        self.source_runtime_id = source_runtime_id
        self.source_agent_id = source_agent_id
        self.display_name = display_name
        self.description = description
        self.enabled = enabled
        self.created_by = created_by
        self.tuning = tuning
        self.created_at = created_at
        self.updated_at = updated_at


def _row_to_record(row: AgentInstanceRow) -> AgentInstanceRecord:
    tuning: ManagedAgentTuning
    if row.tuning_json:
        try:
            tuning = ManagedAgentTuning.model_validate_json(row.tuning_json)
        except Exception:
            logger.warning(
                "Failed to parse tuning_json for instance %s — using defaults",
                row.agent_instance_id,
            )
            tuning = ManagedAgentTuning(
                role=row.display_name, description=row.description or row.display_name
            )
    else:
        tuning = ManagedAgentTuning(
            role=row.display_name, description=row.description or row.display_name
        )
    return AgentInstanceRecord(
        agent_instance_id=row.agent_instance_id,
        team_id=TeamId(row.team_id),
        template_id=row.template_id,
        source_runtime_id=row.source_runtime_id,
        source_agent_id=row.source_agent_id,
        display_name=row.display_name,
        description=row.description,
        enabled=row.enabled,
        created_by=row.created_by,
        tuning=tuning,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentInstanceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        record: AgentInstanceRecord,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord:
        created_at = record.created_at or _utcnow()
        updated_at = record.updated_at or created_at
        tuning_json = record.tuning.model_dump_json()
        row = AgentInstanceRow(
            agent_instance_id=record.agent_instance_id,
            team_id=str(record.team_id),
            template_id=record.template_id,
            source_runtime_id=record.source_runtime_id,
            source_agent_id=record.source_agent_id,
            display_name=record.display_name,
            description=record.description,
            enabled=record.enabled,
            created_by=record.created_by,
            tuning_json=tuning_json,
            created_at=created_at,
            updated_at=updated_at,
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return await self.get(record.agent_instance_id)  # type: ignore[return-value]

    async def list_by_team(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> list[AgentInstanceRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(AgentInstanceRow).where(
                            AgentInstanceRow.team_id == str(team_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [_row_to_record(row) for row in rows]

    async def get(
        self,
        agent_instance_id: str,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(AgentInstanceRow, agent_instance_id)
        if row is None:
            return None
        return _row_to_record(row)

    async def get_for_team(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(AgentInstanceRow).where(
                            AgentInstanceRow.agent_instance_id == agent_instance_id,
                            AgentInstanceRow.team_id == str(team_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            return None
        return _row_to_record(rows[0])

    async def update(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        *,
        display_name: str | None = None,
        description: str | None = None,
        tuning: ManagedAgentTuning | None = None,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        """Update one instance scoped to team_id. Returns None if not found."""
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(AgentInstanceRow).where(
                            AgentInstanceRow.agent_instance_id == agent_instance_id,
                            AgentInstanceRow.team_id == str(team_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                return None
            row = rows[0]
            if display_name is not None:
                row.display_name = display_name
            if description is not None:
                row.description = description
            if tuning is not None:
                row.tuning_json = tuning.model_dump_json()
            row.updated_at = _utcnow()
        return await self.get(agent_instance_id)

    async def delete(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> bool:
        """Delete one instance scoped to team_id. Returns True if a row was removed."""
        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(AgentInstanceRow).where(
                    AgentInstanceRow.agent_instance_id == agent_instance_id,
                    AgentInstanceRow.team_id == str(team_id),
                )
            )
        return result.rowcount > 0
