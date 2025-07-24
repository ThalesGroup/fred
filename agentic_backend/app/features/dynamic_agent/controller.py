from fastapi import APIRouter, HTTPException

from app.features.dynamic_agent.structures import CreateAgentRequest, MCPAgentRequest
from app.application_context import get_app_context

class DynamicAgentController:
    """
    Controller for managing dynamic MCP agents.
    """
    def __init__(self, app: APIRouter):
        fastapi_tags = ["Dynamic MCP agent creation"]
        self.service = get_app_context().get_dynamic_agent_manager_service()
        
        @app.post(
            "/agents/create",
            tags=fastapi_tags,
            summary="Create a Dynamic Agent that can access MCP tools",
        )
        async def create_agent(req: CreateAgentRequest):
            try:
                if not isinstance(req, MCPAgentRequest):
                    raise HTTPException(status_code=400, detail=f"Unsupported agent_type: {req.agent_type}")
                
                return self.service.build_and_register_mcp_agent(req)

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
