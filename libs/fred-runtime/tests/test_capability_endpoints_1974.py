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
Capability product surface on the pod (#1974, RFC AGENT-CAPABILITY-RFC.md
§3.4, §3.7–§3.8).

Covers:
- `GET /agents/templates` advertises the pod's installed capabilities as
  serializable `CapabilityCatalogEntry` projections (`available_capabilities`)
- `POST /agents/capabilities/{id}/validate-config` — the agent-save
  round-trip: pod-validated config wrapped in the
  `{"schema_version", "config"}` envelope; asset-slot cardinality/extension
  enforced with uniform 422s BEFORE capability code runs; binaries reach
  `validate_config` while only storage keys enter the returned envelope
- managed execution assembles the tuning-selected capabilities into the
  agent (typed config reaches the capability tool) and fails LOUDLY on an
  unknown selected capability id
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_sdk.authoring import ReActAgent
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    UploadedFile,
)
from fred_sdk.contracts.capability.context import SaveContext
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import create_agent_app
from fred_runtime.capabilities.demo import DemoEchoCapability
from test_agent_app import _build_test_config, _EchoAgent

# ---------------------------------------------------------------------------
# Test capabilities
# ---------------------------------------------------------------------------

DECK_VALIDATE_CALLS: list[list[str]] = []
PROBE_RUNS: list[dict[str, Any]] = []


class _DeckConfig(BaseModel):
    title: str = "untitled"


class _DeckStored(_DeckConfig):
    """Stored shape adds the derived asset storage key (RFC §3.2)."""

    template_key: str = ""


class _DeckCapability(AgentCapability[_DeckConfig, _DeckStored, EmptyModel]):
    """Asset-bearing capability: exactly one .pptx in slot 'template'."""

    manifest = CapabilityManifest(
        id="deck_filler",
        version="1.0.0",
        name="capability.deck_filler.name",
        description="capability.deck_filler.description",
        icon="Slideshow",
        assets=[
            AssetSlot(
                key="template",
                accepted_types=[".pptx"],
                min_count=1,
                max_count=1,
            )
        ],
    )
    ConfigModel = _DeckConfig
    StoredConfigModel = _DeckStored

    async def validate_config(
        self,
        config: _DeckConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> _DeckStored:
        DECK_VALIDATE_CALLS.append(sorted(uploads))
        upload = uploads["template"][0]
        assert upload.content  # the binary reached capability code
        # RFC §3.8: store the blob through the KF-backed asset store and keep
        # ONLY the storage key in the stored config — never the bytes.
        return _DeckStored(
            title=config.title,
            template_key=f"kf://agent-assets/{upload.filename}",
        )

    def middleware(
        self, ctx: CapabilityContext[_DeckStored, EmptyModel]
    ) -> list[AgentMiddleware]:
        return []


class _ProbeConfig(BaseModel):
    uppercase: bool = False


class _ProbeMiddleware(AgentMiddleware):
    def __init__(self, ctx: CapabilityContext[_ProbeConfig, EmptyModel]) -> None:
        super().__init__()
        config = ctx.config
        identity = ctx.identity

        @tool
        def probe_echo(text: str) -> str:
            """Echo the given text back."""

            PROBE_RUNS.append(
                {
                    "text": text,
                    "uppercase": config.uppercase,
                    "user_id": identity.user_id,
                    "team_id": identity.team_id,
                    "agent_instance_id": identity.agent_instance_id,
                }
            )
            return text.upper() if config.uppercase else text

        self.tools = [probe_echo]


class _ProbeCapability(AgentCapability[_ProbeConfig, _ProbeConfig, EmptyModel]):
    """Records the typed context its tool runs with."""

    manifest = CapabilityManifest(
        id="probe_echo",
        version="1.0.0",
        name="capability.probe_echo.name",
        description="capability.probe_echo.description",
        icon="Sensors",
    )
    ConfigModel = _ProbeConfig

    def middleware(
        self, ctx: CapabilityContext[_ProbeConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_ProbeMiddleware(ctx)]


def _app_with_capabilities(
    tmp_path, monkeypatch, *capabilities, model=None, **config_kwargs
):
    # Offline pods have no models catalog; stub the factory like every other
    # agent_app test does.
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            model
            or ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
        raising=True,
    )
    definition = _EchoAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path, **config_kwargs),
    )
    client = TestClient(app)
    client.__enter__()  # run lifespan → boot registry on app.state
    for capability in capabilities:
        app.state.capability_registry.register(capability)
    return client


# ---------------------------------------------------------------------------
# Catalog advertisement
# ---------------------------------------------------------------------------


def test_templates_advertise_pod_capabilities(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, DemoEchoCapability())
    try:
        response = client.get("/pod/v1/agents/templates")
        assert response.status_code == 200
        entries = response.json()[0]["available_capabilities"]
        assert [e["id"] for e in entries] == ["demo_echo"]
        entry = entries[0]
        assert entry["version"] == DemoEchoCapability.manifest.version
        assert entry["config_fields"][0]["key"] == "uppercase"
        assert entry["assets"] == []
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# validate-config: the agent-save round-trip
# ---------------------------------------------------------------------------


def test_validate_config_returns_versioned_envelope(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, DemoEchoCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/demo_echo/validate-config",
            data={"config": json.dumps({"uppercase": True})},
        )
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": DemoEchoCapability.manifest.version,
            "config": {"uppercase": True},
        }
    finally:
        client.__exit__(None, None, None)


def test_validate_config_unknown_capability_is_404(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, DemoEchoCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/ghost/validate-config",
            data={"config": "{}"},
        )
        assert response.status_code == 404
        assert "ghost" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_validate_config_invalid_value_is_422(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, DemoEchoCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/demo_echo/validate-config",
            data={"config": json.dumps({"uppercase": "not-a-bool"})},
        )
        assert response.status_code == 422
        assert "demo_echo" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_slot_cardinality_violation_is_422_before_capability_code(tmp_path, monkeypatch) -> None:
    DECK_VALIDATE_CALLS.clear()
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/deck_filler/validate-config",
            data={"config": json.dumps({"title": "Q3"})},
        )
        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "Asset slot 'template': expected exactly 1 file(s), got 0."
        )
        assert DECK_VALIDATE_CALLS == []  # capability code never ran
    finally:
        client.__exit__(None, None, None)


def test_slot_extension_violation_is_422_before_capability_code(tmp_path, monkeypatch) -> None:
    DECK_VALIDATE_CALLS.clear()
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/deck_filler/validate-config",
            data={"config": "{}"},
            files={"template": ("notes.txt", b"plain text", "text/plain")},
        )
        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "Asset slot 'template': file 'notes.txt' has an unsupported "
            "type; accepted: .pptx."
        )
        assert DECK_VALIDATE_CALLS == []
    finally:
        client.__exit__(None, None, None)


def test_undeclared_slot_is_422(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/deck_filler/validate-config",
            data={"config": "{}"},
            files=[
                ("template", ("deck.pptx", b"\x00", "application/octet-stream")),
                ("sidecar", ("extra.pptx", b"\x00", "application/octet-stream")),
            ],
        )
        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "Asset slot 'sidecar': capability 'deck_filler' declares no "
            "such upload slot."
        )
    finally:
        client.__exit__(None, None, None)


def test_valid_upload_reaches_capability_and_only_keys_persist(tmp_path, monkeypatch) -> None:
    DECK_VALIDATE_CALLS.clear()
    client = _app_with_capabilities(tmp_path, monkeypatch, _DeckCapability())
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/deck_filler/validate-config",
            data={"config": json.dumps({"title": "Q3 review"})},
            files={
                "template": ("deck.pptx", b"\x50\x4b\x03\x04", "application/pptx")
            },
        )
        assert response.status_code == 200
        envelope = response.json()
        assert envelope["schema_version"] == "1.0.0"
        assert envelope["config"] == {
            "title": "Q3 review",
            "template_key": "kf://agent-assets/deck.pptx",
        }
        # only the storage key persists — never the binary
        assert "\x50" not in json.dumps(envelope)
        assert DECK_VALIDATE_CALLS == [["template"]]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Managed execution assembles selected capabilities
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.reason_phrase = "OK"

    def json(self) -> dict[str, object]:
        return self._payload


def _fake_control_plane(tuning_extra: dict[str, object]):
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None):
            return _FakeResponse(
                {
                    "agent_instance_id": "instance-cap-1",
                    "template_agent_id": "rags.sample.echo",
                    "owner_scope": "team",
                    "owner_team_id": "fredlab",
                    "enabled": True,
                    "tuning": {
                        "role": "Echo tool agent",
                        "description": "Echo agent with capabilities.",
                        "tags": [],
                        "fields": [],
                        "mcp_servers": [],
                        **tuning_extra,
                    },
                }
            )

    return _FakeAsyncClient


def _execute_managed(client: TestClient, message: str) -> dict[str, Any]:
    response = client.post(
        "/pod/v1/agents/execute",
        headers={"Authorization": "Bearer test-token"},
        json={
            "agent_instance_id": "instance-cap-1",
            "input": message,
            "session_id": "cap-session",
            "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_managed_execution_runs_selected_capability_with_typed_config(
    monkeypatch, tmp_path
) -> None:
    PROBE_RUNS.clear()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-1", "name": "probe_echo", "args": {"text": "hello"}}
                ],
            ),
            AIMessage(content="Capability run complete."),
        ]
    )
    monkeypatch.setattr(
        agent_app_module.httpx,
        "AsyncClient",
        _fake_control_plane(
            {
                "selected_capability_ids": ["probe_echo"],
                "capability_config": {
                    "probe_echo": {
                        "schema_version": "1.0.0",
                        "config": {"uppercase": True},
                    }
                },
            }
        ),
    )
    client = _app_with_capabilities(
        tmp_path,
        monkeypatch,
        _ProbeCapability(),
        model=model,
        control_plane_url="http://control-plane:8222/control-plane/v1",
    )
    try:
        payload = _execute_managed(client, "shout hello")
        assert payload["kind"] == "final"
        assert payload["content"] == "Capability run complete."
        assert PROBE_RUNS == [
            {
                "text": "hello",
                "uppercase": True,
                "user_id": "alice",
                "team_id": "fredlab",
                "agent_instance_id": "instance-cap-1",
            }
        ]
    finally:
        client.__exit__(None, None, None)


def test_managed_execution_with_demo_capability_end_to_end(
    monkeypatch, tmp_path
) -> None:
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-1", "name": "demo_echo", "args": {"text": "ping"}}
                ],
            ),
            AIMessage(content="Echo done."),
        ]
    )
    monkeypatch.setattr(
        agent_app_module.httpx,
        "AsyncClient",
        _fake_control_plane(
            {
                "selected_capability_ids": ["demo_echo"],
                "capability_config": {
                    "demo_echo": {
                        "schema_version": DemoEchoCapability.manifest.version,
                        "config": {"uppercase": True},
                    }
                },
            }
        ),
    )
    client = _app_with_capabilities(
        tmp_path,
        monkeypatch,
        DemoEchoCapability(),
        model=model,
        control_plane_url="http://control-plane:8222/control-plane/v1",
    )
    try:
        payload = _execute_managed(client, "ping")
        # A successful final proves the capability tool was resolvable and
        # callable inside the loop — an unknown tool would have errored.
        assert payload["kind"] == "final"
        assert payload["content"] == "Echo done."
    finally:
        client.__exit__(None, None, None)


def test_managed_execution_with_unknown_capability_fails_loudly(
    monkeypatch, tmp_path
) -> None:
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="never used")])
    monkeypatch.setattr(
        agent_app_module.httpx,
        "AsyncClient",
        _fake_control_plane({"selected_capability_ids": ["ghost"]}),
    )
    client = _app_with_capabilities(
        tmp_path,
        monkeypatch,
        DemoEchoCapability(),
        model=model,
        control_plane_url="http://control-plane:8222/control-plane/v1",
    )
    try:
        payload = _execute_managed(client, "hi")
        # RFC §3.9: never a silent degrade — the turn surfaces a runtime
        # error naming the missing capability.
        assert payload["kind"] != "final"
        assert "ghost" in json.dumps(payload)
    finally:
        client.__exit__(None, None, None)
