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

from knowledge_flow_backend.core.stores.resources.base_resource_store import (
    BaseResourceStore,
    ResourceNotFoundError,
)
from knowledge_flow_backend.core.stores.resources.resource_models import ResourceRow
from knowledge_flow_backend.features.resources.structures import Resource, ResourceKind

logger = logging.getLogger(__name__)


class PostgresResourceStore(BaseResourceStore):
    """PostgreSQL-backed resource store using declarative ORM."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    # --- helpers ---

    @staticmethod
    def _row_to_resource(row: ResourceRow) -> Resource:
        return Resource.model_validate(row.doc or {})

    # --- CRUD ---

    async def create_resource(self, resource: Resource, session: AsyncSession | None = None) -> Resource:
        async with use_session(self._sessions, session) as s:
            existing = await s.get(ResourceRow, resource.id)
            if existing:
                # Upsert: update in place
                existing.resource_name = resource.name
                existing.resource_type = resource.kind.value
                existing.author = resource.author
                existing.doc = resource.model_dump(mode="json")
            else:
                row = ResourceRow(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    resource_type=resource.kind.value,
                    author=resource.author,
                    doc=resource.model_dump(mode="json"),
                )
                s.add(row)
        return resource

    async def get_resource_by_id(self, resource_id: str, session: AsyncSession | None = None) -> Resource:
        async with use_session(self._sessions, session) as s:
            row = await s.get(ResourceRow, resource_id)
        if row is None:
            raise ResourceNotFoundError(f"Resource '{resource_id}' not found")
        return self._row_to_resource(row)

    async def update_resource(self, resource_id: str, resource: Resource, session: AsyncSession | None = None) -> Resource:
        async with use_session(self._sessions, session) as s:
            row = await s.get(ResourceRow, resource_id)
            if row is None:
                raise ResourceNotFoundError(f"Resource '{resource_id}' not found")
            row.resource_name = resource.name
            row.resource_type = resource.kind.value
            row.author = resource.author
            row.doc = resource.model_dump(mode="json")
        return resource

    async def delete_resource(self, resource_id: str, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(ResourceRow, resource_id)
            if row is None:
                raise ResourceNotFoundError(f"Resource '{resource_id}' not found")
            await s.delete(row)

    async def get_all_resources(self, kind: ResourceKind, session: AsyncSession | None = None) -> List[Resource]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(ResourceRow).where(ResourceRow.resource_type == kind.value))).scalars().all()
        return [self._row_to_resource(row) for row in rows]

    async def list_resources_for_user(self, user: str, kind: ResourceKind, session: AsyncSession | None = None) -> List[Resource]:
        return await self.get_all_resources(kind, session=session)

    async def get_resources_in_tag(self, tag_id: str, session: AsyncSession | None = None) -> List[Resource]:
        # Placeholder: tag relations not persisted in this simple schema.
        return []
