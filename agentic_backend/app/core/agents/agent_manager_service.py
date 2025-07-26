from fastapi.responses import JSONResponse
from app.core.agents.mcp_agent import MCPAgent
from app.core.agents.structures import MCPAgentRequest
from app.application_context import get_agent_store

# --- Domain Exceptions ---
class AgentAlreadyExistsException(Exception):
    pass

class AgentManagerService:

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
