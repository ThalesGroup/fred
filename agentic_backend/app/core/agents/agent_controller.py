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

from fastapi import APIRouter, Depends, HTTPException, Request
from fred_core import KeycloakUser, get_current_user

from app.common.error import MCPClientConnectionException
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.agent_service import AgentAlreadyExistsException, AgentService
from app.core.agents.structures import CreateAgentRequest


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency function to retrieve AgentManager from app.state."""
    return request.app.state.agent_manager


def handle_exception(e: Exception) -> HTTPException | Exception:
    if isinstance(e, AgentAlreadyExistsException):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, MCPClientConnectionException):
        return HTTPException(
            status_code=502, detail=f"MCP connection failed: {e.reason}"
        )
    return e


# Create a module-level APIRouter
router = APIRouter(tags=["Agents"])


@router.post(
    "/agents/create",
    summary="Create a Dynamic Agent that can access MCP tools",
)
async def create_agent(
    req: CreateAgentRequest,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    try:
        service = AgentService(agent_manager=agent_manager)
        return await service.build_and_register_mcp_agent(user, req)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)


@router.put(
    "/agents/{name}",
    summary="Update a dynamic agent's configuration",
)
async def update_agent(
    name: str,
    req: CreateAgentRequest,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    try:
        service = AgentService(agent_manager=agent_manager)
        return await service.update_agent(user, name, req)
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
        return await service.delete_agent(user, name)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
