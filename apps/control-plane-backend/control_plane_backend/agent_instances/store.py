from __future__ import annotations

import logging
from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, func, select
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
        suspension_reason: str | None = None,
        created_at=None,
        updated_at=None,
        updated_by: str | None = None,
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
        # Platform-forced suspension (#1975, RFC §3.9): None means the instance
        # is not suspended; a non-None value is a `SuspensionReason`. Distinct
        # from `enabled` (the editor's disable toggle).
        self.suspension_reason = suspension_reason
        self.created_at = created_at
        self.updated_at = updated_at
        # Last editing user's uid (#1952); None = never user-edited.
        self.updated_by = updated_by

    @property
    def is_suspended(self) -> bool:
        """True when the platform has suspended this instance (#1975, RFC §3.9)."""

        return self.suspension_reason is not None


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
        suspension_reason=row.suspension_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
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
            suspension_reason=record.suspension_reason,
            created_by=record.created_by,
            updated_by=record.updated_by,
            tuning_json=tuning_json,
            created_at=created_at,
            updated_at=updated_at,
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return await self.get(record.agent_instance_id)  # type: ignore[return-value]

    async def count_all(self, session: AsyncSession | None = None) -> int:
        async with use_session(self._sessions, session) as s:
            result = await s.execute(select(func.count()).select_from(AgentInstanceRow))
            return result.scalar_one()

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

    async def list_all(
        self,
        session: AsyncSession | None = None,
    ) -> list[AgentInstanceRecord]:
        """
        Return every managed agent instance across all teams.

        Used by the capability reconciliation sweep (#1975, RFC §3.9), which
        must re-check every instance's capability availability whenever the
        aggregated pod manifests change. Team-scoped reads use `list_by_team`.
        """
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(AgentInstanceRow))).scalars().all()
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
        enabled: bool | None = None,
        tuning: ManagedAgentTuning | None = None,
        updated_by: str | None = None,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        """Update one instance scoped to team_id. Returns None if not found.

        ``updated_by`` stamps the acting user's uid (#1952); None leaves the
        stored value unchanged (seed/startup saves have no acting user).
        """
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
            if enabled is not None:
                row.enabled = enabled
            if tuning is not None:
                row.tuning_json = tuning.model_dump_json()
            if updated_by is not None:
                row.updated_by = updated_by
            row.updated_at = _utcnow()
        return await self.get(agent_instance_id)

    async def set_suspension(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        *,
        reason: str | None,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        """
        Set or clear the platform-forced suspension reason for one instance
        (#1975, RFC §3.9). ``reason=None`` clears the suspension.

        Why this is a dedicated method (not part of ``update``):
        - suspension is a platform-forced lifecycle state, separate from the
          editor's ``enabled`` toggle and from tuning saves; ``update`` uses
          ``None`` to mean "leave unchanged", which cannot express "clear the
          suspension". This method writes the column directly.
        - it deliberately does NOT touch ``updated_at``: a reconciliation sweep
          flipping the platform state must not look like a user edit.

        Returns the refreshed record, or None if no such instance exists in the
        team.
        """
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
            rows[0].suspension_reason = reason
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
