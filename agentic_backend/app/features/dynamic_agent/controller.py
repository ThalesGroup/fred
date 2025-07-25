from app.common.error import MCPClientConnectionException
from fastapi import APIRouter, HTTPException

from app.features.dynamic_agent.structures import CreateAgentRequest
from app.features.dynamic_agent.service import AgentAlreadyExistsException
from app.application_context import get_app_context
from app.common.utils import log_exception

def handle_exception(e: Exception) -> HTTPException:
    if isinstance(e, AgentAlreadyExistsException):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, MCPClientConnectionException):
        return HTTPException(status_code=502, detail=f"MCP connection failed: {e.reason}")
    return HTTPException(status_code=500, detail="Internal server error")

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
        # @TODO: check for authorization
        async def create_agent(req: CreateAgentRequest):
            try:
                return self.service.build_and_register_mcp_agent(req)
            except Exception as e:
                log_exception(e)
                raise handle_exception(e)
