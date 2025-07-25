from fastapi.responses import JSONResponse
from app.chatbot.dynamic_agent_manager import DynamicAgentManager
from app.features.dynamic_agent.mcp_agent import MCPAgent
from app.features.dynamic_agent.structures import MCPAgentRequest
from app.application_context import get_app_context, get_configuration
from app.common.structures import AgentSettings

# --- Domain Exceptions ---
class AgentAlreadyExistsException(Exception):
    pass

class DynamicAgentManagerService:
    dynamic_agent_manager = DynamicAgentManager()

    def get_dynamic_agent_manager(self) -> DynamicAgentManager:
        """
        Returns the dynamic agent manager for integration elsewhere
        """
        return self.dynamic_agent_manager

    def build_and_register_mcp_agent(self, req: MCPAgentRequest):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        if req.name in get_app_context().get_enabled_agent_names() + self.dynamic_agent_manager.get_registered_names():
            raise AgentAlreadyExistsException(f"Agent '{req.name}' already exists")

        get_app_context()._agent_index[req.name] = AgentSettings(
            name=req.name,
            class_path="app.features.dynamic_agent.mcp_agent.MCPAgent",
            enabled=True,
            categories=req.categories or [],
            settings={},
            model=get_configuration().ai.default_model,
            tag=req.tag,
            mcp_servers=req.mcp_servers,
            max_steps=10,
        )

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

        self.dynamic_agent_manager.register_agent(req.name, constructor, MCPAgent)

        agent_store = get_app_context().get_dynamic_agent_store()
        agent_store.save(agent_instance)

        return JSONResponse(content=agent_instance.to_dict())
