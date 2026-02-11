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

import importlib
import inspect
import sys
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

from agentic_backend.common.error import MCPClientConnectionException
from agentic_backend.common.mcp_utils import MCPConnectionError
from agentic_backend.common.structures import (
    AgentSettings,
)
from agentic_backend.core.agents.agent_manager import (
    AgentAlreadyExistsException,
    AgentManager,
    AgentUpdatesDisabled,
)
from agentic_backend.core.agents.agent_service import (
    AgentService,
    MissingTeamIdError,
    OwnerFilter,
)
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.mcp_server_manager import McpServerManager
from agentic_backend.core.runtime_source import get_runtime_source_registry


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MissingTeamIdError)
    async def missing_team_id_handler(
        request: Request, exc: MissingTeamIdError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(AgentAlreadyExistsException)
    async def agent_already_exists_handler(
        request: Request, exc: AgentAlreadyExistsException
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(MCPClientConnectionException)
    async def mcp_client_connection_handler(
        request: Request, exc: MCPClientConnectionException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"detail": f"MCP connection failed: {exc.reason}"}
        )

    @app.exception_handler(MCPConnectionError)
    async def mcp_connection_error_handler(
        request: Request, exc: MCPConnectionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"detail": f"MCP connection failed: {exc.reason}"}
        )

    @app.exception_handler(AgentUpdatesDisabled)
    async def agent_updates_disabled_handler(
        request: Request, exc: AgentUpdatesDisabled
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency function to retrieve AgentManager from app.state."""
    return request.app.state.agent_manager


def get_mcp_manager(request: Request) -> McpServerManager:
    manager: McpServerManager | None = getattr(request.app.state, "mcp_manager", None)
    if manager is None:
        raise HTTPException(status_code=500, detail="MCP manager not initialized")
    return manager


@dataclass
class _SourceBlob:
    text: str
    file: str | None
    start_line: int | None


def _sourcelines(obj) -> _SourceBlob:
    # FRED: Pure-Python only; will raise for builtins/C-ext/pyc-only.
    try:
        lines, start = inspect.getsourcelines(obj)
        mod = inspect.getmodule(obj)
        return _SourceBlob("".join(lines), getattr(mod, "__file__", None), start)
    except OSError as e:
        raise HTTPException(status_code=422, detail=f"Source not available: {e}")


def _resolve_attr(root: object, qualname: str) -> object:
    # FRED: Safe dotted traversal: module.Class.method
    cur = root
    for part in qualname.split("."):
        if not hasattr(cur, part):
            raise HTTPException(
                status_code=404,
                detail=f"Attribute '{part}' not found under '{getattr(cur, '__name__', type(cur).__name__)}'",
            )
        cur = getattr(cur, part)
    return cur


def _import_class(class_path: str) -> object:
    try:
        module_name, class_name = class_path.rsplit(".", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid class_path (expected module.Class): {class_path}",
        ) from exc

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise HTTPException(
            status_code=404, detail=f"Cannot import module: {module_name}: {exc}"
        ) from exc

    if not hasattr(module, class_name):
        raise HTTPException(
            status_code=404,
            detail=f"Class '{class_name}' not found in module '{module_name}'",
        )
    return getattr(module, class_name)


# Create a module-level APIRouter
router = APIRouter(tags=["Agents"])


class CreateAgentRequest(BaseModel):
    name: str
    type: str = "basic"
    team_id: str | None = None
    a2a_base_url: str | None = None
    a2a_token: str | None = None


@router.get(
    "/agents",
    summary="Get the list of available agents",
    response_model=list[AgentSettings],
)
async def list_agents(
    owner_filter: Optional[OwnerFilter] = None,
    team_id: Optional[str] = None,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> list[AgentSettings]:
    service = AgentService(agent_manager=agent_manager)
    return await service.list_agents(
        user=user, owner_filter=owner_filter, team_id=team_id
    )


@router.post(
    "/agents/create",
    summary="Create a Dynamic Agent that can access tools",
)
async def create_agent(
    request: CreateAgentRequest,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    service = AgentService(agent_manager=agent_manager)
    await service.create_agent(
        user,
        request.name,
        agent_type=request.type,
        team_id=request.team_id,
        a2a_base_url=request.a2a_base_url,
        a2a_token=request.a2a_token,
    )


@router.put(
    "/agents/update",
    summary="Update an agent. Only the tuning part is updatable",
)
async def update_agent(
    agent_settings: AgentSettings,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    service = AgentService(agent_manager=agent_manager)
    return await service.update_agent(user, agent_settings)


@router.delete(
    "/agents/{agent_id}",
    summary="Delete a dynamic agent by ID",
    status_code=204,
)
async def delete_agent(
    agent_id: str,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    service = AgentService(agent_manager=agent_manager)
    await service.delete_agent(user=user, agent_id=agent_id)


@router.post(
    "/agents/restore",
    summary="Restore static agents from configuration",
    response_model=None,
)
async def restore_agents(
    force_overwrite: bool = True,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    service = AgentService(agent_manager=agent_manager)
    await service.restore_static_agents(user=user, force_overwrite=force_overwrite)


@router.get(
    "/agents/mcp-servers",
    summary="List MCP servers known to all agents",
    response_model=list[MCPServerConfiguration],
)
async def list_mcp_servers(
    user: KeycloakUser = Depends(get_current_user),
    mcp_manager: McpServerManager = Depends(get_mcp_manager),
):
    return mcp_manager.list_servers()


@router.get(
    "/agents/source/keys",
    summary="List keys registered for runtime source inspection",
)
async def list_runtime_source_keys(
    user: KeycloakUser = Depends(get_current_user),
):
    # FRED: Simple discoverability for the UI (Monaco picker, etc.)
    # 👇 CHANGE: Use the getter function
    return {"keys": sorted(get_runtime_source_registry().keys())}


@router.get(
    "/agents/source/by-object",
    response_class=PlainTextResponse,
    summary="Get source of a registered runtime object",
)
async def runtime_source_by_object(
    key: str,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    # FRED: Prefer this path — explicit allowlist.
    # 👇 CHANGE: Access the registry via the getter function
    obj = get_runtime_source_registry().get(key)
    if obj is None and key.startswith("agent."):
        agent_id = key.split(".", 1)[1]
        agent_settings = agent_manager.get_agent_settings(agent_id)
        if agent_settings and agent_settings.class_path:
            obj = _import_class(agent_settings.class_path)
    if obj is None:
        raise HTTPException(status_code=404, detail="Unknown registry key")
    blob = _sourcelines(obj)
    header = f"# key: {key}\n# file: {blob.file or 'unknown'}  # starts at line {blob.start_line or '?'}\n"
    return header + blob.text


@router.get(
    "/agents/source/by-module",
    response_class=PlainTextResponse,
    summary="Get source by module and optional qualname (admin/dev only)",
)
async def runtime_source_by_module(
    module: str,
    qualname: Optional[str] = None,
    user: KeycloakUser = Depends(get_current_user),
):
    # FRED: This can import modules → guard with RBAC in get_current_user/roles.
    mod = sys.modules.get(module)
    if mod is None:
        try:
            mod = __import__(module, fromlist=["*"])  # may run import-time code
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Cannot import module: {e}")

    target = mod if not qualname else _resolve_attr(mod, qualname)
    blob = _sourcelines(target)
    header = (
        f"# module: {module}  qualname: {qualname or '<module>'}\n"
        f"# file: {blob.file or 'unknown'}  # starts at line {blob.start_line or '?'}\n"
    )
    return header + blob.text
