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

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

from app.common.error import MCPClientConnectionException
from app.common.mcp_utils import MCPConnectionError
from app.common.structures import Agent, AgentSettings, MCPServerConfiguration
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.agent_service import AgentAlreadyExistsException, AgentService


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency function to retrieve AgentManager from app.state."""
    return request.app.state.agent_manager


def handle_exception(e: Exception) -> HTTPException | Exception:
    if isinstance(e, AgentAlreadyExistsException):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, MCPClientConnectionException) or isinstance(e, MCPConnectionError):
        return HTTPException(
            status_code=502, detail=f"MCP connection failed: {e.reason}"
        )
    return e


# Create a module-level APIRouter
router = APIRouter(tags=["Agents"])


class CreateMcpAgentRequest(BaseModel):
    name: str
    mcp_servers: List[MCPServerConfiguration]
    role: str
    description: str
    tags: Optional[List[str]] = None


@router.post(
    "/agents/create",
    summary="Create a Dynamic Agent that can access MCP tools",
)
async def create_agent(
    request: CreateMcpAgentRequest,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    try:
        service = AgentService(agent_manager=agent_manager)
        agent = Agent(
            type="agent",
            name=request.name,
            description=request.description,
            role=request.role,
            tags=request.tags or [],
            mcp_servers=request.mcp_servers,
            class_path="app.core.agents.mcp_agent.MCPAgent",  # dynamic agent
        )
        await service.create_agent(user, agent)
        return {"message": f"Agent '{agent.name}' created successfully."}
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)


@router.put(
    "/agents/update",
    summary="Update an agent. Only the tuning part is upfatable",
)
async def update_agent(
    agent_settings: AgentSettings,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    try:
        service = AgentService(agent_manager=agent_manager)
        return await service.update_agent(user, agent_settings)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)


@router.delete(
    "/agents/{name}",
    summary="Delete a dynamic agent by name",
)
async def delete_agent(
    name: str,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    try:
        service = AgentService(agent_manager=agent_manager)
        return await service.delete_agent(user=user, agent_name=name)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
