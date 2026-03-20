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
import logging
import sys
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common import OwnerFilter
from pydantic import BaseModel

from agentic_backend.common.error import MCPClientConnectionException
from agentic_backend.common.mcp_utils import MCPConnectionError
from agentic_backend.common.structures import (
    AgentSettings,
)
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_manager import (
    AgentAlreadyExistsException,
    AgentManager,
    AgentUpdatesDisabled,
)
from agentic_backend.core.agents.agent_service import (
    AgentService,
    ImmutableTeamIdError,
    InvalidClassPathError,
    MissingTeamIdError,
)
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.agents.v2.catalog import build_definition_from_settings
from agentic_backend.core.agents.v2.inspection import inspect_agent
from agentic_backend.core.agents.v2.models import AgentInspection
from agentic_backend.core.agents.v2.react_profiles import list_react_profiles_filtered
from agentic_backend.core.mcp.mcp_server_manager import McpServerManager
from agentic_backend.core.runtime_source import get_runtime_source_registry

logger = logging.getLogger(__name__)


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

    @app.exception_handler(InvalidClassPathError)
    async def invalid_class_path_handler(
        request: Request, exc: InvalidClassPathError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ImmutableTeamIdError)
    async def immutable_team_id_handler(
        request: Request, exc: ImmutableTeamIdError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


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
    type: Literal["basic"] = "basic"
    team_id: str | None = None
    class_path: str | None = None
    definition_ref: str | None = None
    profile_id: str | None = None


class ReActProfileSummary(BaseModel):
    profile_id: str
    title: str
    description: str
    agent_description: str
    tags: list[str]


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
        class_path=request.class_path,
        definition_ref=request.definition_ref,
        profile_id=request.profile_id,
    )


@router.get(
    "/agents/react-profiles",
    summary="List available v2 ReAct starting profiles",
    response_model=list[ReActProfileSummary],
)
async def list_react_agent_profiles(
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> list[ReActProfileSummary]:
    profiles = list_react_profiles_filtered(
        agent_manager.config.ai.react_profile_allowlist
    )
    return [
        ReActProfileSummary(
            profile_id=profile.profile_id,
            title=profile.title,
            description=profile.description,
            agent_description=profile.agent_description,
            tags=list(profile.tags),
        )
        for profile in profiles
    ]


@router.get(
    "/agents/{agent_id}/inspect",
    summary="Inspect a v2 agent definition without activation",
    response_model=AgentInspection,
)
async def inspect_v2_agent(
    agent_id: str,
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> AgentInspection:
    service = AgentService(agent_manager=agent_manager)
    settings = await service.get_agent_by_id(user, agent_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        resolved = resolve_agent_reference(
            class_path=settings.class_path,
            definition_ref=settings.definition_ref,
        )
        if resolved.implementation_kind != AgentImplementationKind.V2_DEFINITION:
            raise HTTPException(
                status_code=409,
                detail="Agent inspection is only supported for v2 agent definitions.",
            )

        definition = build_definition_from_settings(
            definition_class=resolved.cls,
            settings=settings,
        )
        return inspect_agent(definition)

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        if isinstance(e, (ValueError, TypeError)):
            raise HTTPException(status_code=400, detail=str(e)) from e
        logger.error(f"Failed to inspect agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to inspect agent") from e


@router.get(
    "/agents/class-paths",
    summary="List class paths declared in static agent configuration",
    response_model=list[str],
)
async def list_declared_agent_class_paths(
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> list[str]:
    service = AgentService(agent_manager=agent_manager)
    return await service.list_declared_class_paths(user)


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
        agent_settings = await agent_manager.get_agent_settings(agent_id)
        if agent_settings:
            try:
                resolved = resolve_agent_reference(
                    class_path=agent_settings.class_path,
                    definition_ref=agent_settings.definition_ref,
                )
            except Exception:
                resolved = None
            if resolved is not None:
                obj = _import_class(resolved.class_path)
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
