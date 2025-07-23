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

import json
from typing import List, Optional
from pathlib import Path
import logging

from fred_core.store.duckdb_store import DuckDBTableStore
from app.features.dynamic_agent.stores.base_agent_store import BaseDynamicAgentStore
from app.flow import AgentFlow
from app.features.dynamic_agent.mcp_agent import MCPAgent

logger = logging.getLogger(__name__)

class DuckdbMCPAgentStorage(BaseDynamicAgentStore):
    def __init__(self, db_path: Path):
        self.table_name = "mcp_agents"
        self.prefix = "_mcp_agents"
        self.store = DuckDBTableStore(prefix=self.prefix, db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.store._prefixed(self.table_name)} (
                    name TEXT PRIMARY KEY,
                    base_prompt TEXT,
                    role TEXT,
                    nickname TEXT,
                    description TEXT,
                    icon TEXT,
                    categories TEXT,
                    tag TEXT
                )
            """)

    def _serialize(self, agent: AgentFlow) -> tuple:
        return (
            agent.name,
            agent.base_prompt,
            agent.role,
            agent.nickname,
            agent.description,
            agent.icon,
            json.dumps(agent.categories) if agent.categories else None,
            agent.tag,
        )

    def _deserialize(self, row: tuple) -> AgentFlow:
        return MCPAgent(
            name=row[0],
            base_prompt=row[1],
            role=row[2],
            nickname=row[3],
            description=row[4],
            icon=row[5],
            categories=json.loads(row[6]) if row[6] else [],
            tag=row[7],
            cluster_fullname="", # Placeholder waiting to get rid of it as a non optional param in Agen8tFlow
        )

    def save(self, agent: AgentFlow) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.store._prefixed(self.table_name)} 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._serialize(agent),
            )
            logger.info(f"Agent {agent.name} saved in {self.table_name}")

    def get(self, name: str) -> Optional[AgentFlow]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.store._prefixed(self.table_name)} WHERE name = ?",
                (name,),
            ).fetchone()
        return self._deserialize(row) if row else None

    def load_all(self) -> List[AgentFlow]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.store._prefixed(self.table_name)}"
            ).fetchall()
        loaded_agents = [self._deserialize(row) for row in rows]
        logger.info(f"Fetched all dynamic agents: {loaded_agents}")
        return loaded_agents

    def delete(self, name: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"DELETE FROM {self.store._prefixed(self.table_name)} WHERE name = ?",
                (name,),
            )
