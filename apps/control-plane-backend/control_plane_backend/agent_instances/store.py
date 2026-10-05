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

import json
import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.agent_instances.names import is_agent_name_violation
from control_plane_backend.agent_marketplace.store import (
    RemovalReason,
    RemovedEntry,
    emit_unpublished,
    remove_published_entries,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.routing_policy_models import TeamRoutingPolicyRow
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from control_plane_backend.routing_policy.schemas import ModelDisabledForTeamError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamAgentsDeletion:
    """What a team deletion removed: its agents, and the entries they had published."""

    agent_instance_ids: list[str]
    unpublished: list[RemovedEntry]


class AgentNameAlreadyExistsError(Exception):
    """Another agent of the team already has this name (case and spaces ignored)."""

    def __init__(self, team_id: TeamId, display_name: str) -> None:
        super().__init__(
            f"Agent name {display_name!r} already exists in team {team_id!r}."
        )
        self.team_id = team_id
        self.display_name = display_name


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
        suspension_detail: str | None = None,
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
        # Failure message carried with `capability_pending`; None otherwise.
        self.suspension_detail = suspension_detail
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
        suspension_detail=row.suspension_detail,
        created_at=row.created_at,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


async def clear_recommended_chat_profiles(
    session: AsyncSession,
    *,
    profile_ids: Collection[str],
    team_id: TeamId | None,
) -> list[str]:
    """Clear `recommended_chat_profile_id` on instances naming one of
    `profile_ids`, inside the caller's transaction. Edits the stored JSON in
    place so unknown keys survive, and leaves `updated_at` alone: this is a
    platform side effect, not a user edit. Returns the cleared instance ids."""

    # Row locks serialize this with a concurrent agent save (see `update`).
    statement = select(AgentInstanceRow).with_for_update()
    if team_id is not None:
        statement = statement.where(AgentInstanceRow.team_id == str(team_id))
    cleared: list[str] = []
    for row in (await session.execute(statement)).scalars().all():
        try:
            tuning = json.loads(row.tuning_json) if row.tuning_json else None
        except ValueError:
            continue
        if not isinstance(tuning, dict):
            continue
        if tuning.get("recommended_chat_profile_id") not in profile_ids:
            continue
        tuning["recommended_chat_profile_id"] = None
        row.tuning_json = json.dumps(tuning)
        cleared.append(row.agent_instance_id)
    return cleared


async def _require_model_enabled_for_team(
    session: AsyncSession, *, team_id: TeamId, capability_id: str, profile_id: str
) -> None:
    """Re-check a recommendation against the team policy inside the write
    transaction. The shared lock makes a concurrent disable wait for this
    write, and its clear then sees the new recommendation."""

    disabled_json = (
        await session.execute(
            select(TeamRoutingPolicyRow.disabled_model_ids_json)
            .where(TeamRoutingPolicyRow.team_id == str(team_id))
            .with_for_update(read=True)
        )
    ).scalar_one_or_none()
    try:
        disabled = json.loads(disabled_json or "[]")
    except ValueError:
        disabled = []
    if isinstance(disabled, list) and capability_id in disabled:
        raise ModelDisabledForTeamError(team_id=team_id, profile_ids=[profile_id])


class AgentInstanceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        record: AgentInstanceRecord,
        session: AsyncSession | None = None,
        *,
        recommended_capability_id: str | None = None,
    ) -> AgentInstanceRecord:
        """`recommended_capability_id`, when set, is the model of the record's
        recommendation, re-checked against the team policy in this write."""
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
            suspension_detail=record.suspension_detail,
            created_by=record.created_by,
            updated_by=record.updated_by,
            tuning_json=tuning_json,
            created_at=created_at,
            updated_at=updated_at,
        )
        try:
            async with use_session(self._sessions, session) as s:
                recommended = record.tuning.recommended_chat_profile_id
                if recommended_capability_id is not None and recommended is not None:
                    await _require_model_enabled_for_team(
                        s,
                        team_id=record.team_id,
                        capability_id=recommended_capability_id,
                        profile_id=recommended,
                    )
                s.add(row)
                # Flushed here so a caller-owned session still gets the typed error.
                await s.flush()
        except IntegrityError as exc:
            if is_agent_name_violation(exc):
                raise AgentNameAlreadyExistsError(
                    record.team_id, record.display_name
                ) from exc
            raise
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
        recommended_capability_id: str | None = None,
        keep_stored_recommendation: bool = False,
    ) -> AgentInstanceRecord | None:
        """Update one instance scoped to team_id. Returns None if not found.

        ``updated_by`` stamps the acting user's uid (#1952); None leaves the
        stored value unchanged (seed/startup saves have no acting user).
        ``recommended_capability_id`` re-checks the new tuning's recommendation
        against the team policy in this transaction (policy lock first, the
        same order as a policy write). ``keep_stored_recommendation`` keeps
        the row's current recommendation, which a policy write may have
        cleared since ``tuning`` was loaded.
        """
        try:
            async with use_session(self._sessions, session) as s:
                recommended = tuning.recommended_chat_profile_id if tuning else None
                if recommended_capability_id is not None and recommended is not None:
                    await _require_model_enabled_for_team(
                        s,
                        team_id=team_id,
                        capability_id=recommended_capability_id,
                        profile_id=recommended,
                    )
                rows = (
                    (
                        await s.execute(
                            select(AgentInstanceRow)
                            .where(
                                AgentInstanceRow.agent_instance_id == agent_instance_id,
                                AgentInstanceRow.team_id == str(team_id),
                            )
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .all()
                )
                if not rows:
                    return None
                row = rows[0]
                if tuning is not None and keep_stored_recommendation:
                    tuning = tuning.model_copy(
                        update={
                            "recommended_chat_profile_id": _row_to_record(
                                row
                            ).tuning.recommended_chat_profile_id
                        }
                    )
                deactivated = enabled is False and row.enabled
                changes = {
                    "display_name": display_name,
                    "description": description,
                    "enabled": enabled,
                    "tuning_json": tuning.model_dump_json()
                    if tuning is not None
                    else None,
                }
                changed = False
                for column, value in changes.items():
                    if value is not None and getattr(row, column) != value:
                        setattr(row, column, value)
                        changed = True
                # The marketplace compares `updated_at` to the published snapshot:
                # a no-op save keeps it, a real one stamps it to the microsecond.
                if changed:
                    if updated_by is not None:
                        row.updated_by = updated_by
                    row.updated_at = utcnow()
                removed: list[RemovedEntry] = (
                    await remove_published_entries(
                        s,
                        reason=RemovalReason.DEACTIVATED,
                        agent_instance_ids=[agent_instance_id],
                    )
                    if deactivated
                    else []
                )
                await s.flush()
        except IntegrityError as exc:
            if display_name is not None and is_agent_name_violation(exc):
                raise AgentNameAlreadyExistsError(team_id, display_name) from exc
            raise
        emit_unpublished(removed, actor_uid=updated_by)
        return await self.get(agent_instance_id)

    async def set_suspension(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        *,
        reason: str | None,
        detail: str | None = None,
        session: AsyncSession | None = None,
    ) -> AgentInstanceRecord | None:
        """
        Set or clear the platform-forced suspension reason for one instance
        (#1975, RFC §3.9). ``reason=None`` clears the suspension. ``detail``
        is written with every call, so a reason change drops a stale message.

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
            rows[0].suspension_detail = detail
            removed = (
                await remove_published_entries(
                    s,
                    reason=RemovalReason.SUSPENDED,
                    agent_instance_ids=[agent_instance_id],
                )
                if reason is not None
                else []
            )
        emit_unpublished(removed)
        return await self.get(agent_instance_id)

    async def delete(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
        actor_uid: str | None = None,
    ) -> bool:
        """Delete one instance scoped to team_id. Returns True if a row was removed.
        A published entry is taken down first and audited once the deletion is done."""
        unpublished: list[RemovedEntry] = []
        async with use_session(self._sessions, session) as s:
            instance = await s.scalar(
                select(AgentInstanceRow)
                .where(
                    AgentInstanceRow.agent_instance_id == agent_instance_id,
                    AgentInstanceRow.team_id == str(team_id),
                )
                .with_for_update()
            )
            if instance is None:
                return False
            unpublished = await remove_published_entries(
                s, reason=RemovalReason.DELETED, agent_instance_ids=[agent_instance_id]
            )
            # Keep the last name without making deletion look like chat activity.
            await s.execute(
                update(SessionMetadataRow)
                .where(
                    SessionMetadataRow.agent_instance_id == agent_instance_id,
                    SessionMetadataRow.team_id == str(team_id),
                )
                .values(
                    agent_display_name=instance.display_name,
                    updated_at=SessionMetadataRow.updated_at,
                )
            )
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(AgentInstanceRow).where(
                    AgentInstanceRow.agent_instance_id == agent_instance_id,
                    AgentInstanceRow.team_id == str(team_id),
                )
            )
        emit_unpublished(unpublished, actor_uid=actor_uid)
        return result.rowcount > 0

    async def delete_by_team(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> TeamAgentsDeletion:
        """Delete every instance of a team (team deletion); marketplace rows cascade."""
        async with use_session(self._sessions, session) as s:
            team_agents = select(AgentInstanceRow.agent_instance_id).where(
                AgentInstanceRow.team_id == str(team_id)
            )
            agent_ids = list((await s.scalars(team_agents.with_for_update())).all())
            if not agent_ids:
                return TeamAgentsDeletion([], [])
            # Taken down before the cascade so the caller can audit what was published.
            unpublished = await remove_published_entries(
                s, reason=RemovalReason.TEAM_DELETED, team_ids=[str(team_id)]
            )
            # Keep each agent's last name on its sessions, as a single delete does.
            await s.execute(
                update(SessionMetadataRow)
                .where(
                    SessionMetadataRow.team_id == str(team_id),
                    SessionMetadataRow.agent_instance_id.in_(team_agents),
                )
                .values(
                    agent_display_name=select(AgentInstanceRow.display_name)
                    .where(
                        AgentInstanceRow.agent_instance_id
                        == SessionMetadataRow.agent_instance_id,
                        AgentInstanceRow.team_id == str(team_id),
                    )
                    .scalar_subquery(),
                    updated_at=SessionMetadataRow.updated_at,
                )
            )
            await s.execute(
                delete(AgentInstanceRow).where(AgentInstanceRow.team_id == str(team_id))
            )
        return TeamAgentsDeletion(agent_ids, unpublished)
