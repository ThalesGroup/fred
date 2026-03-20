from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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
        self.store = AsyncBaseSqlStore(engine=engine)
        self.table_name = self.store.prefixed("teammetadata")
        self._ddl_lock_id = advisory_lock_key(self.table_name)
        self._schema_ready_task: asyncio.Task[None] | None = None

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("id", String, primary_key=True),
            Column("description", String(180), nullable=True),
            Column("is_private", Boolean, nullable=False, default=True),
            Column("banner_object_storage_key", String(300), nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            keep_existing=True,
        )

        async def _create() -> None:
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=metadata.create_all,
                logger=logger,
            )

        try:
            loop = asyncio.get_running_loop()
            self._schema_ready_task = loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())

        logger.info("[TEAM_METADATA] Table ready: %s", self.table_name)

    async def _ensure_schema_ready(self) -> None:
        if self._schema_ready_task is not None:
            await self._schema_ready_task

    async def get_by_team_ids(
        self, team_ids: list[TeamId]
    ) -> dict[TeamId, TeamMetadata]:
        if not team_ids:
            return {}

        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(
                    self.table.c.id,
                    self.table.c.description,
                    self.table.c.is_private,
                    self.table.c.banner_object_storage_key,
                ).where(self.table.c.id.in_(team_ids))
            )
            rows = result.mappings().all()

        return {
            TeamId(str(row["id"])): TeamMetadata(
                id=TeamId(str(row["id"])),
                description=row["description"],
                is_private=row["is_private"],
                banner_object_storage_key=row["banner_object_storage_key"],
            )
            for row in rows
        }

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata | None:
        by_team_id = await self.get_by_team_ids([team_id])
        return by_team_id.get(team_id)

    async def upsert(self, team_id: TeamId, patch: TeamMetadataPatch) -> TeamMetadata:
        await self._ensure_schema_ready()

        update_values = patch.to_store_values()
        if not update_values:
            existing = await self.get_by_team_id(team_id)
            if existing is not None:
                return existing
            return TeamMetadata(id=team_id)

        now = _utcnow()
        values: dict[str, str | bool | datetime | None] = {
            "id": team_id,
            "is_private": True,
            "created_at": now,
            "updated_at": now,
            **update_values,
        }
        update_cols = list(update_values.keys()) + ["updated_at"]

        async with self.store.begin() as conn:
            await self.store.upsert(
                conn=conn,
                table=self.table,
                values=values,
                pk_cols=["id"],
                update_cols=update_cols,
            )

        updated = await self.get_by_team_id(team_id)
        if updated is None:
            raise RuntimeError(
                f"Failed to read metadata for team '{team_id}' after upsert"
            )
        return updated
