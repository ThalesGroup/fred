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
from typing import List, Optional

from fred_core.sql import BaseSqlStore
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from pydantic import TypeAdapter

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore

logger = logging.getLogger(__name__)

McpServerAdapter = TypeAdapter(MCPServerConfiguration)


class PostgresMcpServerStore(BaseMcpServerStore):
    """
    PostgreSQL-backed MCP server store using JSONB.
    Schema mirrors DuckDB/OpenSearch variants.
    """

    def __init__(self, engine: Engine, table_name: str, prefix: str = "mcp_"):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._seed_marker_id = "__static_seeded__"

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("server_id", String, primary_key=True),
            Column("payload_json", JSONB),
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[MCP][PG] Table ready: %s", self.table_name)

    def load_all(self) -> List[MCPServerConfiguration]:
        with self.store.begin() as conn:
            rows = conn.execute(
                select(self.table.c.server_id, self.table.c.payload_json)
            ).fetchall()

        servers: List[MCPServerConfiguration] = []
        for server_id, payload in rows:
            if server_id == self._seed_marker_id:
                continue
            try:
                data = payload if payload is not None else {}
                servers.append(McpServerAdapter.validate_python(data))
            except Exception:
                logger.exception(
                    "[STORE][PG][MCP] Failed to parse payload for server id=%s",
                    server_id,
                )
        return servers

    def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        if server_id == self._seed_marker_id:
            return None
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.payload_json).where(
                    self.table.c.server_id == server_id
                )
            ).fetchone()
        if not row:
            return None
        try:
            payload = row[0] if row[0] is not None else {}
            return McpServerAdapter.validate_python(payload)
        except Exception:
            logger.exception("[STORE][PG][MCP] Failed to parse server id=%s", server_id)
            return None

    def save(self, server: MCPServerConfiguration) -> None:
        values = {
            "server_id": server.id,
            "payload_json": McpServerAdapter.dump_python(
                server, mode="json", exclude_none=True
            ),
        }
        with self.store.begin() as conn:
            self.store.upsert(conn, self.table, values, pk_cols=["server_id"])
        logger.debug("[STORE][PG][MCP] Saved server id=%s", server.id)

    def delete(self, server_id: str) -> None:
        if server_id == self._seed_marker_id:
            logger.info("[STORE][PG][MCP] Seed marker delete skipped")
            return
        with self.store.begin() as conn:
            result = conn.execute(
                self.table.delete().where(self.table.c.server_id == server_id)
            )
        deleted = getattr(result, "rowcount", None)
        if deleted == 0:
            logger.warning("[STORE][PG][MCP] Server id=%s not found", server_id)
        else:
            logger.info("[STORE][PG][MCP] Deleted server id=%s", server_id)

    def static_seeded(self) -> bool:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.server_id)
                .where(self.table.c.server_id == self._seed_marker_id)
                .limit(1)
            ).fetchone()
        return bool(row)

    def mark_static_seeded(self) -> None:
        marker = {
            "server_id": self._seed_marker_id,
            "payload_json": {},
        }
        with self.store.begin() as conn:
            self.store.upsert(
                conn,
                self.table,
                marker,
                pk_cols=["server_id"],
                update_cols=[],
            )
