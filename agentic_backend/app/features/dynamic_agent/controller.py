from fastapi import APIRouter, HTTPException
from app.features.dynamic_agent.mcp_agent import MCPAgent
from app.features.dynamic_agent.structures import CreateAgentRequest, MCPAgentRequest
from app.application_context import get_app_context
from app.common.structures import AgentSettings
from app.features.dynamic_agent.service import create_mcp_agent
from app.application_context import get_configuration

class DynamicAgentController:
    """
    Plip plop
    """
    def __init__(self, app: APIRouter):
        """
        Plap ploup
        """
        
        fastapi_tags = ["Dynamic MCP agent creation"]
        
        @app.post(
            "/agents/create",
            tags=fastapi_tags,
            summary="Create a Dynamic Agent that can access MCP tools",
        )
        async def create_agent(req: CreateAgentRequest):
            try:
                if isinstance(req, MCPAgentRequest):
                    create_mcp_agent(req)
            
                    get_app_context()._agent_index[req.name] = AgentSettings(
                        name=req.name,
                        class_path=f"app.features.dynamic_agent.mcp_agent.MCPAgent",
                        enabled=True,
                        categories=req.categories,
                        settings={},
                        model=get_configuration().ai.default_model,
                        tag=req.tag,
                        mcp_servers=req.mcp_servers,
                        max_steps=10,
                    )

                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported agent_type: {req.agent_type}")

                return {"status": "success", "agent_name": req.name}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
