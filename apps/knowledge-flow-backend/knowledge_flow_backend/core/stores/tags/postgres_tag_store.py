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
from datetime import datetime, timezone
from typing import List

from fred_core.documents.tag_models import TagRow, tag_full_path_expression
from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from knowledge_flow_backend.core.stores.tags.base_tag_store import (
    BaseTagStore,
    TagAlreadyExistsError,
    TagDeserializationError,
    TagNotFoundError,
)
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy, CorpusLifecycle
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
            return Tag.model_validate({**(row.doc or {}), "id": row.tag_id, "owner_id": row.owner_id, "name": row.name, "path": row.path, "type": row.type, "deletion_task_id": row.deletion_task_id})
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

    async def list_by_owner(self, owner_id: str, *, path_prefix: str | None = None, limit: int | None = None, offset: int = 0) -> list[Tag]:
        full_path = tag_full_path_expression()
        query = select(TagRow).where(TagRow.owner_id == owner_id, TagRow.type == TagType.DOCUMENT.value, TagRow.deletion_task_id.is_(None))
        if path_prefix:
            query = query.where(or_(full_path == path_prefix, full_path.startswith(path_prefix + "/", autoescape=True)))
        query = query.order_by(func.lower(full_path), TagRow.tag_id).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        async with use_session(self._sessions) as session:
            rows = (await session.scalars(query)).all()
        return [self._row_to_tag(row) for row in rows]

    async def get_tag_by_id(self, tag_id: str, session: AsyncSession | None = None) -> Tag:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TagRow, tag_id)
        if row is None:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        return self._row_to_tag(row)

    async def create_tag(self, tag: Tag, session: AsyncSession | None = None) -> Tag:
        tid = self._require_id(tag)
        async with use_session(self._sessions, session) as s:
            if tag.path:
                parent = await self.get_by_owner_type_full_path(tag.owner_id, tag.type, tag.path, session=s)
                if parent is None:
                    raise TagNotFoundError(f"Parent folder '{tag.path}' not found")
                locked_parent = (await CorpusLifecycle.lock_folders(s, {parent.id}))[0]
                if self._row_to_tag(locked_parent).full_path != tag.path:
                    raise CorpusBusy("The parent folder was renamed. Refresh before creating a subfolder.")
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

    async def get_tags_by_ids(self, tag_ids: list[str]) -> list[Tag]:
        if not tag_ids:
            return []
        async with use_session(self._sessions) as session:
            rows = (await session.scalars(select(TagRow).where(TagRow.tag_id.in_(tag_ids)))).all()
        return [self._row_to_tag(row) for row in rows]

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

    async def rename_tag(self, tag_id: str, *, name: str, description: str | None) -> Tag:
        try:
            async with use_session(self._sessions) as session:
                folder = (await CorpusLifecycle.lock_folders(session, {tag_id}))[0]
                tree = await CorpusLifecycle.subtree(session, folder) if folder.name != name else [folder]
                if any(row.deletion_task_id is not None for row in tree):
                    raise CorpusBusy("A folder in this tree is being deleted")
                old_path = f"{folder.path}/{folder.name}" if folder.path else folder.name
                new_path = f"{folder.path}/{name}" if folder.path else name
                now = datetime.now(timezone.utc)
                for row in tree:
                    if row.tag_id == tag_id:
                        row.name = name
                        row.description = description
                    else:
                        row.path = new_path + (row.path or "")[len(old_path or "") :]
                    row.updated_at = now
                    row.doc = {**(row.doc or {}), "name": row.name, "path": row.path, "description": row.description, "updated_at": now.isoformat()}
                await session.flush()
                renamed = self._row_to_tag(folder)
            return renamed
        except IntegrityError as exc:
            if "uq_tag_owner_full_path" in str(exc.orig):
                raise TagAlreadyExistsError("A folder with this name already exists") from exc
            raise

    async def touch_tag(self, tag_id: str) -> None:
        async with use_session(self._sessions) as session:
            row = await session.get(TagRow, tag_id, with_for_update=True)
            if row is None:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            now = datetime.now(timezone.utc)
            row.updated_at = now
            row.doc = {**(row.doc or {}), "updated_at": now.isoformat()}

    async def delete_tag_by_id(self, tag_id: str, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(TagRow, tag_id)
            if row is None:
                raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
            await s.delete(row)

    async def get_by_owner_type_full_path(self, owner_id: str, tag_type: TagType, full_path: str, session: AsyncSession | None = None) -> Tag | None:
        """Resolve the persisted, unique full path through its SQL index."""
        full_path_column = tag_full_path_expression()
        async with use_session(self._sessions, session) as s:
            row = (await s.scalars(select(TagRow).where(TagRow.owner_id == owner_id, TagRow.type == tag_type.value, full_path_column == full_path))).one_or_none()
        return self._row_to_tag(row) if row is not None else None

    # --- convenience helpers ---

    async def list_all(self, session: AsyncSession | None = None) -> List[Tag]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TagRow))).scalars().all()
        return [self._row_to_tag(row) for row in rows]

    async def list_by_type(self, tag_type: str, session: AsyncSession | None = None) -> List[Tag]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(TagRow).where(TagRow.type == tag_type))).scalars().all()
        return [self._row_to_tag(row) for row in rows]
