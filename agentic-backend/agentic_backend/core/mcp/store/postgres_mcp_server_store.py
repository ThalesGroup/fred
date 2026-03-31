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
from typing import List, Optional, cast

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore
from agentic_backend.core.mcp.store.mcp_server_models import McpServerRow

logger = logging.getLogger(__name__)

McpServerAdapter = TypeAdapter(MCPServerConfiguration)


class PostgresMcpServerStore(BaseMcpServerStore):
    """
    PostgreSQL-backed MCP server store using JSONB (ORM sessions).
    """

    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)
        self._seed_marker_id = "__static_seeded__"

    async def load_all(
        self, session: AsyncSession | None = None
    ) -> List[MCPServerConfiguration]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(McpServerRow))).scalars().all()

        servers: List[MCPServerConfiguration] = []
        for row in rows:
            if row.server_id == self._seed_marker_id:
                continue
            try:
                data = row.payload_json if row.payload_json is not None else {}
                servers.append(McpServerAdapter.validate_python(data))
            except Exception:
                logger.exception(
                    "[STORE][PG][MCP] Failed to parse payload for server id=%s",
                    row.server_id,
                )
        return servers

    async def get(
        self, server_id: str, session: AsyncSession | None = None
    ) -> Optional[MCPServerConfiguration]:
        if server_id == self._seed_marker_id:
            return None
        async with use_session(self._sessions, session) as s:
            row = await s.get(McpServerRow, server_id)
        if row is None:
            return None
        try:
            data = row.payload_json if row.payload_json is not None else {}
            return McpServerAdapter.validate_python(data)
        except Exception:
            logger.exception("[STORE][PG][MCP] Failed to parse server id=%s", server_id)
            return None

    async def save(
        self, server: MCPServerConfiguration, session: AsyncSession | None = None
    ) -> None:
        row = McpServerRow(
            server_id=server.id,
            payload_json=McpServerAdapter.dump_python(
                server, mode="json", exclude_none=True
            ),
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)
        logger.debug("[STORE][PG][MCP] Saved server id=%s", server.id)

    async def delete(self, server_id: str, session: AsyncSession | None = None) -> None:
        if server_id == self._seed_marker_id:
            logger.info("[STORE][PG][MCP] Seed marker delete skipped")
            return
        async with use_session(self._sessions, session) as s:
            result = cast(
                CursorResult,
                await s.execute(
                    delete(McpServerRow).where(McpServerRow.server_id == server_id)
                ),
            )
        if result.rowcount == 0:
            logger.warning("[STORE][PG][MCP] Server id=%s not found", server_id)
        else:
            logger.info("[STORE][PG][MCP] Deleted server id=%s", server_id)

    async def static_seeded(self, session: AsyncSession | None = None) -> bool:
        async with use_session(self._sessions, session) as s:
            row = await s.get(McpServerRow, self._seed_marker_id)
        return row is not None

    async def mark_static_seeded(self, session: AsyncSession | None = None) -> None:
        row = McpServerRow(server_id=self._seed_marker_id, payload_json={})
        async with use_session(self._sessions, session) as s:
            await s.merge(row)
