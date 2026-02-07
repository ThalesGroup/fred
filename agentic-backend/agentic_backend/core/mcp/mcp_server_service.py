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

from fred_core import Action, KeycloakUser, Resource, authorize

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.mcp_server_manager import (
    McpServerManager,
    McpServerNotFound,
)

logger = logging.getLogger(__name__)


class McpServerService:
    def __init__(self, manager: McpServerManager):
        self.manager = manager

    @authorize(action=Action.CREATE, resource=Resource.MCP_SERVERS)
    async def create_server(
        self, user: KeycloakUser, server: MCPServerConfiguration
    ) -> None:
        await self.save_server(user, server, allow_upsert=False)

    @authorize(action=Action.UPDATE, resource=Resource.MCP_SERVERS)
    async def save_server(
        self,
        user: KeycloakUser,
        server: MCPServerConfiguration,
        allow_upsert: bool = True,
    ) -> None:
        existing = self.manager.get(server.id)
        if existing and not allow_upsert:
            raise ValueError(f"MCP server '{server.id}' already exists.")
        if not existing and not allow_upsert:
            # no specific action; create path will handle absence
            pass
        await self.manager.upsert(server)

    @authorize(action=Action.DELETE, resource=Resource.MCP_SERVERS)
    async def delete_server(self, user: KeycloakUser, server_id: str) -> None:
        if not self.manager.get(server_id):
            raise McpServerNotFound(f"MCP server '{server_id}' not found.")
        await self.manager.delete(server_id)

    @authorize(action=Action.UPDATE, resource=Resource.MCP_SERVERS)
    async def restore_static_servers(self, user: KeycloakUser) -> None:
        await self.manager.restore_static_servers()
