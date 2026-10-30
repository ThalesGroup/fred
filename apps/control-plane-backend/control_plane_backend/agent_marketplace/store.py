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

"""Storage of marketplace entries, their files, likes and imports. No
authorization here; that is `agent_marketplace/service.py`'s job."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.sql import make_session_factory, use_session
from fred_core.sql.base_sql import advisory_lock_key
from fred_core.teams.metadata_store import TeamVisibility
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import JSON, case, cast, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.agent_marketplace_models import (
    AgentMarketplaceEntryFileRow,
    AgentMarketplaceEntryRow,
    AgentMarketplaceImportRow,
    AgentMarketplaceLikeRow,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.marketplace_settings_models import (
    DEFAULT_AGENTS_PUBLISH_QUOTA,
    DEFAULT_AGENTS_PUBLISHING_ENABLED,
    PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID,
    PlatformMarketplaceSettingsRow,
)


class EntryState(str, Enum):
    PUBLISHED = "published"
    # Shown on the team card until an editor or the team admin hides it.
    REMOVED = "removed"
    DISMISSED = "dismissed"


class RemovalReason(str, Enum):
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"
    SWITCH_OFF = "switch_off"
    TEAM_PRIVATE = "team_private"
    # Audit only: the entry cascades with its agent, or with the team's agents.
    DELETED = "deleted"
    TEAM_DELETED = "team_deleted"
    REMOVED_BY_PLATFORM_ADMIN = "removed_by_platform_admin"
    # A removal by an editor or the team admin leaves no Removed state.
    REMOVED_BY_TEAM = "removed_by_team"


class MarketplaceVersionConflict(Exception):
    """The caller's `expected_version` is not the entry's current version."""


class MarketplaceQuotaReached(Exception):
    """A new publication would exceed the team's agents quota."""

    def __init__(self, quota: int) -> None:
        super().__init__(quota)
        self.quota = quota


class MarketplacePublishingClosed(Exception):
    """The team's switch went off, or the team went private, before the write."""

    def __init__(self, team_private: bool) -> None:
        super().__init__(team_private)
        self.team_private = team_private


class MarketplaceAgentInactive(Exception):
    """The agent was deactivated, suspended or deleted before the write."""


class MarketplaceEntryNotFound(Exception):
    """No entry in the state the operation needs."""


@dataclass(frozen=True)
class SnapshotFile:
    capability_id: str
    asset_key: str
    filename: str
    content: bytes


@dataclass(frozen=True)
class Snapshot:
    """What a publication stores: the agent as a copy to another team carries it."""

    template_id: str
    source_runtime_id: str
    source_agent_id: str
    display_name: str
    description: str | None
    tuning_json: str
    capabilities: list[dict[str, Any]]
    source_updated_at: datetime
    files: list[SnapshotFile] = field(default_factory=list)


@dataclass(frozen=True)
class MarketplaceEntry:
    entry_id: str
    agent_instance_id: str
    team_id: TeamId
    state: EntryState
    removed_reason: str | None
    removed_message: str | None
    removed_at: datetime | None
    template_id: str
    source_runtime_id: str
    source_agent_id: str
    display_name: str
    description: str | None
    tuning_json: str
    capabilities: list[dict[str, Any]]
    version: int
    first_published_at: datetime
    published_at: datetime
    snapshot_source_updated_at: datetime
    published_by: str | None = None


@dataclass(frozen=True)
class ListedEntry:
    """A published entry as the listing shows it, without the snapshot body."""

    entry_id: str
    team_id: TeamId
    team_name: str | None
    template_id: str
    display_name: str
    description: str | None
    role: str
    version: int
    first_published_at: datetime
    published_at: datetime


@dataclass(frozen=True)
class RemovedEntry:
    entry_id: str
    agent_instance_id: str
    team_id: TeamId
    reason: RemovalReason
    state: EntryState = EntryState.REMOVED
    display_name: str = ""
    published_by: str | None = None
    removed_at: datetime | None = None
    message: str | None = None
    team_name: str | None = None


@dataclass(frozen=True)
class EntryCounters:
    like_count: int = 0
    likes_since_update: int = 0
    import_count: int = 0


@dataclass(frozen=True)
class EntryFileInfo:
    capability_id: str
    asset_key: str
    filename: str
    size: int


def _to_entry(row: AgentMarketplaceEntryRow) -> MarketplaceEntry:
    return MarketplaceEntry(
        entry_id=row.entry_id,
        agent_instance_id=row.agent_instance_id,
        team_id=TeamId(row.team_id),
        state=EntryState(row.state),
        removed_reason=row.removed_reason,
        removed_message=row.removed_message,
        removed_at=row.removed_at,
        template_id=row.template_id,
        source_runtime_id=row.source_runtime_id,
        source_agent_id=row.source_agent_id,
        display_name=row.display_name,
        description=row.description,
        tuning_json=row.tuning_json,
        capabilities=json.loads(row.capabilities_json),
        version=row.version,
        first_published_at=row.first_published_at,
        published_at=row.published_at,
        snapshot_source_updated_at=row.snapshot_source_updated_at,
        published_by=row.published_by,
    )


async def remove_published_entries(
    session: AsyncSession,
    *,
    reason: RemovalReason,
    agent_instance_ids: Sequence[str] | None = None,
    team_ids: Sequence[str] | None = None,
    message: str | None = None,
) -> list[RemovedEntry]:
    """Take published entries down inside the caller's transaction: files
    deleted, row, likes and imports kept, version bumped so a stale card's
    next write gets 409."""

    query = select(AgentMarketplaceEntryRow).where(
        AgentMarketplaceEntryRow.state == EntryState.PUBLISHED.value
    )
    if agent_instance_ids is not None:
        query = query.where(
            AgentMarketplaceEntryRow.agent_instance_id.in_(list(agent_instance_ids))
        )
    if team_ids is not None:
        query = query.where(AgentMarketplaceEntryRow.team_id.in_(list(team_ids)))
    rows = (await session.execute(query.with_for_update())).scalars().all()
    if not rows:
        return []
    state = (
        EntryState.DISMISSED
        if reason == RemovalReason.REMOVED_BY_TEAM
        else EntryState.REMOVED
    )
    now = utcnow()
    for row in rows:
        row.state = state.value
        row.removed_reason = reason.value
        row.removed_message = message
        row.removed_at = now
        row.version += 1
    await session.execute(
        delete(AgentMarketplaceEntryFileRow).where(
            AgentMarketplaceEntryFileRow.entry_id.in_([row.entry_id for row in rows])
        )
    )
    await session.flush()
    # Names for the publishers' notifications, read in the same transaction.
    notified_teams = {
        row.team_id for row in rows if row.published_by and state == EntryState.REMOVED
    }
    team_names: dict[str, str] = {}
    if notified_teams:
        names = await session.execute(
            select(TeamMetadataRow.id, TeamMetadataRow.name).where(
                TeamMetadataRow.id.in_(notified_teams)
            )
        )
        team_names = {team_id: name for team_id, name in names.all()}
    return [
        RemovedEntry(
            entry_id=row.entry_id,
            agent_instance_id=row.agent_instance_id,
            team_id=TeamId(row.team_id),
            reason=reason,
            state=state,
            display_name=row.display_name,
            published_by=row.published_by,
            removed_at=now,
            message=message,
            team_name=team_names.get(row.team_id),
        )
        for row in rows
    ]


def emit_unpublished(
    removed: Iterable[RemovedEntry], *, actor_uid: str | None = None
) -> None:
    for entry in removed:
        emit_audit_log(
            "agent.unpublished",
            entry_id=entry.entry_id,
            agent_instance_id=entry.agent_instance_id,
            team_id=str(entry.team_id),
            reason=entry.reason.value,
            user_id=actor_uid,
        )


class AgentMarketplaceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    async def _lock_team(self, session: AsyncSession, team_id: TeamId) -> None:
        # Serializes a team's publications so the quota and the first insert
        # cannot race across replicas; SQLite test runs have no such race.
        if self._engine.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": advisory_lock_key(f"agent_marketplace:{team_id}")},
            )

    @staticmethod
    async def _locked_entry(
        session: AsyncSession, agent_instance_id: str, team_id: TeamId
    ) -> AgentMarketplaceEntryRow | None:
        return (
            await session.execute(
                select(AgentMarketplaceEntryRow)
                .where(
                    AgentMarketplaceEntryRow.agent_instance_id == agent_instance_id,
                    AgentMarketplaceEntryRow.team_id == str(team_id),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _locked_publish_quota(session: AsyncSession, team_id: TeamId) -> int:
        """Re-read the switch and visibility under share locks, settings row then
        team row: a switch-off or private change either waits for this write
        (and then removes it) or commits first and is seen here."""
        default = (
            await session.execute(
                select(PlatformMarketplaceSettingsRow)
                .where(
                    PlatformMarketplaceSettingsRow.id
                    == PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID
                )
                .with_for_update(read=True)
            )
        ).scalar_one_or_none()
        team = (
            await session.execute(
                select(TeamMetadataRow)
                .where(TeamMetadataRow.id == str(team_id))
                .with_for_update(read=True)
            )
        ).scalar_one_or_none()
        if team is None or team.visibility != TeamVisibility.PUBLIC.value:
            raise MarketplacePublishingClosed(team_private=True)
        enabled = team.agents_publishing_enabled
        if enabled is None:
            enabled = (
                default.agents_publishing_enabled
                if default is not None
                else DEFAULT_AGENTS_PUBLISHING_ENABLED
            )
        if not enabled:
            raise MarketplacePublishingClosed(team_private=False)
        if team.agents_publish_quota is not None:
            return team.agents_publish_quota
        return (
            default.agents_publish_quota
            if default is not None
            else DEFAULT_AGENTS_PUBLISH_QUOTA
        )

    @staticmethod
    async def _lock_active_agent(
        session: AsyncSession, agent_instance_id: str, team_id: TeamId
    ) -> None:
        """Share-lock the agent row before the entry, the order deactivation and
        suspension take (agent row, then entry): either they wait and then remove
        this publication, or they committed first and are seen here."""
        agent = (
            await session.execute(
                select(AgentInstanceRow.enabled, AgentInstanceRow.suspension_reason)
                .where(
                    AgentInstanceRow.agent_instance_id == agent_instance_id,
                    AgentInstanceRow.team_id == str(team_id),
                )
                .with_for_update(read=True)
            )
        ).first()
        if agent is None or not agent.enabled or agent.suspension_reason is not None:
            raise MarketplaceAgentInactive()

    @staticmethod
    async def _published_count(session: AsyncSession, team_id: TeamId) -> int:
        return (
            await session.execute(
                select(func.count()).where(
                    AgentMarketplaceEntryRow.team_id == str(team_id),
                    AgentMarketplaceEntryRow.state == EntryState.PUBLISHED.value,
                )
            )
        ).scalar_one()

    async def save_publication(
        self,
        *,
        agent_instance_id: str,
        team_id: TeamId,
        snapshot: Snapshot,
        expected_version: int | None,
        published_by: str,
    ) -> tuple[MarketplaceEntry, bool]:
        """Publish or republish; returns the entry and whether it was a new
        publication (first one, or after a removal), the only kind the quota limits."""

        now = utcnow()
        try:
            async with self._sessions() as s, s.begin():
                quota = await self._locked_publish_quota(s, team_id)
                await self._lock_team(s, team_id)
                await self._lock_active_agent(s, agent_instance_id, team_id)
                row = await self._locked_entry(s, agent_instance_id, team_id)
                current = row.version if row is not None else None
                if expected_version != current:
                    raise MarketplaceVersionConflict()
                is_new = row is None or row.state != EntryState.PUBLISHED.value
                if is_new and await self._published_count(s, team_id) >= quota:
                    raise MarketplaceQuotaReached(quota)
                if row is None:
                    row = AgentMarketplaceEntryRow(
                        entry_id=str(uuid4()),
                        agent_instance_id=agent_instance_id,
                        team_id=str(team_id),
                        version=0,
                        first_published_at=now,
                    )
                    s.add(row)
                else:
                    await s.execute(
                        delete(AgentMarketplaceEntryFileRow).where(
                            AgentMarketplaceEntryFileRow.entry_id == row.entry_id
                        )
                    )
                row.state = EntryState.PUBLISHED.value
                row.removed_reason = None
                row.removed_message = None
                row.removed_at = None
                row.template_id = snapshot.template_id
                row.source_runtime_id = snapshot.source_runtime_id
                row.source_agent_id = snapshot.source_agent_id
                row.display_name = snapshot.display_name
                row.description = snapshot.description
                row.tuning_json = snapshot.tuning_json
                row.capabilities_json = json.dumps(snapshot.capabilities)
                row.version += 1
                row.published_at = now
                row.snapshot_source_updated_at = snapshot.source_updated_at
                row.published_by = published_by
                await s.flush()
                s.add_all(
                    AgentMarketplaceEntryFileRow(
                        entry_id=row.entry_id,
                        capability_id=file.capability_id,
                        asset_key=file.asset_key,
                        filename=file.filename,
                        size=len(file.content),
                        content=file.content,
                    )
                    for file in snapshot.files
                )
                await s.flush()
                entry = _to_entry(row)
        except IntegrityError as exc:
            # Two first publications of the same agent: the loser saw no entry.
            raise MarketplaceVersionConflict() from exc
        return entry, is_new

    async def remove(
        self,
        *,
        agent_instance_id: str,
        team_id: TeamId,
        expected_version: int,
        reason: RemovalReason,
        message: str | None = None,
    ) -> RemovedEntry:
        async with self._sessions() as s, s.begin():
            row = await self._locked_entry(s, agent_instance_id, team_id)
            if row is None:
                raise MarketplaceEntryNotFound()
            if row.version != expected_version:
                raise MarketplaceVersionConflict()
            if row.state != EntryState.PUBLISHED.value:
                raise MarketplaceEntryNotFound()
            [removed] = await remove_published_entries(
                s,
                reason=reason,
                agent_instance_ids=[agent_instance_id],
                message=message,
            )
        return removed

    async def dismiss(self, *, agent_instance_id: str, team_id: TeamId) -> None:
        """Hide the Removed state for the whole team; nothing else changes."""
        async with self._sessions() as s, s.begin():
            row = await self._locked_entry(s, agent_instance_id, team_id)
            if row is None or row.state != EntryState.REMOVED.value:
                raise MarketplaceEntryNotFound()
            row.state = EntryState.DISMISSED.value

    async def remove_team_entries(
        self,
        team_ids: Sequence[TeamId],
        reason: RemovalReason,
        *,
        session: AsyncSession | None = None,
    ) -> list[RemovedEntry]:
        if not team_ids:
            return []
        async with use_session(self._sessions, session) as s:
            return await remove_published_entries(
                s, reason=reason, team_ids=[str(t) for t in team_ids]
            )

    async def get_for_agent(
        self, agent_instance_id: str, team_id: TeamId
    ) -> MarketplaceEntry | None:
        async with self._sessions() as s:
            row = (
                await s.execute(
                    select(AgentMarketplaceEntryRow).where(
                        AgentMarketplaceEntryRow.agent_instance_id == agent_instance_id,
                        AgentMarketplaceEntryRow.team_id == str(team_id),
                    )
                )
            ).scalar_one_or_none()
        return _to_entry(row) if row is not None else None

    async def get_published(self, entry_id: str) -> MarketplaceEntry | None:
        async with self._sessions() as s:
            row = await s.get(AgentMarketplaceEntryRow, entry_id)
        if row is None or row.state != EntryState.PUBLISHED.value:
            return None
        return _to_entry(row)

    async def list_for_team(self, team_id: TeamId) -> list[MarketplaceEntry]:
        async with self._sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(AgentMarketplaceEntryRow).where(
                            AgentMarketplaceEntryRow.team_id == str(team_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [_to_entry(row) for row in rows]

    def _role_column(self) -> Any:
        # The role read inside the database: the listing never loads the snapshot.
        tuning = AgentMarketplaceEntryRow.tuning_json
        if self._engine.dialect.name == "postgresql":
            return func.json_extract_path_text(cast(tuning, JSON), "role")
        return func.json_extract(tuning, "$.role")

    async def list_published(
        self, *, q: str | None = None, team_id: TeamId | None = None
    ) -> list[ListedEntry]:
        """Published entries, newest first publication first, with the team's current name."""
        entry = AgentMarketplaceEntryRow
        query = (
            select(
                entry.entry_id,
                entry.team_id,
                TeamMetadataRow.name,
                entry.template_id,
                entry.display_name,
                entry.description,
                self._role_column(),
                entry.version,
                entry.first_published_at,
                entry.published_at,
            )
            .outerjoin(
                TeamMetadataRow, TeamMetadataRow.id == AgentMarketplaceEntryRow.team_id
            )
            .where(AgentMarketplaceEntryRow.state == EntryState.PUBLISHED.value)
            .order_by(AgentMarketplaceEntryRow.first_published_at.desc())
        )
        if team_id is not None:
            query = query.where(AgentMarketplaceEntryRow.team_id == str(team_id))
        if q and q.strip():
            needle = q.strip().lower()
            query = query.where(
                or_(
                    func.lower(AgentMarketplaceEntryRow.display_name).contains(
                        needle, autoescape=True
                    ),
                    func.lower(AgentMarketplaceEntryRow.description).contains(
                        needle, autoescape=True
                    ),
                    func.lower(TeamMetadataRow.name).contains(needle, autoescape=True),
                )
            )
        async with self._sessions() as s:
            rows = (await s.execute(query)).all()
        return [
            ListedEntry(
                entry_id=row[0],
                team_id=TeamId(row[1]),
                team_name=row[2],
                template_id=row[3],
                display_name=row[4],
                description=row[5],
                role=row[6],
                version=row[7],
                first_published_at=row[8],
                published_at=row[9],
            )
            for row in rows
        ]

    async def team_name(self, team_id: TeamId) -> str | None:
        async with self._sessions() as s:
            return (
                await s.execute(
                    select(TeamMetadataRow.name).where(
                        TeamMetadataRow.id == str(team_id)
                    )
                )
            ).scalar_one_or_none()

    async def counters(self, entry_ids: Sequence[str]) -> dict[str, EntryCounters]:
        """Likes (total and on the current version) and imports, two grouped queries."""
        if not entry_ids:
            return {}
        ids = list(entry_ids)
        async with self._sessions() as s:
            likes = (
                await s.execute(
                    select(
                        AgentMarketplaceLikeRow.entry_id,
                        func.count(),
                        func.sum(
                            case(
                                (
                                    AgentMarketplaceLikeRow.version
                                    == AgentMarketplaceEntryRow.version,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                    )
                    .join(
                        AgentMarketplaceEntryRow,
                        AgentMarketplaceEntryRow.entry_id
                        == AgentMarketplaceLikeRow.entry_id,
                    )
                    .where(
                        AgentMarketplaceLikeRow.entry_id.in_(ids),
                        AgentMarketplaceLikeRow.removed_at.is_(None),
                    )
                    .group_by(AgentMarketplaceLikeRow.entry_id)
                )
            ).all()
            imports = (
                await s.execute(
                    select(AgentMarketplaceImportRow.entry_id, func.count())
                    .where(AgentMarketplaceImportRow.entry_id.in_(ids))
                    .group_by(AgentMarketplaceImportRow.entry_id)
                )
            ).all()
        like_by_id = {row[0]: (row[1], int(row[2] or 0)) for row in likes}
        import_by_id = {row[0]: row[1] for row in imports}
        return {
            entry_id: EntryCounters(
                like_count=like_by_id.get(entry_id, (0, 0))[0],
                likes_since_update=like_by_id.get(entry_id, (0, 0))[1],
                import_count=import_by_id.get(entry_id, 0),
            )
            for entry_id in ids
        }

    async def liked_by(self, user_id: str, entry_ids: Sequence[str]) -> set[str]:
        if not entry_ids:
            return set()
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(AgentMarketplaceLikeRow.entry_id).where(
                        AgentMarketplaceLikeRow.user_id == user_id,
                        AgentMarketplaceLikeRow.entry_id.in_(list(entry_ids)),
                        AgentMarketplaceLikeRow.removed_at.is_(None),
                    )
                )
            ).all()
        return {row[0] for row in rows}

    async def count_published(self, team_ids: Sequence[TeamId]) -> dict[TeamId, int]:
        counts: dict[TeamId, int] = {team_id: 0 for team_id in team_ids}
        if not team_ids:
            return counts
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(AgentMarketplaceEntryRow.team_id, func.count())
                    .where(
                        AgentMarketplaceEntryRow.team_id.in_(
                            [str(t) for t in team_ids]
                        ),
                        AgentMarketplaceEntryRow.state == EntryState.PUBLISHED.value,
                    )
                    .group_by(AgentMarketplaceEntryRow.team_id)
                )
            ).all()
        for team_id, count in rows:
            counts[TeamId(team_id)] = count
        return counts

    async def published_agent_ids(self, agent_instance_ids: Sequence[str]) -> set[str]:
        if not agent_instance_ids:
            return set()
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(AgentMarketplaceEntryRow.agent_instance_id).where(
                        AgentMarketplaceEntryRow.agent_instance_id.in_(
                            list(agent_instance_ids)
                        ),
                        AgentMarketplaceEntryRow.state == EntryState.PUBLISHED.value,
                    )
                )
            ).all()
        return {row[0] for row in rows}

    async def set_like(self, entry_id: str, user_id: str, *, liked: bool) -> None:
        """Idempotent like or unlike of a published entry; an unlike keeps the row."""
        try:
            async with self._sessions() as s, s.begin():
                entry = await s.get(AgentMarketplaceEntryRow, entry_id)
                if entry is None or entry.state != EntryState.PUBLISHED.value:
                    raise MarketplaceEntryNotFound()
                active = AgentMarketplaceLikeRow.removed_at.is_(None)
                if not liked:
                    await s.execute(
                        update(AgentMarketplaceLikeRow)
                        .where(
                            AgentMarketplaceLikeRow.entry_id == entry_id,
                            AgentMarketplaceLikeRow.user_id == user_id,
                            active,
                        )
                        .values(removed_at=utcnow())
                    )
                    return
                existing = (
                    await s.execute(
                        select(AgentMarketplaceLikeRow.like_id).where(
                            AgentMarketplaceLikeRow.entry_id == entry_id,
                            AgentMarketplaceLikeRow.user_id == user_id,
                            active,
                        )
                    )
                ).first()
                if existing is None:
                    s.add(
                        AgentMarketplaceLikeRow(
                            like_id=str(uuid4()),
                            entry_id=entry_id,
                            user_id=user_id,
                            version=entry.version,
                            created_at=utcnow(),
                        )
                    )
        except IntegrityError:
            # A concurrent like by the same user already holds the active row.
            return

    async def list_files(self, entry_id: str) -> list[EntryFileInfo]:
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(
                        AgentMarketplaceEntryFileRow.capability_id,
                        AgentMarketplaceEntryFileRow.asset_key,
                        AgentMarketplaceEntryFileRow.filename,
                        AgentMarketplaceEntryFileRow.size,
                    )
                    .where(AgentMarketplaceEntryFileRow.entry_id == entry_id)
                    .order_by(
                        AgentMarketplaceEntryFileRow.capability_id,
                        AgentMarketplaceEntryFileRow.asset_key,
                    )
                )
            ).all()
        return [
            EntryFileInfo(
                capability_id=row[0], asset_key=row[1], filename=row[2], size=row[3]
            )
            for row in rows
        ]

    async def asset_files(self, entry_id: str) -> dict[str, dict[str, str]]:
        """The snapshot's files per capability, base64-encoded for `copy-config`."""
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(
                        AgentMarketplaceEntryFileRow.capability_id,
                        AgentMarketplaceEntryFileRow.asset_key,
                        AgentMarketplaceEntryFileRow.content,
                    ).where(AgentMarketplaceEntryFileRow.entry_id == entry_id)
                )
            ).all()
        files: dict[str, dict[str, str]] = {}
        for capability_id, asset_key, content in rows:
            files.setdefault(capability_id, {})[asset_key] = base64.b64encode(
                content
            ).decode("ascii")
        return files

    async def record_import(
        self,
        *,
        entry_id: str,
        target_team_id: TeamId,
        user_id: str,
        agent_instance_id: str,
        version: int,
    ) -> None:
        async with use_session(self._sessions) as s:
            s.add(
                AgentMarketplaceImportRow(
                    import_id=str(uuid4()),
                    entry_id=entry_id,
                    target_team_id=str(target_team_id),
                    user_id=user_id,
                    agent_instance_id=agent_instance_id,
                    version=version,
                    created_at=utcnow(),
                )
            )
