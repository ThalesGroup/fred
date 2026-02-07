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
from typing import Dict, List, Optional

from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore

logger = logging.getLogger(__name__)


class McpUpdatesDisabled(Exception):
    """Raised when MCP server updates are attempted in static-only mode."""

    pass


class McpServerNotFound(Exception):
    pass


class McpServerManager:
    """
    Maintains the catalog of MCP servers by merging static configuration with
    persisted overrides from the configured store.
    """

    def __init__(self, config: Configuration, store: BaseMcpServerStore):
        self.config = config
        self.store = store
        self.static_servers: Dict[str, MCPServerConfiguration] = {}
        self.servers: Dict[str, MCPServerConfiguration] = {}
        self.use_static_config_only = config.ai.use_static_config_only

    async def bootstrap(self) -> None:
        self.static_servers = {srv.id: srv for srv in self.config.mcp.servers}
        if self.use_static_config_only:
            logger.warning(
                "[MCP] Static-config-only is enabled. Skipping persisted MCP servers."
            )
            merged = dict(self.static_servers)
        else:
            persisted = {srv.id: srv for srv in await self.store.load_all()}

            # Reconcile static servers on every bootstrap (new or changed entries)
            for srv_id, srv in self.static_servers.items():
                persisted_srv = persisted.get(srv_id)
                if persisted_srv != srv:
                    await self.store.save(srv)
                    persisted[srv_id] = srv
                    logger.info(
                        "[MCP] Upserted static server id=%s into storage (new or updated)",
                        srv_id,
                    )
            await self.store.mark_static_seeded()

            merged = dict(persisted)

        self.servers = merged
        self._sync_config()
        logger.info(
            "[MCP] Catalog initialized with %d servers (static=%d, persisted=%d)",
            len(self.servers),
            len(self.static_servers),
            len(self.servers) - len(self.static_servers),
        )

    def list_servers(
        self, include_disabled: bool = False
    ) -> List[MCPServerConfiguration]:
        if include_disabled:
            return list(self.servers.values())
        # Treat servers as enabled unless they are explicitly disabled.
        return [s for s in self.servers.values() if s.enabled is not False]

    def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        return self.servers.get(server_id)

    async def upsert(self, server: MCPServerConfiguration) -> None:
        if self.use_static_config_only:
            raise McpUpdatesDisabled()
        await self.store.save(server)
        self.servers[server.id] = server
        self._sync_config()
        logger.info("[MCP] Saved server id=%s", server.id)

    async def delete(self, server_id: str) -> None:
        if self.use_static_config_only:
            raise McpUpdatesDisabled()
        await self.store.delete(server_id)
        self.servers.pop(server_id, None)
        logger.info("[MCP] Deleted server id=%s", server_id)

        self._sync_config()

    def _sync_config(self) -> None:
        # Keep application-wide configuration in sync for downstream consumers.
        self.config.mcp.servers = list(self.servers.values())

    async def restore_static_servers(self) -> None:
        """
        Re-apply static configuration to the store, re-enabling any static servers that
        were disabled or removed by a persisted override. Dynamic servers are left as-is.
        """
        if self.use_static_config_only:
            # In static-only mode we never persisted overrides, so nothing to restore.
            return

        for srv_id, srv in self.static_servers.items():
            await self.store.save(srv)
            self.servers[srv_id] = srv
            logger.info("[MCP] Restored static server id=%s from configuration", srv_id)

        await self.store.mark_static_seeded()
        self._sync_config()
