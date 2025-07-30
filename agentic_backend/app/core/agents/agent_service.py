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

from app.common.structures import AgentSettings, ModelConfiguration
from app.common.utils import get_class_path
from app.core.agents.agent_manager import AgentManager
from fastapi.responses import JSONResponse
from app.core.agents.mcp_agent import MCPAgent
from app.core.agents.structures import CreateAgentRequest, MCPAgentRequest
from app.application_context import get_agent_store, get_app_context

# --- Domain Exceptions ---
class AgentAlreadyExistsException(Exception):
    pass

class AgentService:

    def __init__(self, agent_manager: AgentManager):
        self.store = get_agent_store()
        self.agent_manager = agent_manager

    async def build_and_register_mcp_agent(self, req: MCPAgentRequest):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
         # 1. Create config
        agent_settings = AgentSettings(
            type=req.agent_type,
            name=req.name,
            class_path=get_class_path(MCPAgent),  
            enabled=True,
            categories=req.categories or [],
            tag=req.tag or "mcp",
            mcp_servers=req.mcp_servers,
            description=req.description,
            base_prompt=req.base_prompt,
            nickname=req.nickname,
            role=req.role,
            icon=req.icon,
            model=ModelConfiguration(),  # empty
            settings={},
        )

        # Fill in model from default if not specified
        agent_settings = get_app_context().apply_default_model_to_agent(agent_settings)
        # 3. Instantiate and init
        agent_instance = MCPAgent(
            agent_settings=agent_settings,
        )
        await agent_instance.async_init()

        # 4. Persist
        self.store.save(agent_settings)
        self.agent_manager.register_dynamic_agent(agent_instance, agent_settings)
         # 5. Register live

        return JSONResponse(content=agent_instance.to_dict())

    async def update_agent(self, name: str, req: CreateAgentRequest):   
            if name != req.name:
                raise ValueError("Agent name in URL and body must match.")

            # Delete existing agent (if any)
            self.agent_manager.unregister_agent(name)
            self.store.delete(name)

            # Recreate it using the same logic as in create
            return await self.build_and_register_mcp_agent(req)
    
    def delete_agent(self, name: str):
        # Unregister from memory
        self.agent_manager.unregister_agent(name)

        # Delete from DuckDB
        self.store.delete(name)

        return {"message": f"✅ Agent '{name}' deleted successfully."}
