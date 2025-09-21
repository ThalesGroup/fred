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

from fred_core import Action, KeycloakUser, Resource, authorize

from app.application_context import get_agent_store
from app.common.structures import AgentSettings
from app.core.agents.agent_manager import AgentManager


# --- Domain Exceptions ---
class AgentAlreadyExistsException(Exception):
    pass


class AgentService:
    def __init__(self, agent_manager: AgentManager):
        self.store = get_agent_store()
        self.agent_manager = agent_manager

    @authorize(action=Action.CREATE, resource=Resource.AGENTS)
    async def create_agent(
        self, user: KeycloakUser, agent_settings: AgentSettings
    ):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        # 1. Create config
        # agent_settings = AgentSettings(
        #     type=req.agent_type,
        #     name=req.name,
        #     class_path=get_class_path(MCPAgent),
        #     enabled=True,
        #     categories=req.categories or [],
        #     tag=req.tag or "mcp",
        #     mcp_servers=req.mcp_servers,
        #     description=req.description,
        #     base_prompt=req.base_prompt,
        #     role=req.role,
        #     icon=req.icon,
        #     model=ModelConfiguration(),  # empty
        #     settings={},
        # )
        # Fill in model from default if not specified
        # agent_settings = get_app_context().apply_default_model_to_agent(agent_settings)
        # # 3. Instantiate and init
        # agent_instance = MCPAgent(
        #     agent_settings=agent_settings,
        # )
        # await agent_instance.async_init()

        # # 4. Persist
        # self.store.save(agent_settings)
        # self.agent_manager.register_dynamic_agent(agent_instance, agent_settings)
        # # 5. Register live

        # return JSONResponse(content=agent_instance.to_dict())
        raise NotImplementedError("MCP agent creation is being revamped.")

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def update_agent(
        self, user: KeycloakUser, agent_settings: AgentSettings
    ):
        # Delete existing agent (if any)
        #await self.agent_manager.unregister_agent(agent_settings)
        #self.store.delete(agent_settings.name)

        # Recreate it using the same logic as in create
        #return await self.build_and_register_mcp_agent(user, agent_settings)
        self.agent_manager.update_agent(agent_settings)

    @authorize(action=Action.DELETE, resource=Resource.AGENTS)
    async def delete_agent(self, user: KeycloakUser, agent_name: str):
        # Unregister from memory
        await self.agent_manager.unregister_agent(agent_name)

        # Delete from DuckDB
        self.store.delete(agent_name)

        return {"message": f"✅ Agent '{agent_name}' deleted successfully."}
