# Copyright Thales 2025
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

import asyncio
import logging
from typing import Any, List

from fred_core import KeycloakUser
from fred_core.sql import AsyncBaseSqlStore, PydanticJsonMixin, json_for_engine
from sqlalchemy import Column, DateTime, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.core.stores.tags.base_tag_store import (
    BaseTagStore,
    TagAlreadyExistsError,
    TagDeserializationError,
    TagNotFoundError,
)
from knowledge_flow_backend.features.tag.structure import Tag, TagType

logger = logging.getLogger(__name__)


class PostgresTagStore(BaseTagStore, PydanticJsonMixin):
    """
    PostgreSQL-backed tag store using JSONB.
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        json_type = json_for_engine(self.store.engine)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("tag_id", String, primary_key=True),
            Column("created_at", DateTime(timezone=True)),
            Column("updated_at", DateTime(timezone=True), index=True),
            Column("owner_id", String, index=True),
            Column("name", String, index=True),
            Column("path", String, index=True),
            Column("description", String),
            Column("type", String, index=True),
            Column("doc", json_type),
            keep_existing=True,
        )

        async def _create():
            async with self.store.engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(metadata.create_all)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[TAGS][PG][ASYNC] Table ready: %s", self.table_name)

    @staticmethod
    def _from_dict(data: Any) -> Tag:
        try:
            return Tag.model_validate(data or {})
        except Exception as e:  # keep broad to mirror metadata store behavior
            raise TagDeserializationError(f"Invalid tag JSON: {e}") from e

    @staticmethod
    def _require_id(tag: Tag) -> str:
        tid = tag.id
        if not tid:
            raise ValueError("Tag must contain an 'id'")
        return tid

    # CRUD implementation mirroring DuckDB store

    async def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        owner_id = getattr(user, "uid", None) or getattr(user, "id", None) or getattr(user, "sub", None)
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc).where(self.table.c.owner_id == owner_id).order_by(self.table.c.path.nullsfirst(), self.table.c.name))
            rows = result.fetchall()
        return [self._from_dict(r[0]) for r in rows]

    async def get_tag_by_id(self, tag_id: str) -> Tag:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc).where(self.table.c.tag_id == tag_id))
            row = result.fetchone()
        if not row:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        return self._from_dict(row[0])

    async def create_tag(self, tag: Tag) -> Tag:
        tid = self._require_id(tag)
        # fail if exists
        try:
            await self.get_tag_by_id(tid)
            raise TagAlreadyExistsError(f"Tag with id '{tid}' already exists.")
        except TagNotFoundError:
            pass
        values = {
            "tag_id": tid,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "owner_id": tag.owner_id,
            "name": tag.name,
            "path": tag.path,
            "description": tag.description,
            "type": tag.type.value,
            "doc": tag.model_dump(mode="json"),
        }
        async with self.store.begin() as conn:
            await conn.execute(self.table.insert().values(**values))
        return tag

    async def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        await self.get_tag_by_id(tag_id)
        values = {
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "owner_id": tag.owner_id,
            "name": tag.name,
            "path": tag.path,
            "description": tag.description,
            "type": tag.type.value,
            "doc": tag.model_dump(mode="json"),
        }
        async with self.store.begin() as conn:
            await conn.execute(self.table.update().where(self.table.c.tag_id == tag_id).values(**values))
        return tag

    async def delete_tag_by_id(self, tag_id: str) -> None:
        async with self.store.begin() as conn:
            result = await conn.execute(self.table.delete().where(self.table.c.tag_id == tag_id))
        if result.rowcount == 0:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")

    async def get_by_owner_type_full_path(self, owner_id: str, tag_type: TagType, full_path: str) -> Tag | None:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.doc).where(
                    self.table.c.owner_id == owner_id,
                    self.table.c.type == tag_type.value,
                )
            )
            rows = result.fetchall()
        for r in rows:
            t = self._from_dict(r[0])
            if t.full_path == full_path and t.type == tag_type:
                return t
        return None

    # Convenience helpers used elsewhere
    async def list_all(self) -> List[Tag]:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc))
            rows = result.fetchall()
        return [self._from_dict(r[0]) for r in rows]

    async def list_by_type(self, tag_type: str) -> List[Tag]:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc).where(self.table.c.type == tag_type))
            rows = result.fetchall()
        return [self._from_dict(r[0]) for r in rows]
