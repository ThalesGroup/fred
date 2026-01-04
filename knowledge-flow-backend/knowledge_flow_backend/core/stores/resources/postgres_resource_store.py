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
from typing import Any, List

from fred_core.sql import BaseSqlStore
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from knowledge_flow_backend.core.stores.resources.base_resource_store import (
    BaseResourceStore,
    ResourceNotFoundError,
)
from knowledge_flow_backend.features.resources.structures import Resource, ResourceKind

logger = logging.getLogger(__name__)


class PostgresResourceStore(BaseResourceStore):
    """
    PostgreSQL-backed resource store using JSONB.
    """

    def __init__(self, engine: Engine, table_name: str, prefix: str):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("resource_id", String, primary_key=True),
            Column("resource_name", String, index=True),
            Column("resource_type", String, index=True),
            Column("author", String, index=True),
            Column("doc", JSONB),
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[RESOURCES][PG] Table ready: %s", self.table_name)

    def _from_dict(self, data: Any) -> Resource:
        return Resource.model_validate(data or {})

    # --- CRUD ---

    def create_resource(self, resource: Resource) -> Resource:
        values = {
            "resource_id": resource.id,
            "resource_name": resource.name,
            "resource_type": resource.kind.value,
            "author": resource.author,
            "doc": resource.model_dump(mode="json"),
        }
        with self.store.begin() as conn:
            self.store.upsert(conn, self.table, values, pk_cols=["resource_id"])
        return resource

    def get_resource_by_id(self, resource_id: str) -> Resource:
        with self.store.begin() as conn:
            row = conn.execute(select(self.table.c.doc).where(self.table.c.resource_id == resource_id)).fetchone()
        if not row:
            raise ResourceNotFoundError(f"Resource '{resource_id}' not found")
        return self._from_dict(row[0])

    def update_resource(self, resource_id: str, resource: Resource) -> Resource:
        self.get_resource_by_id(resource_id)  # ensure exists
        values = {
            "resource_id": resource.id,
            "resource_name": resource.name,
            "resource_type": resource.kind.value,
            "author": resource.author,
            "doc": resource.model_dump(mode="json"),
        }
        with self.store.begin() as conn:
            self.store.upsert(conn, self.table, values, pk_cols=["resource_id"])
        return resource

    def delete_resource(self, resource_id: str) -> None:
        with self.store.begin() as conn:
            result = conn.execute(self.table.delete().where(self.table.c.resource_id == resource_id))
            if result.rowcount == 0:
                raise ResourceNotFoundError(f"Resource '{resource_id}' not found")

    def get_all_resources(self, kind: ResourceKind) -> List[Resource]:
        with self.store.begin() as conn:
            rows = conn.execute(select(self.table.c.doc).where(self.table.c.resource_type == kind.value)).fetchall()
        return [self._from_dict(r[0]) for r in rows]

    def list_resources_for_user(self, user: str, kind: ResourceKind) -> List[Resource]:
        # If we add owner scoping later, we can store owner_id; currently no owner field in Postgres schema.
        # Align with other stores: filter by kind only (since owner not persisted here).
        return self.get_all_resources(kind)

    def get_resources_in_tag(self, tag_id: str) -> List[Resource]:
        # Placeholder: tag relations not persisted in this simple schema.
        return []
