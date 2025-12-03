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

    def bootstrap(self) -> None:
        self.static_servers = {srv.id: srv for srv in self.config.mcp.servers}
        if self.use_static_config_only:
            logger.warning(
                "[MCP] Static-config-only is enabled. Skipping persisted MCP servers."
            )
            merged = dict(self.static_servers)
        else:
            persisted = {srv.id: srv for srv in self.store.load_all()}
            merged = dict(self.static_servers)
            merged.update(persisted)

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

    def upsert(self, server: MCPServerConfiguration) -> None:
        if self.use_static_config_only:
            raise McpUpdatesDisabled()
        self.store.save(server)
        self.servers[server.id] = server
        self._sync_config()
        logger.info("[MCP] Saved server id=%s", server.id)

    def delete(self, server_id: str) -> None:
        if self.use_static_config_only:
            raise McpUpdatesDisabled()
        self.store.delete(server_id)
        self.servers.pop(server_id, None)

        # Restore static definition if it exists
        if server_id in self.static_servers:
            self.servers[server_id] = self.static_servers[server_id]
            logger.info(
                "[MCP] Removed persisted override for static server id=%s", server_id
            )
        else:
            logger.info("[MCP] Deleted persisted server id=%s", server_id)

        self._sync_config()

    def _sync_config(self) -> None:
        # Keep application-wide configuration in sync for downstream consumers.
        self.config.mcp.servers = list(self.servers.values())
