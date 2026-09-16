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

from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from knowledge_flow_backend.core.stores.tags.base_tag_store import (
    BaseTagStore,
    TagAlreadyExistsError,
    TagDeserializationError,
    TagNotFoundError,
)
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
        """Find one tag by the path that identifies it within its owner.

        A full path is a parent path and a leaf name, and both are indexed
        columns, so the pair is looked up directly. That matters because this is
        asked once per folder of every document a synchronizing caller writes —
        as a scan of every tag its owner has, a bulk run cost one full read of
        the table per path segment per document.

        The scan is kept as a fallback for the one case the columns cannot
        answer: a tag stored before names were validated may carry "/" in its
        own name, and splitting its full path then lands on the wrong halves.
        A column hit is never wrong — both are written from the same model — so
        the fallback only ever runs on a miss.
        """
        parent_path, _, name = full_path.rpartition("/")
        async with use_session(self._sessions, session) as s:
            row = (
                (
                    await s.execute(
                        select(TagRow).where(
                            TagRow.owner_id == owner_id,
                            TagRow.type == tag_type.value,
                            TagRow.name == name,
                            TagRow.path == (parent_path or None),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                return self._row_to_tag(row)

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

    async def list_descendants(self, owner_id: str, tag_type: TagType, full_path: str, session: AsyncSession | None = None) -> List[Tag]:
        """Every folder nested under this path, at any depth, for one owner.

        Answered from the indexed path column: a library mirroring a source tree
        can hold hundreds of folders, and reading the owner's whole tree to find
        them would cost a table scan on every listing of that library.
        """
        # A folder's own name may contain LIKE's wildcards, so the prefix is
        # escaped and the escape character declared rather than assumed.
        escaped = full_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TagRow).where(
                        TagRow.owner_id == owner_id,
                        TagRow.type == tag_type.value,
                        or_(
                            TagRow.path == full_path,
                            TagRow.path.like(f"{escaped}/%", escape="\\"),
                        ),
                    )
                )
            ).scalars().all()
        return [self._row_to_tag(row) for row in rows]

    async def list_by_type(self, tag_type: str, session: AsyncSession | None = None) -> List[Tag]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TagRow).where(TagRow.type == tag_type))).scalars().all()
        return [self._row_to_tag(row) for row in rows]
