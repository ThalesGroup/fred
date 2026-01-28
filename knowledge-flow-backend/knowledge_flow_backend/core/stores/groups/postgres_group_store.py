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
from collections.abc import Iterable

from fred_core.sql import BaseSqlStore
from sqlalchemy import Boolean, Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from knowledge_flow_backend.core.stores.groups.base_group_store import BaseGroupStore
from knowledge_flow_backend.features.groups.groups_structures import GroupProfile

logger = logging.getLogger(__name__)


class PostgresGroupStore(BaseGroupStore):
    """
    PostgreSQL-backed store for group profiles.
    """

    def __init__(self, engine: Engine, table_name: str, prefix: str):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("group_id", String, primary_key=True),
            Column("banner_image_url", String),
            Column("is_private", Boolean),
            Column("description", String),
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[GROUPS][PG] Table ready: %s", self.table_name)

    def get_group_profile(self, group_id: str) -> GroupProfile | None:
        with self.store.begin() as conn:
            row = conn.execute(
                select(
                    self.table.c.group_id,
                    self.table.c.banner_image_url,
                    self.table.c.is_private,
                    self.table.c.description,
                ).where(self.table.c.group_id == group_id)
            ).fetchone()

        if not row:
            return None

        return GroupProfile(
            id=row[0],
            banner_image_url=row[1],
            is_private=row[2],
            description=row[3],
        )

    def list_group_profiles(self, group_ids: Iterable[str]) -> dict[str, GroupProfile]:
        ids = [group_id for group_id in group_ids if group_id]
        if not ids:
            return {}

        with self.store.begin() as conn:
            rows = conn.execute(
                select(
                    self.table.c.group_id,
                    self.table.c.banner_image_url,
                    self.table.c.is_private,
                    self.table.c.description,
                ).where(self.table.c.group_id.in_(ids))
            ).fetchall()

        return {
            row[0]: GroupProfile(
                id=row[0],
                banner_image_url=row[1],
                is_private=row[2],
                description=row[3],
            )
            for row in rows
        }

    def upsert_group_profile(self, profile: GroupProfile) -> None:
        values = {
            "group_id": profile.id,
            "banner_image_url": profile.banner_image_url,
            "is_private": profile.is_private,
            "description": profile.description,
        }
        with self.store.begin() as conn:
            upsert_query = pg_insert(self.table).values(**values)
            upsert_query = upsert_query.on_conflict_do_update(
                index_elements=[self.table.c.group_id],
                set_={
                    "banner_image_url": values["banner_image_url"],
                    "is_private": values["is_private"],
                    "description": values["description"],
                },
            )
            conn.execute(upsert_query)
