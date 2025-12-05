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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

from agentic_backend.common.utils import log_exception
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.mcp_server_manager import (
    McpServerManager,
    McpServerNotFound,
    McpUpdatesDisabled,
)
from agentic_backend.core.mcp.mcp_server_service import McpServerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP Servers"])


def get_mcp_manager(request: Request) -> McpServerManager:
    manager: Optional[McpServerManager] = getattr(
        request.app.state, "mcp_manager", None
    )
    if manager is None:
        raise HTTPException(status_code=500, detail="MCP manager not initialized")
    return manager


class SaveMcpServerRequest(BaseModel):
    server: MCPServerConfiguration


@router.get(
    "/mcp/servers",
    summary="List MCP servers available to agents",
    response_model=list[MCPServerConfiguration],
)
async def list_mcp_servers(
    user: KeycloakUser = Depends(get_current_user),
    manager: McpServerManager = Depends(get_mcp_manager),
):
    # MCP Hub should display all servers, even disabled ones, so operators can toggle them.
    return manager.list_servers(include_disabled=True)


@router.post(
    "/mcp/servers",
    summary="Create a new MCP server configuration",
    response_model=None,
)
async def create_mcp_server(
    request: SaveMcpServerRequest,
    user: KeycloakUser = Depends(get_current_user),
    manager: McpServerManager = Depends(get_mcp_manager),
):
    service = McpServerService(manager)
    try:
        await service.create_server(user, request.server)
    except Exception as e:
        log_exception(e)
        raise _handle_exception(e)


@router.put(
    "/mcp/servers/{server_id}",
    summary="Update or create an MCP server configuration",
    response_model=None,
)
async def update_mcp_server(
    server_id: str,
    request: SaveMcpServerRequest,
    user: KeycloakUser = Depends(get_current_user),
    manager: McpServerManager = Depends(get_mcp_manager),
):
    payload = request.server
    if payload.id != server_id:
        payload = payload.model_copy(update={"id": server_id})
    service = McpServerService(manager)
    try:
        await service.save_server(user, payload, allow_upsert=True)
    except Exception as e:
        log_exception(e)
        raise _handle_exception(e)


@router.delete(
    "/mcp/servers/{server_id}",
    summary="Delete an MCP server configuration",
    response_model=None,
)
async def delete_mcp_server(
    server_id: str,
    user: KeycloakUser = Depends(get_current_user),
    manager: McpServerManager = Depends(get_mcp_manager),
):
    service = McpServerService(manager)
    try:
        await service.delete_server(user, server_id)
    except Exception as e:
        log_exception(e)
        raise _handle_exception(e)


@router.post(
    "/mcp/servers/restore",
    summary="Restore MCP servers from static configuration",
    response_model=None,
)
async def restore_mcp_servers_from_config(
    user: KeycloakUser = Depends(get_current_user),
    manager: McpServerManager = Depends(get_mcp_manager),
):
    service = McpServerService(manager)
    try:
        await service.restore_static_servers(user)
    except Exception as e:
        log_exception(e)
        raise _handle_exception(e)


def _handle_exception(e: Exception) -> HTTPException:
    if isinstance(e, McpServerNotFound):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, McpUpdatesDisabled):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValueError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=500, detail="Internal Server Error")
