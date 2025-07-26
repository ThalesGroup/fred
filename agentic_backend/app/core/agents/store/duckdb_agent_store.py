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

from typing import List, Optional
from pathlib import Path
import logging

from app.core.agents.store.base_agent_store import BaseAgentStore
from pydantic import ValidationError
from app.common.structures import AgentSettings
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


class DuckdbAgentStorage(BaseAgentStore):
    def __init__(self, db_path: Path):
        self.table_name = "agents"
        self.store = DuckDBTableStore(prefix="", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.store._prefixed(self.table_name)} (
                    name TEXT PRIMARY KEY,
                    settings_json TEXT
                )
            """)

    def save(self, settings: AgentSettings) -> None:
        try:
            json_str = settings.model_dump_json()
        except Exception as e:
            raise ValueError(f"Failed to serialize AgentSettings for {settings.name}: {e}")

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.store._prefixed(self.table_name)} (name, settings_json)
                VALUES (?, ?)
                """,
                (settings.name, json_str),
            )
        logger.info(f"✅ AgentSettings for '{settings.name}' saved to DuckDB")

    def get(self, name: str) -> Optional[AgentSettings]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT settings_json FROM {self.store._prefixed(self.table_name)} WHERE name = ?",
                (name,),
            ).fetchone()
        if row:
            try:
                return AgentSettings.parse_raw(row[0])
            except ValidationError as e:
                logger.error(f"❌ Failed to parse AgentSettings for '{name}': {e}")
        return None

    def load_all(self) -> List[AgentSettings]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT settings_json FROM {self.store._prefixed(self.table_name)}"
            ).fetchall()
        settings_list = []
        for row in rows:
            try:
                settings = AgentSettings.parse_raw(row[0])
                settings_list.append(settings)
            except ValidationError as e:
                logger.error(f"❌ Skipping malformed AgentSettings: {e}")
        logger.info(f"✅ Loaded {len(settings_list)} agent settings from DuckDB")
        return settings_list

    def delete(self, name: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"DELETE FROM {self.store._prefixed(self.table_name)} WHERE name = ?",
                (name,),
            )
        logger.info(f"🗑️ AgentSettings for '{name}' deleted from DuckDB")
