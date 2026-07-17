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

"""
Capability chat parts → `UiPart` union → OpenAPI (#1977, RFC §3.6/§4/§9.1).

What is verified:
- `CapabilityRegistry.chat_parts()` composes contributed parts deterministically
- `registry.validate()` folds validated parts into the `UiPart` union, so
  runtime events accept them (model-build-time registration, RFC §4)
- the app built by `create_agent_app` exposes the demo capability's part in
  its OpenAPI document with ZERO hand edits to union files — the acceptance
  criterion for the generated-frontend-types flow
- the demo tool emits `DemoCardPart` through the standard
  `content_and_artifact` channel the runtime merges onto tool_result/final
"""

from __future__ import annotations

import json
from typing import Literal

import pytest
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.assembly import build_capability_context
from fred_runtime.capabilities.demo import DemoCardPart, DemoEchoCapability
from fred_runtime.capabilities.registry import BUILTIN_CHAT_PART_KINDS
from fred_sdk.contracts.capability import CapabilityIdentity
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import RuntimeServices
from pydantic import BaseModel, ValidationError

DEMO_CARD = {"type": "demo_card", "title": "Demo echo", "body": "HELLO"}


class _AlphaPart(BaseModel):
    type: Literal["alpha_part"] = "alpha_part"
    value: int = 0


def _capability_with_part(cap_id: str, part: type[BaseModel]):
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityManifest,
        EmptyModel,
    )

    class _Cap(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
        manifest = CapabilityManifest(
            id=cap_id,
            version="0.0.1",
            name=f"capability.{cap_id}.name",
            description=f"capability.{cap_id}.description",
            icon="extension",
            chat_parts=[part],
        )

        def middleware(self, ctx):  # noqa: ANN001, ANN201 - test stub
            return []

    return _Cap()


# -- registry composition ------------------------------------------------------


def test_builtin_kinds_derive_from_sdk_base_union() -> None:
    assert BUILTIN_CHAT_PART_KINDS == frozenset({"link", "geo"})


def test_chat_parts_compose_in_deterministic_capability_order() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability_with_part("zeta", _AlphaPart))
    registry.register(DemoEchoCapability())

    # Sorted capability ids: demo_echo before zeta.
    assert registry.chat_parts() == (DemoCardPart, _AlphaPart)


# -- model-build-time union registration ---------------------------------------


def test_validate_folds_demo_part_into_ui_part_union() -> None:
    with pytest.raises(ValidationError):
        ToolInvocationResult.model_validate({"tool_ref": "t", "ui_parts": [DEMO_CARD]})

    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    registry.validate(env={})

    result = ToolInvocationResult.model_validate(
        {"tool_ref": "t", "ui_parts": [DEMO_CARD]}
    )
    assert isinstance(result.ui_parts[0], DemoCardPart)
    assert result.ui_parts[0].body == "HELLO"


# -- OpenAPI: the generated-types acceptance criterion --------------------------


def _openapi_pod_config():
    from fred_runtime.app import AgentPodConfig

    return AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Chat Parts Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
            },
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-m2m",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-user",
                },
                "authorized_origins": [],
            },
            "ai": {"knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1"},
            "storage": {
                "postgres": {"sqlite_path": "~/.fred/tests/chat-parts.sqlite3"}
            },
            "platform": {"control_plane_url": "http://localhost:8222/control-plane/v1"},
        }
    )


def test_openapi_includes_demo_capability_part_with_no_hand_edits() -> None:
    """
    The offline OpenAPI export path (`generate_openapi.py` → `create_agent_app`
    → `app.openapi()`, no lifespan): the installed demo capability's chat part
    must appear in the schema purely through entry-point registration.
    """

    from fred_runtime.app import create_agent_app

    app = create_agent_app(registry={}, config=_openapi_pod_config())
    document = json.dumps(app.openapi())

    assert "DemoCardPart" in document
    assert "demo_card" in document
    # The frozen members are still there.
    assert "LinkPart" in document
    assert "GeoPart" in document


# -- demo tool emission ----------------------------------------------------------


def test_demo_tool_emits_demo_card_part_as_artifact() -> None:
    capability = DemoEchoCapability()
    # Boot always validates the registry (extending the union) before any
    # tool can run; mirror that here so the artifact's ui_parts validate.
    registry = CapabilityRegistry()
    registry.register(capability)
    registry.validate(env={})
    ctx = build_capability_context(
        capability,
        identity=CapabilityIdentity(user_id="user-1", session_id="session-1"),
        services=RuntimeServices(),
        config={"uppercase": True},
    )
    (middleware,) = capability.middleware(ctx)
    (demo_tool,) = middleware.tools

    message = demo_tool.invoke(
        {
            "name": "demo_echo",
            "args": {"text": "hello"},
            "id": "c-1",
            "type": "tool_call",
        }
    )

    assert message.content == "HELLO"
    artifact = message.artifact
    assert isinstance(artifact, ToolInvocationResult)
    part = artifact.ui_parts[0]
    assert isinstance(part, DemoCardPart)
    assert part.type == "demo_card"
    assert part.body == "HELLO"
