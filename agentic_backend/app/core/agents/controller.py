from app.common.error import MCPClientConnectionException
from fastapi import APIRouter, HTTPException

from app.core.agents.structures import CreateAgentRequest
from app.core.agents.agent_manager_service import AgentAlreadyExistsException, AgentManagerService
from app.common.utils import log_exception

def handle_exception(e: Exception) -> HTTPException:
    if isinstance(e, AgentAlreadyExistsException):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, MCPClientConnectionException):
        return HTTPException(status_code=502, detail=f"MCP connection failed: {e.reason}")
    return HTTPException(status_code=500, detail="Internal server error")

class AgentController:
    """
    Controller for managing dynamic MCP agents.
    """
    def __init__(self, app: APIRouter):
        fastapi_tags = ["Agents"]
        self.service = AgentManagerService()
        
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
