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

import json
import logging
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import TypeAdapter

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore

logger = logging.getLogger(__name__)

McpServerAdapter = TypeAdapter(MCPServerConfiguration)


class DuckDBMcpServerStore(BaseMcpServerStore):
    """
    Simple DuckDB-backed MCP server store.
    """

    TABLE = "mcp_servers"

    def __init__(self, db_path: Path):
        self.store = DuckDBTableStore(prefix="mcp_servers_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.store._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT
                )
                """
            )

    def save(self, server: MCPServerConfiguration) -> None:
        payload_json = json.dumps(
            McpServerAdapter.dump_python(server, mode="json", exclude_none=True)
        )
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mcp_servers (id, payload_json) VALUES (?, ?)",
                (server.id, payload_json),
            )
        logger.debug("[STORE][DUCKDB][MCP] Saved server id=%s", server.id)

    def load_all(self) -> List[MCPServerConfiguration]:
        with self.store._connect() as conn:
            rows = conn.execute("SELECT payload_json FROM mcp_servers").fetchall()

        servers: List[MCPServerConfiguration] = []
        for (payload,) in rows:
            try:
                data = json.loads(payload) if payload else {}
                servers.append(McpServerAdapter.validate_python(data))
            except Exception:
                logger.exception(
                    "[STORE][DUCKDB][MCP] Failed to parse MCP server payload"
                )
        return servers

    def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM mcp_servers WHERE id = ?",
                (server_id,),
            ).fetchone()

        if not row:
            return None
        try:
            data = json.loads(row[0]) if row[0] else {}
            return McpServerAdapter.validate_python(data)
        except Exception:
            logger.exception(
                "[STORE][DUCKDB][MCP] Failed to parse MCP server id=%s", server_id
            )
            return None

    def delete(self, server_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
        logger.info("[STORE][DUCKDB][MCP] Deleted server id=%s", server_id)
