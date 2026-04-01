from __future__ import annotations

import logging

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.team_metadata_models import TeamMetadataRow

logger = logging.getLogger(__name__)


class TeamMetadataPatch(BaseModel):
    description: str | None = Field(default=None, max_length=180)
    is_private: bool | None = None
    banner_object_storage_key: str | None = Field(default=None, max_length=300)
    banner_image_url: str | None = Field(default=None, max_length=300)

    def to_store_values(self) -> dict[str, str | bool | None]:
        values: dict[str, str | bool | None] = {}
        payload = self.model_dump(exclude_unset=True)
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
    description: str | None = None
    is_private: bool = True
    banner_object_storage_key: str | None = None


class TeamMetadataStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

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
                description=row.description,
                is_private=row.is_private,
                banner_object_storage_key=row.banner_object_storage_key,
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
                    is_private=True,
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
