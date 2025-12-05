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

        # Special marker row id used to avoid reseeding static servers after first init
        self._seed_marker_id = "__static_seeded__"

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
            try:
                conn.execute("BEGIN")
                conn.execute(
                    "INSERT OR REPLACE INTO mcp_servers (id, payload_json) VALUES (?, ?)",
                    (server.id, payload_json),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                logger.exception(
                    "[STORE][DUCKDB][MCP] Failed to save server id=%s", server.id
                )
                raise
        logger.debug("[STORE][DUCKDB][MCP] Saved server id=%s", server.id)

    def load_all(self) -> List[MCPServerConfiguration]:
        with self.store._connect() as conn:
            rows = conn.execute("SELECT id, payload_json FROM mcp_servers").fetchall()

        servers: List[MCPServerConfiguration] = []
        for row_id, payload in rows:
            if row_id == self._seed_marker_id:
                continue
            try:
                data = json.loads(payload) if payload else {}
                servers.append(McpServerAdapter.validate_python(data))
            except Exception:
                logger.exception(
                    "[STORE][DUCKDB][MCP] Failed to parse MCP server payload"
                )
        return servers

    def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        if server_id == self._seed_marker_id:
            return None
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
            try:
                conn.execute("BEGIN")
                result = conn.execute(
                    "DELETE FROM mcp_servers WHERE id = ?", (server_id,)
                )
                conn.execute("COMMIT")
                deleted = getattr(result, "rowcount", None)
                if deleted == 0:
                    logger.warning(
                        "[STORE][DUCKDB][MCP] Server id=%s not found for deletion",
                        server_id,
                    )
                elif deleted is None or deleted < 0:
                    logger.info(
                        "[STORE][DUCKDB][MCP] Delete issued for server id=%s "
                        "(rowcount unavailable)",
                        server_id,
                    )
                else:
                    logger.info("[STORE][DUCKDB][MCP] Deleted server id=%s", server_id)
            except Exception:
                conn.execute("ROLLBACK")
                logger.exception(
                    "[STORE][DUCKDB][MCP] Failed to delete server id=%s", server_id
                )
                raise

    def static_seeded(self) -> bool:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM mcp_servers WHERE id = ? LIMIT 1",
                (self._seed_marker_id,),
            ).fetchone()
        return bool(row)

    def mark_static_seeded(self) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mcp_servers (id, payload_json) VALUES (?, ?)",
                (self._seed_marker_id, "{}"),
            )
