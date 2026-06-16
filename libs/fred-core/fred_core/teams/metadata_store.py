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
from datetime import datetime, timezone
from typing import cast

from pydantic import BaseModel, Field
from sqlalchemy import CursorResult, delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.common.team_id import TeamId
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.teams.team_metatada_models import TeamMetadataRow

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TeamMetadataPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=180)
    is_private: bool | None = None
    banner_object_storage_key: str | None = Field(default=None, max_length=300)
    banner_image_url: str | None = Field(default=None, max_length=300)

    def to_store_values(self) -> dict[str, str | bool | None]:
        values: dict[str, str | bool | None] = {}
        payload = self.model_dump(exclude_unset=True)
        if "name" in payload:
            values["name"] = payload["name"]
        if "description" in payload:
            values["description"] = payload["description"]
        if "is_private" in payload:
            values["is_private"] = payload["is_private"]
        if "banner_object_storage_key" in payload:
            values["banner_object_storage_key"] = payload["banner_object_storage_key"]
        elif "banner_image_url" in payload:
            # Backward compatibility for clients that still send this field.
            values["banner_object_storage_key"] = payload["banner_image_url"]
        return values


class TeamMetadata(BaseModel):
    id: TeamId
    name: str | None = None
    description: str | None = None
    is_private: bool = True
    banner_object_storage_key: str | None = None
    max_resources_storage_size: int | None = None
    current_resources_storage_size: int | None = None


class TeamMetadataStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def list_all(self) -> list[TeamMetadata]:
        async with use_session(self._sessions) as s:
            rows = (await s.execute(select(TeamMetadataRow))).scalars().all()
        return [
            TeamMetadata(
                id=TeamId(row.id),
                name=row.name,
                description=row.description,
                is_private=row.is_private,
                banner_object_storage_key=row.banner_object_storage_key,
                max_resources_storage_size=row.max_resources_storage_size,
                current_resources_storage_size=row.current_resources_storage_size,
            )
            for row in rows
        ]

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
                is_private=row.is_private,
                banner_object_storage_key=row.banner_object_storage_key,
                max_resources_storage_size=row.max_resources_storage_size,
                current_resources_storage_size=row.current_resources_storage_size,
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

    async def insert(
        self,
        team_id: TeamId,
        name: str,
        description: str | None,
        is_private: bool,
    ) -> TeamMetadata:
        """Insert a new team row; raises IntegrityError if team_id already exists."""
        row = TeamMetadataRow(
            id=str(team_id),
            name=name,
            description=description,
            is_private=is_private,
            current_resources_storage_size=0,
        )
        async with use_session(self._sessions) as s:
            s.add(row)
        return TeamMetadata(
            id=team_id,
            name=name,
            description=description,
            is_private=is_private,
        )

    async def delete_by_id(self, team_id: TeamId) -> bool:
        """Delete a team row. Returns True if a row was deleted."""
        async with use_session(self._sessions) as s:
            result = await s.execute(
                sa_delete(TeamMetadataRow).where(TeamMetadataRow.id == str(team_id))
            )
        return cast(CursorResult, result).rowcount > 0

    async def upsert(
        self,
        team_id: TeamId,
        patch: TeamMetadataPatch,
        session: AsyncSession | None = None,
    ) -> TeamMetadata:
        update_values = patch.to_store_values()
        if not update_values:
            existing = await self.get_by_team_id(team_id, session=session)
            if existing is not None:
                return existing
            return TeamMetadata(id=team_id)

        async with use_session(self._sessions, session) as s:
            existing_row = await s.get(TeamMetadataRow, str(team_id))
            if existing_row is None:
                row = TeamMetadataRow(
                    id=str(team_id),
                    **update_values,
                )
            else:
                for k, v in update_values.items():
                    setattr(existing_row, k, v)
                row = existing_row
            await s.merge(row)

        updated = await self.get_by_team_id(team_id, session=session)
        if updated is None:
            raise RuntimeError(
                f"Failed to read metadata for team '{team_id}' after upsert"
            )
        return updated

    async def increment_current_storage_size(
        self,
        team_id: TeamId,
        delta: int,
        session: AsyncSession | None = None,
    ) -> None:
        """Increment current storage size of a team by a delta (can be negative)."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(TeamMetadataRow, str(team_id))
            if row is None:
                row = TeamMetadataRow(
                    id=str(team_id),
                    current_resources_storage_size=delta,
                )
                s.add(row)
            else:
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
