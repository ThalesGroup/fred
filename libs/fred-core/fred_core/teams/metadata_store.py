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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.common.team_id import TeamId
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.sql.base_sql import advisory_lock_key
from fred_core.teams.team_metatada_models import TeamMetadataRow

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class JoiningMode(str, Enum):
    """TEAM-09 (RFC FRED-TEAM-CONFIG-RFC.md §5.1.1): replaces the former
    standalone `is_private` bool. Gates only whether/how a user can become a
    member — never marketplace visibility, which is now unconditional for
    every team (see `RebacEngine.ensure_team_public_relations`)."""

    OPEN = "open"
    REQUEST_ONLY = "request_only"
    INVITE_ONLY = "invite_only"
    CLOSED = "closed"


class TeamMetadataPatch(BaseModel):
    description: str | None = Field(default=None, max_length=180)
    joining_mode: JoiningMode | None = None
    banner_object_storage_key: str | None = Field(default=None, max_length=300)
    banner_image_url: str | None = Field(default=None, max_length=300)
    # CTRLP-12 (RFC §3.B): per-team retention fields, patched through the same
    # team surface. Partial semantics via exclude_unset — omitted keeps the
    # current value, explicit None clears it.
    team_delete_grace: str | None = None
    max_idle: str | None = None
    retention_updated_by: str | None = None

    def to_store_values(self) -> dict[str, str | bool | None]:
        values: dict[str, str | bool | None] = {}
        payload = self.model_dump(exclude_unset=True, mode="json")
        if "description" in payload:
            values["description"] = payload["description"]
        if "joining_mode" in payload:
            values["joining_mode"] = payload["joining_mode"]
        if "banner_object_storage_key" in payload:
            values["banner_object_storage_key"] = payload["banner_object_storage_key"]
        elif "banner_image_url" in payload:
            # Backward compatibility for clients that still send this field.
            values["banner_object_storage_key"] = payload["banner_image_url"]
        for field in ("team_delete_grace", "max_idle", "retention_updated_by"):
            if field in payload:
                values[field] = payload[field]
        return values


class TeamMetadata(BaseModel):
    id: TeamId
    # AUTHZ-05 review item 9: the team's name, set once at creation
    # (`TeamMetadataStore.create`) and immutable afterwards — no Keycloak
    # group backs it anymore.
    name: str
    description: str | None = None
    joining_mode: JoiningMode = JoiningMode.REQUEST_ONLY
    banner_object_storage_key: str | None = None
    max_resources_storage_size: int | None = None
    current_resources_storage_size: int | None = None
    # CTRLP-12 (RFC §3.B): per-team retention, read straight off this record so
    # the resolver never needs a separate override store. None = inherit cap.
    team_delete_grace: str | None = None
    max_idle: str | None = None
    retention_updated_by: str | None = None


class TeamMetadataStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @asynccontextmanager
    async def advisory_lock(self, key: str) -> AsyncIterator[None]:
        """Hold a Postgres transaction-scoped advisory lock for `key` for the
        duration of the `async with` block.

        Why this exists: some team-registry actions (e.g. `rescue_team_admin`)
        must check-then-write against OpenFGA, which has no way to express a
        conditional write ("only if this team has no team_admin yet") in a
        single atomic call. Serializing concurrent callers on the same `key`
        (across replicas, not just this process — an `asyncio.Lock` would only
        cover one) closes that race without needing OpenFGA itself to support it.

        The lock auto-releases when the backing transaction commits or rolls
        back — no explicit unlock, nothing can leak it on a crash. No-op on
        non-Postgres dialects (e.g. SQLite in tests): a single-process test
        run has no cross-replica race to close.
        """
        async with self._sessions() as s, s.begin():
            if self._engine.dialect.name == "postgresql":
                await s.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(key)},
                )
            yield

    async def get_by_team_ids(
        self,
        team_ids: list[TeamId],
        session: AsyncSession | None = None,
    ) -> dict[TeamId, TeamMetadata]:
        if not team_ids:
            return {}
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(TeamMetadataRow).where(TeamMetadataRow.id.in_(team_ids))
                    )
                )
                .scalars()
                .all()
            )
        return {
            TeamId(row.id): TeamMetadata(
                id=TeamId(row.id),
                name=row.name,
                description=row.description,
                joining_mode=JoiningMode(row.joining_mode),
                banner_object_storage_key=row.banner_object_storage_key,
                max_resources_storage_size=row.max_resources_storage_size,
                current_resources_storage_size=row.current_resources_storage_size,
                team_delete_grace=row.team_delete_grace,
                max_idle=row.max_idle,
                retention_updated_by=row.retention_updated_by,
            )
            for row in rows
        }

    async def get_by_team_id(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> TeamMetadata | None:
        by_id = await self.get_by_team_ids([team_id], session=session)
        return by_id.get(team_id)

    async def create(
        self,
        team_id: TeamId,
        name: str,
        session: AsyncSession | None = None,
    ) -> TeamMetadata:
        """Create one team's metadata row (AUTHZ-05 review item 9).

        `name` is set once, here, and never patched afterwards — `upsert`
        only touches the mutable fields (description, privacy, banner,
        retention). Callers must ensure `team_id` does not already exist
        (`create_team`'s own name-uniqueness check does this); a duplicate
        id raises the underlying integrity error rather than silently
        overwriting an existing team.
        """
        async with use_session(self._sessions, session) as s:
            s.add(TeamMetadataRow(id=str(team_id), name=name))

        created = await self.get_by_team_id(team_id, session=session)
        if created is None:
            raise RuntimeError(
                f"Failed to read metadata for team '{team_id}' after create"
            )
        return created

    async def list_all(self, session: AsyncSession | None = None) -> list[TeamMetadata]:
        """Return every team's metadata (AUTHZ-05 review item 9: the registry
        source of truth, replacing the Keycloak root-group enumeration)."""
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TeamMetadataRow))).scalars().all()
        return [
            TeamMetadata(
                id=TeamId(row.id),
                name=row.name,
                description=row.description,
                joining_mode=JoiningMode(row.joining_mode),
                banner_object_storage_key=row.banner_object_storage_key,
                max_resources_storage_size=row.max_resources_storage_size,
                current_resources_storage_size=row.current_resources_storage_size,
                team_delete_grace=row.team_delete_grace,
                max_idle=row.max_idle,
                retention_updated_by=row.retention_updated_by,
            )
            for row in rows
        ]

    async def get_by_name(
        self,
        name: str,
        session: AsyncSession | None = None,
    ) -> TeamMetadata | None:
        """Look up one team by its (unique) name — used by `create_team` to
        reject a colliding name before writing a new row."""
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.name == name)
                )
            ).scalar_one_or_none()
        return (
            None
            if row is None
            else TeamMetadata(
                id=TeamId(row.id),
                name=row.name,
                description=row.description,
                joining_mode=JoiningMode(row.joining_mode),
                banner_object_storage_key=row.banner_object_storage_key,
                max_resources_storage_size=row.max_resources_storage_size,
                current_resources_storage_size=row.current_resources_storage_size,
                team_delete_grace=row.team_delete_grace,
                max_idle=row.max_idle,
                retention_updated_by=row.retention_updated_by,
            )
        )

    async def delete(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> None:
        """Delete one team's metadata row (AUTHZ-05 review item 9, `can_delete_team`)."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamMetadataRow, str(team_id))
            if row is not None:
                await s.delete(row)

    async def upsert(
        self,
        team_id: TeamId,
        patch: TeamMetadataPatch,
        session: AsyncSession | None = None,
    ) -> TeamMetadata | None:
        """Patch an existing team's mutable metadata fields.

        Returns `None` when the row does not exist — `upsert` never creates a
        team (`create` is the only path that does, and it requires `name`,
        which a patch does not carry). AUTHZ-05 post-implementation review
        finding: this used to fall through to constructing a `TeamMetadataRow`
        with no `name` when the row was missing, which is `NOT NULL` — a
        concurrent `delete_team` landing between a caller's existence check
        and this call would turn into a raw `IntegrityError` (500) instead of
        the graceful "nothing to update" every other caller already expects.
        """
        update_values = patch.to_store_values()
        if not update_values:
            return await self.get_by_team_id(team_id, session=session)

        async with use_session(self._sessions, session) as s:
            existing_row = await s.get(TeamMetadataRow, str(team_id))
            if existing_row is None:
                return None
            for k, v in update_values.items():
                setattr(existing_row, k, v)
            await s.merge(existing_row)

        return await self.get_by_team_id(team_id, session=session)

    async def increment_current_storage_size(
        self,
        team_id: TeamId,
        delta: int,
        session: AsyncSession | None = None,
    ) -> None:
        """Increment current storage size of a team by a delta (can be negative).

        No-ops (with a warning) when the team no longer exists — this is a
        best-effort storage-accounting update over a batch of teams
        (`metadata/service.py`), not the source of truth for team existence.
        AUTHZ-05 post-implementation review finding: this used to construct a
        `TeamMetadataRow` with no `name` for a missing team, which is
        `NOT NULL` — a team deleted concurrently with a storage recalculation
        pass would turn one team's accounting update into a raw
        `IntegrityError` (500) instead of skipping just that team.
        """
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamMetadataRow, str(team_id))
            if row is None:
                logger.warning(
                    "Skipping storage size update for unknown team '%s' (delta=%d)",
                    team_id,
                    delta,
                )
                return
            current = row.current_resources_storage_size or 0
            row.current_resources_storage_size = current + delta

    async def check_quota(
        self,
        team_id: TeamId,
        delta: int,
        default_limit: int | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[bool, int, int | None]:
        """
        Check if adding `delta` bytes to the team's current storage would exceed its limit.

        Returns:
            tuple[bool, int, int | None]: (allowed, current_size, max_size)
        """
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamMetadataRow, str(team_id))
            if row is None:
                current = 0
                max_size = default_limit
            else:
                current = row.current_resources_storage_size or 0
                max_size = (
                    row.max_resources_storage_size
                    if row.max_resources_storage_size is not None
                    else default_limit
                )

            if max_size is None or max_size <= 0:
                return True, current, max_size

            allowed = (current + delta) <= max_size
            return allowed, current, max_size
