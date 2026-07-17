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
Chat-time controls + typed turn options on the pod (#1976, RFC
AGENT-CAPABILITY-RFC.md §3.3, §3.5, §3.7).

Covers the pod half of the retired `chat_options` taxonomy:
- `POST /agents/capabilities/chat-controls` batch-evaluates `chat_controls(config)`
  per capability at session prep — ordered items, per-entry `manifest_version`,
  per-capability error isolation (unknown / unresolvable config → error result,
  never a failed batch)
- `validate_turn_options` gates a request's `turn_options` envelope: an unknown /
  unselected capability id or a slice that fails the owning `TurnOptionsModel`
  raises `TurnOptionsInvalidError`, mapped to a typed 422 BEFORE any SSE bytes;
  each capability's middleware then receives only its own typed slice
"""

from __future__ import annotations

from typing import Any, Literal

import pytest
from conftest import ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.capabilities import (
    TurnOptionsInvalidError,
    evaluate_chat_controls_batch,
    validate_turn_options,
)
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    ChatControlSpec,
    ChatControlsRequest,
    ChatControlsRequestItem,
    StoredCapabilityConfig,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel

# Reuse the #1974 endpoint harness verbatim (app + fake control-plane + registry).
from test_capability_endpoints_1974 import (
    _app_with_capabilities,
    _fake_control_plane,
)

# ---------------------------------------------------------------------------
# A capability that both computes chat controls and reads a typed turn-options
# slice — the two halves #1976 adds.
# ---------------------------------------------------------------------------

SCOPE_TURN_OPTIONS: list[dict[str, Any]] = []


class _ScopeConfig(BaseModel):
    attach: bool = False


class _ScopeTurnOptions(BaseModel):
    policy: Literal["strict", "hybrid"] = "hybrid"


class _ScopeMiddleware(AgentMiddleware):
    def __init__(self, ctx: CapabilityContext[_ScopeConfig, _ScopeTurnOptions]) -> None:
        super().__init__()
        # Record the TYPED slice the middleware received (RFC §3.5): proof the
        # generic envelope was narrowed to this capability's TurnOptionsModel.
        SCOPE_TURN_OPTIONS.append(ctx.turn_options.model_dump())

        @tool
        def scope_echo(text: str) -> str:
            """Echo the given text back."""

            return text

        self.tools = [scope_echo]


class _ScopeCapability(AgentCapability[_ScopeConfig, _ScopeConfig, _ScopeTurnOptions]):
    """Emits `attach_files` (only when configured) then `search_policy`, and
    carries a typed per-turn `policy`."""

    manifest = CapabilityManifest(
        id="scope_probe",
        version="1.0.0",
        name="capability.scope_probe.name",
        description="capability.scope_probe.description",
        icon="Sensors",
    )
    ConfigModel = _ScopeConfig
    TurnOptionsModel = _ScopeTurnOptions

    def chat_controls(self, config: _ScopeConfig) -> list[ChatControlSpec]:
        controls: list[ChatControlSpec] = []
        if config.attach:
            controls.append(ChatControlSpec(widget="attach_files"))
        controls.append(ChatControlSpec(widget="search_policy"))
        return controls

    def middleware(
        self, ctx: CapabilityContext[_ScopeConfig, _ScopeTurnOptions]
    ) -> list[AgentMiddleware]:
        return [_ScopeMiddleware(ctx)]


def _registry_with_scope() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(_ScopeCapability())
    return registry


# ---------------------------------------------------------------------------
# chat-controls batch evaluation (pod side of session prep)
# ---------------------------------------------------------------------------


def test_evaluate_chat_controls_batch_orders_and_versions() -> None:
    registry = _registry_with_scope()
    response = evaluate_chat_controls_batch(
        registry,
        ChatControlsRequest(
            items=[
                ChatControlsRequestItem(
                    capability_id="scope_probe",
                    config_envelope=None,  # StoredConfigModel defaults → attach False
                )
            ]
        ),
    )
    assert len(response.results) == 1
    result = response.results[0]
    assert result.capability_id == "scope_probe"
    assert result.manifest_version == "1.0.0"
    assert result.error is None
    # attach False by default → only search_policy, in returned-list order.
    assert [c.widget for c in result.controls] == ["search_policy"]


def test_evaluate_chat_controls_reads_stored_config() -> None:
    registry = _registry_with_scope()
    response = evaluate_chat_controls_batch(
        registry,
        ChatControlsRequest(
            items=[
                ChatControlsRequestItem(
                    capability_id="scope_probe",
                    config_envelope=StoredCapabilityConfig(
                        schema_version="1.0.0", config={"attach": True}
                    ),
                )
            ]
        ),
    )
    assert [c.widget for c in response.results[0].controls] == [
        "attach_files",
        "search_policy",
    ]


def test_evaluate_chat_controls_isolates_unknown_capability() -> None:
    registry = _registry_with_scope()
    response = evaluate_chat_controls_batch(
        registry,
        ChatControlsRequest(items=[ChatControlsRequestItem(capability_id="ghost")]),
    )
    result = response.results[0]
    assert result.error is not None
    assert "ghost" in result.error
    assert result.controls == []


def test_chat_controls_endpoint_returns_results(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, _ScopeCapability())
    try:
        resp = client.post(
            "/pod/v1/agents/capabilities/chat-controls",
            json={
                "items": [
                    {
                        "capability_id": "scope_probe",
                        "config_envelope": {
                            "schema_version": "1.0.0",
                            "config": {"attach": True},
                        },
                    }
                ]
            },
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["capability_id"] == "scope_probe"
        assert results[0]["manifest_version"] == "1.0.0"
        assert [c["widget"] for c in results[0]["controls"]] == [
            "attach_files",
            "search_policy",
        ]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# turn-options validation (turn start)
# ---------------------------------------------------------------------------


def test_validate_turn_options_accepts_valid_slice() -> None:
    registry = _registry_with_scope()
    # No raise = valid.
    validate_turn_options(
        registry,
        selected_capability_ids=["scope_probe"],
        turn_options={"scope_probe": {"policy": "strict"}},
    )


def test_validate_turn_options_rejects_unselected_capability() -> None:
    registry = _registry_with_scope()
    with pytest.raises(TurnOptionsInvalidError):
        validate_turn_options(
            registry,
            selected_capability_ids=[],
            turn_options={"scope_probe": {"policy": "strict"}},
        )


def test_validate_turn_options_rejects_invalid_slice() -> None:
    registry = _registry_with_scope()
    with pytest.raises(TurnOptionsInvalidError):
        validate_turn_options(
            registry,
            selected_capability_ids=["scope_probe"],
            turn_options={"scope_probe": {"policy": "nonsense"}},
        )


def test_empty_turn_options_is_valid() -> None:
    registry = _registry_with_scope()
    validate_turn_options(
        registry, selected_capability_ids=["scope_probe"], turn_options={}
    )


# ---------------------------------------------------------------------------
# turn-options end to end through /agents/execute
# ---------------------------------------------------------------------------


def _execute(client: TestClient, turn_options: dict[str, Any]) -> Any:
    return client.post(
        "/pod/v1/agents/execute",
        headers={"Authorization": "Bearer test-token"},
        json={
            "agent_instance_id": "instance-cap-1",
            "input": "hi",
            "session_id": "cap-session",
            "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
            "turn_options": turn_options,
        },
    )


def test_execute_rejects_invalid_turn_options_with_422(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        agent_app_module.httpx,
        "AsyncClient",
        _fake_control_plane({"selected_capability_ids": ["scope_probe"]}),
    )
    client = _app_with_capabilities(
        tmp_path,
        monkeypatch,
        _ScopeCapability(),
        model=ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")]),
        control_plane_url="http://control-plane:8222/control-plane/v1",
    )
    try:
        # Invalid slice → typed 422 before streaming.
        resp = _execute(client, {"scope_probe": {"policy": "nonsense"}})
        assert resp.status_code == 422
        assert "scope_probe" in resp.text
        # Unknown / unselected id → also 422.
        resp = _execute(client, {"ghost": {}})
        assert resp.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_execute_passes_typed_turn_options_to_middleware(monkeypatch, tmp_path) -> None:
    SCOPE_TURN_OPTIONS.clear()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "scope_echo", "args": {"text": "yo"}}],
            ),
            AIMessage(content="done"),
        ]
    )
    monkeypatch.setattr(
        agent_app_module.httpx,
        "AsyncClient",
        _fake_control_plane({"selected_capability_ids": ["scope_probe"]}),
    )
    client = _app_with_capabilities(
        tmp_path,
        monkeypatch,
        _ScopeCapability(),
        model=model,
        control_plane_url="http://control-plane:8222/control-plane/v1",
    )
    try:
        resp = _execute(client, {"scope_probe": {"policy": "strict"}})
        assert resp.status_code == 200
        # The middleware saw only its own typed slice.
        assert SCOPE_TURN_OPTIONS == [{"policy": "strict"}]
    finally:
        client.__exit__(None, None, None)
