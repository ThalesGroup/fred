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

import inspect
import sys
from dataclasses import dataclass
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

from app.common.error import MCPClientConnectionException
from app.common.mcp_utils import MCPConnectionError
from app.common.structures import Agent, AgentSettings, MCPServerConfiguration
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.agent_service import AgentAlreadyExistsException, AgentService
from app.core.runtime_source import get_runtime_source_registry


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
):
    # FRED: Prefer this path — explicit allowlist.
    # 👇 CHANGE: Access the registry via the getter function
    obj = get_runtime_source_registry().get(key)
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
