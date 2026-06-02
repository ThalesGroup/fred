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

import logging
from typing import List

from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from knowledge_flow_backend.core.stores.tags.base_tag_store import (
    BaseTagStore,
    TagAlreadyExistsError,
    TagDeserializationError,
    TagNotFoundError,
)
from knowledge_flow_backend.core.stores.tags.tag_models import TagRow
from knowledge_flow_backend.features.tag.structure import Tag, TagType

logger = logging.getLogger(__name__)


class PostgresTagStore(BaseTagStore):
    """PostgreSQL-backed tag store using declarative ORM."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    # --- helpers ---

    @staticmethod
    def _row_to_tag(row: TagRow) -> Tag:
        try:
            return Tag.model_validate(row.doc or {})
        except Exception as e:
            raise TagDeserializationError(f"Invalid tag JSON: {e}") from e

    @staticmethod
    def _require_id(tag: Tag) -> str:
        tid = tag.id
        if not tid:
            raise ValueError("Tag must contain an 'id'")
        return tid

    # --- CRUD ---

    async def list_all_tags(self, session: AsyncSession | None = None) -> List[Tag]:
        return await self.list_all(session=session)

    async def get_tag_by_id(self, tag_id: str, session: AsyncSession | None = None) -> Tag:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TagRow, tag_id)
        if row is None:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        return self._row_to_tag(row)

    async def create_tag(self, tag: Tag, session: AsyncSession | None = None) -> Tag:
        tid = self._require_id(tag)
        async with use_session(self._sessions, session) as s:
            existing = await s.get(TagRow, tid)
            if existing:
                raise TagAlreadyExistsError(f"Tag with id '{tid}' already exists.")
            row = TagRow(
                tag_id=tid,
                created_at=tag.created_at,
                updated_at=tag.updated_at,
                owner_id=tag.owner_id,
                name=tag.name,
                path=tag.path,
                description=tag.description,
                type=tag.type.value,
                doc=tag.model_dump(mode="json"),
            )
            s.add(row)
        return tag

    async def update_tag_by_id(self, tag_id: str, tag: Tag, session: AsyncSession | None = None) -> Tag:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TagRow, tag_id)
            if row is None:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            row.created_at = tag.created_at
            row.updated_at = tag.updated_at
            row.owner_id = tag.owner_id
            row.name = tag.name
            row.path = tag.path
            row.description = tag.description
            row.type = tag.type.value
            row.doc = tag.model_dump(mode="json")
        return tag

    async def delete_tag_by_id(self, tag_id: str, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TagRow, tag_id)
            if row is None:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            await s.delete(row)

    async def get_by_owner_type_full_path(self, owner_id: str, tag_type: TagType, full_path: str, session: AsyncSession | None = None) -> Tag | None:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(TagRow).where(
                            TagRow.owner_id == owner_id,
                            TagRow.type == tag_type.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
        for row in rows:
            t = self._row_to_tag(row)
            if t.full_path == full_path and t.type == tag_type:
                return t
        return None

    # --- convenience helpers ---

    async def list_all(self, session: AsyncSession | None = None) -> List[Tag]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TagRow))).scalars().all()
        return [self._row_to_tag(row) for row in rows]

    async def list_by_type(self, tag_type: str, session: AsyncSession | None = None) -> List[Tag]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TagRow).where(TagRow.type == tag_type))).scalars().all()
        return [self._row_to_tag(row) for row in rows]
