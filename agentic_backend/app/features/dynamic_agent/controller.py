# app/controllers/agent_controller.py

from fastapi import APIRouter, HTTPException

from app.features.dynamic_agent.mcp_agent import MCPAgent
from app.features.dynamic_agent.structures import CreateAgentRequest, MCPAgentRequest

router = APIRouter()

@router.post("/agents/create")
async def create_agent(req: CreateAgentRequest):
    try:
        if isinstance(req, MCPAgentRequest):
            agent = MCPAgent(
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
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported agent_type: {req.agent_type}")

        #AgentTeam().register(agent)
        return {"status": "success", "agent_name": agent.name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
