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

import logging
from pathlib import Path
from typing import Iterable

from fred_core.store.duckdb_store import DuckDBTableStore

from knowledge_flow_backend.core.stores.groups.base_group_store import BaseGroupStore
from knowledge_flow_backend.features.groups.groups_structures import GroupProfile

logger = logging.getLogger(__name__)


class DuckdbGroupStore(BaseGroupStore):
    """
    DuckDB implementation of BaseGroupStore.
    """

    def __init__(self, db_path: Path):
        self.table_name = "profiles"
        self.store = DuckDBTableStore(db_path, prefix="group_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self._table()}" (
                    group_id TEXT PRIMARY KEY,
                    banner_image_url TEXT,
                    is_private BOOLEAN,
                    description TEXT
                )
                """
            )

            cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{self._table()}")').fetchall()}
            if "banner_image_url" not in cols:
                conn.execute(f'ALTER TABLE "{self._table()}" ADD COLUMN banner_image_url TEXT')
            if "is_private" not in cols:
                conn.execute(f'ALTER TABLE "{self._table()}" ADD COLUMN is_private BOOLEAN')
            if "description" not in cols:
                conn.execute(f'ALTER TABLE "{self._table()}" ADD COLUMN description TEXT')

        logger.info("[GROUPS] DuckDB table '%s' ensured.", self._table())

    def get_group_profile(self, group_id: str) -> GroupProfile | None:
        with self.store._connect() as conn:
            row = conn.execute(
                f"""
                SELECT group_id, banner_image_url, is_private, description
                FROM "{self._table()}"
                WHERE group_id = ?
                """,
                [group_id],
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

        placeholders = ", ".join(["?"] * len(ids))
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT group_id, banner_image_url, is_private, description
                FROM "{self._table()}"
                WHERE group_id IN ({placeholders})
                """,
                ids,
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
