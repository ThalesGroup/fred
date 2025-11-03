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

from agentic_backend.application_context import get_agent_store
from agentic_backend.common.structures import Agent, AgentSettings
from agentic_backend.core.agents.agent_manager import (
    AgentAlreadyExistsException,
    AgentManager,
)
from agentic_backend.core.agents.mcp_agent import MCP_TUNING, MCPAgent

logger = logging.getLogger(__name__)


def _class_path(obj_or_type) -> str:
    """Return fully-qualified class path, e.g. 'agentic_backend.agents.mcp.mcp_agent.MCPAgent'."""
    t = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
    return f"{t.__module__}.{t.__name__}"


class AgentService:
    def __init__(self, agent_manager: AgentManager):
        self.store = get_agent_store()
        self.agent_manager = agent_manager

    @authorize(action=Action.CREATE, resource=Resource.AGENTS)
    async def create_mcp_agent(self, user: KeycloakUser, name: str):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        # Guard: disallow duplicates at the store level
        try:
            existing = self.store.get(name)
            if existing:
                raise AgentAlreadyExistsException(f"Agent '{name}' already exists.")
        except Exception as e:
            # If .get raises when not found, ignore; if it returns None when not found, also fine
            raise e

        # Ensure class_path points to MCPAgent
        agent_settings = Agent(
            name=name,
            class_path=_class_path(MCPAgent),
            enabled=False,  # Start disabled until fully initialized
            tuning=MCP_TUNING,  # default tuning
            mcp_servers=[],  # Empty list by default; to be configured later
        )
        self.agent_manager.create_dynamic_agent(agent_settings, MCP_TUNING)

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def update_agent(
        self, user: KeycloakUser, agent_settings: AgentSettings, is_global: bool
    ):
        # Delete existing agent (if any)
        # await self.agent_manager.unregister_agent(agent_settings)
        # self.store.delete(agent_settings.name)

        # Recreate it using the same logic as in create
        # return await self.build_and_register_mcp_agent(user, agent_settings)
        await self.agent_manager.update_agent(
            new_settings=agent_settings, is_global=is_global
        )
        self.agent_manager.log_current_settings()

    @authorize(action=Action.DELETE, resource=Resource.AGENTS)
    async def delete_agent(self, user: KeycloakUser, agent_name: str):
        # Unregister from memory
        await self.agent_manager.delete_agent(agent_name)

        # Delete from DuckDB
        self.store.delete(agent_name)

        return {"message": f"✅ Agent '{agent_name}' deleted successfully."}
