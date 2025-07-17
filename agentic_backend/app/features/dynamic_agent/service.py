from fastapi import HTTPException

from app.chatbot.dynamic_agent_manager import DynamicAgentManager
from app.features.dynamic_agent.mcp_agent import MCPAgent
from app.features.dynamic_agent.structures import MCPAgentRequest

# Singleton dynamic manager (can be moved to __init__.py or containerized later)
dynamic_agent_manager = DynamicAgentManager()


def create_mcp_agent(req: MCPAgentRequest):
    """
    Create and register a dynamic MCP agent if it doesn't already exist.
    """
    if req.name in dynamic_agent_manager.get_registered_names():
        raise HTTPException(status_code=409, detail=f"Agent '{req.name}' already exists")

    def constructor() -> MCPAgent:
        return MCPAgent(
            name=req.name,
            prompt=req.prompt,
            mcp_urls=req.mcp_urls,
            role=req.role,
            nickname=req.nickname,
            description=req.description,
            icon=req.icon,
            categories=req.categories,
            tag=req.tag,
        )

    dynamic_agent_manager.register_agent(req.name, constructor)
    return {"status": "success", "agent_name": req.name}


def get_dynamic_agent_manager() -> DynamicAgentManager:
    """
    Returns the dynamic agent manager for integration elsewhere (e.g., Fred).
    """
    return dynamic_agent_manager
