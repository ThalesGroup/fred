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

from fastapi.responses import JSONResponse
from app.core.agents.mcp_agent import MCPAgent
from app.core.agents.mcp_agent_structures import MCPAgentRequest
from app.application_context import get_agent_store

# --- Domain Exceptions ---
class AgentAlreadyExistsException(Exception):
    pass

class AgentService:

    def __init__(self):
        self.store = get_agent_store()

    def build_and_register_mcp_agent(self, req: MCPAgentRequest):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        #if req.name in get_app_context().get_enabled_agent_names() + self.dynamic_agent_manager.get_registered_names():
        #    raise AgentAlreadyExistsException(f"Agent '{req.name}' already exists")

        # get_app_context()._agent_index[req.name] = AgentSettings(
        #     name=req.name,
        #     class_path="app.features.dynamic_agent.mcp_agent.MCPAgent",
        #     enabled=True,
        #     categories=req.categories or [],
        #     settings={},
        #     model=get_configuration().ai.default_model,
        #     tag=req.tag,
        #     mcp_servers=req.mcp_servers,
        #     max_steps=10,
        # )

        agent_instance = MCPAgent(
            cluster_fullname="",
            name=req.name,
            base_prompt=req.base_prompt,
            role=req.role,
            nickname=req.nickname,
            description=req.description,
            icon=req.icon,
            categories=req.categories,
            tag=req.tag,
        )

        def constructor() -> MCPAgent:
            return agent_instance

        #self.dynamic_agent_manager.register_agent(req.name, constructor, MCPAgent)

        self.store.save(agent_instance)

        return JSONResponse(content=agent_instance.to_dict())
