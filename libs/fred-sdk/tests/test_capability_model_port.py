# Copyright Thales 2026
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

"""Contract of the turn-free capability model port and the route team authorizer."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Sequence

import pytest
from fastapi import HTTPException
from fred_sdk.contracts.runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelPort,
    CapabilityTeamAuthorizer,
    RuntimeServices,
    capability_platform_model,
    capability_team_authorizer,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from starlette.requests import Request


class _EchoPort(CapabilityModelPort):
    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        profile_id: str | None = None,
        require_vision: bool = False,
    ) -> AIMessage:
        return AIMessage(content=f"{len(messages)}:{profile_id}:{require_vision}")


class _AllowAll(CapabilityTeamAuthorizer):
    async def require_agent_editor(self, team_id: str) -> None:
        return None


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_capability_model_is_optional_and_appended_last() -> None:
    fields = [field.name for field in dataclasses.fields(RuntimeServices)]
    assert fields[-1] == "capability_model"
    assert RuntimeServices().capability_model is None


def test_port_is_keyword_only_after_messages() -> None:
    services = RuntimeServices(capability_model=_EchoPort())
    port = services.capability_model
    assert port is not None
    reply = asyncio.run(
        port.ainvoke([HumanMessage(content="hi")], profile_id="p", require_vision=True)
    )
    assert reply.content == "1:p:True"


def test_team_authorizer_dependency_fails_closed_when_unbound() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(capability_team_authorizer(_request()))
    assert exc.value.status_code == 503


def test_team_authorizer_dependency_returns_the_bound_authorizer() -> None:
    request = _request()
    authorizer = _AllowAll()
    setattr(request.state, CAPABILITY_TEAM_AUTHORIZER_STATE, authorizer)
    assert asyncio.run(capability_team_authorizer(request)) is authorizer


def test_an_authorizer_without_the_manager_check_refuses_it() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_AllowAll().require_capability_manager())
    assert exc.value.status_code == 403


def test_platform_model_dependency_fails_closed_when_unbound() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(capability_platform_model(_request()))
    assert exc.value.status_code == 503


def test_platform_model_dependency_returns_the_bound_port() -> None:
    request = _request()
    port = _EchoPort()
    setattr(request.state, CAPABILITY_PLATFORM_MODEL_STATE, port)
    assert asyncio.run(capability_platform_model(request)) is port


def test_fred_sdk_imports_fastapi_only_in_the_route_dependency_module() -> None:
    # fred-sdk declares no fastapi dependency: only the lazily loaded route
    # dependency module may import it.
    import ast
    from pathlib import Path

    import fred_sdk

    root = Path(fred_sdk.__file__).parent
    importers = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            if any(n == "fastapi" or n.startswith("fastapi.") for n in names):
                importers.add(path.relative_to(root).as_posix())
    assert importers == {"contracts/_capability_route_deps.py"}
