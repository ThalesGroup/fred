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
Offline unit tests for the fred-runtime agent execution app.

Ref: docs/backlog/BACKLOG.md §3d — managed agent tuning application, MCP server
     selection (C1), tuning value application via _apply_runtime_tuning, KPI emission.
     Also covers: docs/backlog/BACKLOG.md §3d.9 (P1 — prompts.system overlay).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast

import pytest
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_core.common.config_loader import get_config
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.security.structure import KeycloakUser
from fred_core.users.store import postgres_user_store
from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import context as context_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import get_pod_container_from_app
from fred_runtime.runtime_context import get_runtime_context
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    InvocationScope,
    PortableContext,
    PortableEnvironment,
)
from fred_sdk.contracts.execution import (
    RuntimeExecuteRequest,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from langchain_core.messages import AIMessage


@tool("demo.echo", description="Echo the provided text.")
async def _demo_echo(ctx: ToolContext, text: str) -> str:
    """
    Return the provided text so the regression test exercises an authored tool.

    Why this exists:
    - reproduces the exact local-authored-tool path that previously failed in
      the pod app with a missing `RuntimeServices.tool_invoker`

    How to use it:
    - invoked indirectly by the test ReAct agent through the runtime

    Example:
    - `await _demo_echo(ctx, "hello")`
    """

    return f"echo:{text}"


@tool("demo.team_scope", description="Return the current team scope.")
async def _demo_team_scope(ctx: ToolContext) -> str:
    """
    Return the team id bound to the current runtime context.

    Why this exists:
    - managed agent-instance execution should override team scope from the
      control-plane resolution instead of trusting caller-supplied context

    How to use it:
    - invoked by the managed-instance regression agent through the runtime

    Example:
    - `await _demo_team_scope(ctx)`
    """

    return f"team:{ctx.binding.portable_context.team_id or 'none'}"


@tool("demo.context_prompt", description="Return the conversation context prompt.")
async def _demo_context_prompt(ctx: ToolContext) -> str:
    """
    Return the context_prompt_text bound to the current runtime context.

    Why this exists:
    - the marketplace/library prompt selected for a conversation is forwarded by
      the frontend as ``runtime_context.context_prompt_text`` and must survive the
      request → RuntimeContext binding, or no agent ever sees a selected prompt

    How to use it:
    - invoked by the context-prompt regression agent through the runtime

    Example:
    - `await _demo_context_prompt(ctx)`
    """

    return f"ctxprompt:{ctx.binding.runtime_context.context_prompt_text or 'none'}"


class _EchoAgent(ReActAgent):
    """
    Small authored agent used to validate pod runtime wiring.

    Why this exists:
    - the regression needs a real `ReActAgent` definition so toolset
      registration, declared tool refs, and runtime execution all follow the
      same authored-tool path as downstream pods

    How to use it:
    - instantiate inside the test and register it in the app registry

    Example:
    - `registry = {_EchoAgent().agent_id: _EchoAgent()}`
    """

    agent_id: str = "rags.sample.echo"
    role: str = "Echo tool agent"
    description: str = "Uses a local authored tool to echo input."
    system_prompt_template: str = "Use the demo_echo tool, then answer briefly."
    tools = (_demo_echo,)


class _TeamScopeAgent(ReActAgent):
    """
    Small agent used to assert managed team scoping in pod execution tests.

    Why this exists:
    - the pod should execute an `agent_instance_id` using the team resolved by
      control-plane, and this agent exposes that scope through a tiny authored
      tool

    How to use it:
    - register it only in the managed-instance regression test

    Example:
    - `registry = {_TeamScopeAgent().agent_id: _TeamScopeAgent()}`
    """

    agent_id: str = "sentinel.react.v2"
    role: str = "Sentinel"
    description: str = "Reports the current team scope."
    system_prompt_template: str = "Use the team_scope tool and answer with its result."
    tools = (_demo_team_scope,)


def _build_test_config(
    tmp_path,
    *,
    control_plane_url: str | None = None,
    metrics_backend: str = "logging",
    kpi_process_metrics_interval_sec: int = 0,
) -> AgentPodConfig:
    """
    Build an offline pod config for the authored-tool regression test.

    Why this exists:
    - the reusable app factory expects the same structured config as a real pod
    - the test keeps everything local by using disabled security and SQLite

    How to use it:
    - call once per test with pytest's `tmp_path`

    Example:
    - `config = _build_test_config(tmp_path)`
    """

    prometheus_enabled = metrics_backend == "prometheus"
    return AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                # OpenAI-compat is opt-in (off by default, RUNTIME-07 F-A); the
                # broad app test below asserts the /v1 surface, so enable it here.
                "openai_compat": True,
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
            "ai": {
                "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1",
            },
            "observability": {
                "kpi": {
                    "log": {"enabled": True},
                    "prometheus": {"enabled": prometheus_enabled, "port": 9900},
                    "opensearch": {"enabled": False},
                    "process_metrics_interval_sec": kpi_process_metrics_interval_sec,
                },
            },
            "storage": {
                "postgres": {
                    "sqlite_path": str(tmp_path / "runtime.sqlite3"),
                }
            },
            "platform": {
                "control_plane_url": control_plane_url,
            },
        }
    )


def test_create_agent_app_executes_local_authored_tools_and_honors_base_url(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure the reusable pod app wires local authored tools through RuntimeServices.

    Why this exists:
    - before the fix, the first execution request failed with
      `ReActRuntime requires RuntimeServices.tool_invoker for demo.echo`
    - this test also verifies that the app mounts routes and OpenAPI under
      `config.app.base_url` instead of the old hardcoded `/api/v1`

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-echo-1",
                        "name": "demo_echo",
                        "args": {"text": "hello"},
                    }
                ],
            ),
            AIMessage(content="Echo complete."),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        assert client.get("/api/v1/agents").status_code == 404

        list_response = client.get("/pod/v1/agents")
        assert list_response.status_code == 200
        assert list_response.json() == ["rags.sample.echo"]

        templates_response = client.get("/pod/v1/agents/templates")
        assert templates_response.status_code == 200
        assert templates_response.json()[0]["template_agent_id"] == "rags.sample.echo"
        assert (
            templates_response.json()[0]["default_tuning"]["role"] == "Echo tool agent"
        )

        openapi_response = client.get("/pod/v1/openapi.json")
        assert openapi_response.status_code == 200
        openapi_spec = openapi_response.json()
        execute_schema = openapi_spec["paths"]["/pod/v1/agents/execute"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        messages_schema = openapi_spec["paths"][
            "/pod/v1/agents/sessions/{session_id}/messages"
        ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        list_models_schema = openapi_spec["paths"]["/v1/models"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        components = openapi_spec["components"]["schemas"]

        assert "anyOf" in execute_schema
        assert messages_schema["items"]["$ref"] == "#/components/schemas/ChatMessage"
        assert list_models_schema["$ref"] == "#/components/schemas/OpenAIModelList"
        for schema_name in (
            "RuntimeExecuteRequest",
            "AssistantDeltaRuntimeEvent",
            "AwaitingHumanRuntimeEvent",
            "FinalRuntimeEvent",
            "NodeErrorRuntimeEvent",
            "ToolCallRuntimeEvent",
            "ToolResultRuntimeEvent",
            "TurnPersistedEvent",
            "ChatMessage",
            "OpenAIModelList",
        ):
            assert schema_name in components

        execute_response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-execute",
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert execute_response.status_code == 200
        assert execute_response.json()["kind"] == "final"
        assert execute_response.json()["content"] == "Echo complete."

        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-stream",
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert stream_response.status_code == 200

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads
    assert not any("error" in payload for payload in payloads)
    assert any(payload.get("kind") == "tool_result" for payload in payloads)
    assert payloads[-1]["kind"] == "final"
    assert payloads[-1]["content"] == "Echo complete."


class _ContextPromptAgent(ReActAgent):
    """Tiny agent that surfaces the bound context_prompt_text through a tool."""

    agent_id: str = "rags.sample.context_prompt"
    role: str = "Context prompt probe"
    description: str = "Reports the conversation context prompt it received."
    system_prompt_template: str = "Use the demo_context_prompt tool, then answer."
    tools = (_demo_context_prompt,)


def test_execute_forwards_context_prompt_text_to_agent_binding(
    monkeypatch, tmp_path
) -> None:
    """
    Regression: `runtime_context.context_prompt_text` must reach the agent binding.

    Why this exists:
    - the control-plane resolves a session's attached marketplace/library prompts
      into `context_prompt_text` and the frontend forwards it, but the runtime
      rebuilt `RuntimeContext` from the request and silently dropped this field —
      so a selected prompt never reached any agent. The admin self-test harness
      caught it live (the agent echoed `context_prompt: (none)`).

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
    """

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-ctx-1",
                        "name": "demo_context_prompt",
                        "args": {},
                    }
                ],
            ),
            AIMessage(content="Done."),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _ContextPromptAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            json={
                "agent_id": "rags.sample.context_prompt",
                "input": "hello",
                "session_id": "session-ctx",
                "runtime_context": {
                    "user_id": "alice",
                    "context_prompt_text": "CTXMARKER-9f3a",
                },
            },
        )
        assert stream_response.status_code == 200

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_response.text.splitlines()
        if line.startswith("data: ")
    ]
    tool_results = [p for p in payloads if p.get("kind") == "tool_result"]
    assert tool_results, "expected a tool_result event"
    # The tool echoed the bound context_prompt_text — proving the field survived
    # the request → RuntimeContext binding (not dropped → not "ctxprompt:none").
    assert any("CTXMARKER-9f3a" in p.get("content", "") for p in tool_results)


def test_create_agent_app_executes_managed_agent_instances_via_control_plane(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure agent-instance execution resolves template+tuning from control-plane.

    Why this exists:
    - pods now accept `agent_instance_id` in addition to raw `agent_id`
    - the resolved team scope must drive runtime tool behavior rather than any
      caller-provided ad hoc team context

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    class _FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = json.dumps(payload)
            self.reason_phrase = "OK"

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None):
            assert (
                url
                == "http://control-plane:8222/control-plane/v1/teams/fredlab/agent-instances/instance-1/runtime"
            )
            assert headers == {"Authorization": "Bearer test-token"}
            return _FakeResponse(
                {
                    "agent_instance_id": "instance-1",
                    "template_agent_id": "sentinel.react.v2",
                    "owner_scope": "team",
                    "owner_team_id": "fredlab",
                    "enabled": True,
                    "tuning": {
                        "role": "Sentinel",
                        "description": "Reports the current team scope.",
                        "tags": ["ops"],
                        "fields": [],
                    },
                }
            )

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-team-scope-1",
                        "name": "demo_team_scope",
                        "args": {},
                    }
                ],
            ),
            AIMessage(content="Managed execution complete."),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(agent_app_module.httpx, "AsyncClient", _FakeAsyncClient)

    definition = _TeamScopeAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane:8222/control-plane/v1",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            headers={"Authorization": "Bearer test-token"},
            json={
                "agent_instance_id": "instance-1",
                "input": "what team am I in?",
                "session_id": "managed-session",
                "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "final"
    assert payload["content"] == "Managed execution complete."


def test_managed_execution_rejects_grant_with_mismatched_team(
    monkeypatch, tmp_path
) -> None:
    """RUNTIME-07 F4 (Phase 1): a grant whose team_id differs from the resolved
    instance's owner_team_id must be refused with 403, even though the grant is
    otherwise structurally valid. This is the runtime-side team binding that
    `_validate_grant_team_binding` performs after control-plane resolution.

    The Phase 0 characterization
    (`test_main.py`/`test_execution_contracts.py`) documented that team_id was
    never checked; this proves the binding is now enforced."""

    class _FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = json.dumps(payload)
            self.reason_phrase = "OK"

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None):
            # Resolution says the instance is owned by "fredlab".
            return _FakeResponse(
                {
                    "agent_instance_id": "instance-1",
                    "template_agent_id": "sentinel.react.v2",
                    "owner_scope": "team",
                    "owner_team_id": "fredlab",
                    "enabled": True,
                    "tuning": {
                        "role": "Sentinel",
                        "description": "Reports the current team scope.",
                        "tags": ["ops"],
                        "fields": [],
                    },
                }
            )

    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="should not be reached")]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(agent_app_module.httpx, "AsyncClient", _FakeAsyncClient)

    definition = _TeamScopeAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane:8222/control-plane/v1",
        ),
    )

    # The caller claims a DIFFERENT team than the resolved owner_team_id. Team-scoped
    # resolution + `_validate_resolved_team` must reject the cross-team attempt.
    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            headers={"Authorization": "Bearer test-token"},
            json={
                "agent_instance_id": "instance-1",
                "input": "what team am I in?",
                "session_id": "managed-session",
                "runtime_context": {"user_id": "alice", "team_id": "intruder-team"},
            },
        )

    assert response.status_code == 403
    assert "team" in response.json()["detail"].lower()


def test_create_agent_app_initializes_user_store_during_startup(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure pod startup initializes the shared UserStore before secured requests.

    Why this test exists:
    - secured pod routes depend on `get_current_user()`, which now always asks
      for a `UserStore`
    - a missing startup initialization caused real `POST /agents/execute/stream`
      requests to fail with `StoreNotInitializedError`

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
    - the test resets the module-global store first, then starts a pod app and
      asserts startup rebuilt it from the pod SQL configuration

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="startup ready")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    postgres_user_store._user_store = None

    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app):
        assert postgres_user_store.get_user_store() is not None


def test_create_agent_app_overrides_shared_config_dependency(tmp_path) -> None:
    """
    Ensure agent pods expose the shared config dependency expected by security.

    Why this test exists:
    - `fred_core.security.oidc.get_current_user()` resolves configuration
      through `Depends(get_config)`
    - without a pod-level override, secured `/agents/execute*` routes fail at
      request time with `NotImplementedError`

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    config = _build_test_config(tmp_path)
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=config,
    )

    provider = app.dependency_overrides[get_config]
    resolved = provider()
    assert resolved is config
    assert resolved.app.gcu_version is None


def test_create_agent_app_bootstraps_prometheus_kpis_and_background_emitters(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure pod startup restores the historical Prometheus KPI wiring.

    Why this exists:
    - the old Fred backends exposed Prometheus metrics and periodic process/pool
      KPIs, but `fred-runtime` still defaulted to a no-op writer
    - this regression locks the backend completeness gate before CLI `/kpi`
      support starts depending on the metrics surface

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    observed: dict[str, object] = {}

    def _fake_start_http_server(port: int, addr: str = "127.0.0.1") -> tuple[object]:
        observed["metrics_server"] = (port, addr)

        class _FakeServer:
            def shutdown(self) -> None:
                observed["metrics_shutdown"] = True

        return (_FakeServer(),)

    async def _neverending_process(interval_s: float, kpi_writer) -> None:
        observed["process_task"] = (interval_s, type(kpi_writer).__name__)
        await asyncio.sleep(3600)

    async def _neverending_pool(
        interval_s: float, kpi_writer, engine, *, pool_name: str = "postgres"
    ) -> None:
        observed["pool_task"] = (
            interval_s,
            type(kpi_writer).__name__,
            pool_name,
            engine is not None,
        )
        await asyncio.sleep(3600)

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(context_module, "start_http_server", _fake_start_http_server)
    monkeypatch.setattr(context_module, "emit_process_kpis", _neverending_process)
    monkeypatch.setattr(context_module, "emit_sql_pool_kpis", _neverending_pool)

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(
            tmp_path,
            metrics_backend="prometheus",
            kpi_process_metrics_interval_sec=7,
        ),
    )

    with TestClient(app):
        runtime_writer = get_runtime_context().config.kpi_writer
        assert isinstance(runtime_writer, KPIWriter)
        assert isinstance(runtime_writer.store, PrometheusKPIStore)
        assert isinstance(runtime_writer.store._delegate, KpiLogStore)

    assert observed["metrics_server"] == (9900, "127.0.0.1")
    assert observed["process_task"] == (7.0, "KPIWriter")
    assert observed["pool_task"] == (7.0, "KPIWriter", "fred-runtime-postgres", True)
    assert observed["metrics_shutdown"] is True


def test_create_agent_app_keeps_log_kpis_when_prometheus_is_disabled(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure logging-mode pods still get a concrete KPI writer instead of a no-op.

    Why this exists:
    - laptop benches and local debugging need KPI events even when Prometheus is
      not enabled, otherwise the CLI and summary logs have nothing to inspect

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    observed: dict[str, object] = {"metrics_server": False}

    def _unexpected_start_http_server(port: int, addr: str = "127.0.0.1") -> None:
        observed["metrics_server"] = (port, addr)
        return None

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(
        context_module, "start_http_server", _unexpected_start_http_server
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        runtime_writer = get_runtime_context().config.kpi_writer
        assert isinstance(runtime_writer, KPIWriter)
        assert isinstance(runtime_writer.store, KpiLogStore)

    assert observed["metrics_server"] is False


def test_emit_audit_event_populates_ring_buffer(minimal_config) -> None:
    """_emit_audit_event must append to the ring buffer and filter None fields."""
    container = PodApplicationContext(minimal_config)

    agent_app_module._emit_audit_event(
        container,
        "info",
        "grant_validated",
        agent_instance_id="inst-1",
        user_id="alice",
        absent_field=None,
    )

    with container._audit_events_lock:
        events = list(container.audit_events_buffer)

    assert len(events) == 1
    ev = events[0]
    assert ev["audit_event"] == "grant_validated"
    assert ev.get("agent_instance_id") == "inst-1"
    assert ev.get("user_id") == "alice"
    assert "ts" in ev
    assert "absent_field" not in ev


def test_ring_buffer_endpoints_return_seeded_events(monkeypatch, tmp_path) -> None:
    """GET /agents/kpi-turns and /agents/audit-events return pod ring buffer contents."""
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _EchoAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        container = get_pod_container_from_app(app)
        container.audit_events_buffer.clear()
        container.kpi_turns_buffer.clear()

        agent_app_module._emit_audit_event(
            container, "info", "grant_validated", user_id="bob"
        )
        from typing import cast as _cast

        from fred_runtime.app.context import KpiTurnRecord

        with container._kpi_turns_lock:
            container.kpi_turns_buffer.append(
                _cast(
                    KpiTurnRecord,
                    {
                        "ts": "2026-01-01T00:00:00+00:00",
                        "exchange_id": "ex-seed",
                        "session_id": "s-seed",
                        "user_id": "test",
                        "total_ms": 42,
                        "is_error": False,
                    },
                )
            )

        audit_resp = client.get("/pod/v1/agents/audit-events?limit=10")
        kpi_resp = client.get("/pod/v1/agents/kpi-turns?limit=10")

    assert audit_resp.status_code == 200
    assert any(e["audit_event"] == "grant_validated" for e in audit_resp.json())

    assert kpi_resp.status_code == 200
    assert any(t["session_id"] == "s-seed" for t in kpi_resp.json())


def test_emit_turn_completed_populates_kpi_turns_buffer(monkeypatch, tmp_path) -> None:
    """One /execute call must add exactly one record to the KPI turns ring buffer."""

    async def _fake_iterate(
        definition,
        request,
        access_token=None,
        *,
        team_id=None,
        registry=None,
        exchange_id=None,
        **_kwargs,
    ):
        yield {"kind": "final", "sequence": 0, "content": "pong"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        container = get_pod_container_from_app(app)
        container.kpi_turns_buffer.clear()

        resp = client.post(
            "/pod/v1/agents/execute",
            json={"agent_id": "rags.sample.echo", "input": "ping"},
        )
        assert resp.status_code == 200

        with container._kpi_turns_lock:
            turns = list(container.kpi_turns_buffer)

    assert len(turns) == 1
    assert "ts" in turns[0]
    assert "exchange_id" in turns[0]
    assert turns[0]["is_error"] is False


def test_execute_route_propagates_checkpoint_and_observability_context(
    monkeypatch, tmp_path
) -> None:
    """
    Ensure the pod bridges checkpoint and observability fields into internal execution.

    Why this exists:
    - resume validation and observability enrichment both rely on the internal
      request carrying checkpoint/correlation metadata from the public contract

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    seen: dict[str, object] = {}

    async def _fake_iterate_runtime_event_payloads(
        definition,
        request,
        access_token=None,
        *,
        team_id=None,
        registry=None,
        exchange_id=None,
        **_kwargs,
    ):
        seen["checkpoint_id"] = request.checkpoint_id
        seen["context"] = dict(request.context or {})
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )

    async def _fake_load_checkpoint(
        checkpointer, *, thread_id, checkpoint_id=None, checkpoint_ns=""
    ):
        _ = (checkpointer, thread_id, checkpoint_ns)
        return {"id": checkpoint_id or "cp-1", "channel_values": {}}

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-1",
                "checkpoint_id": "cp-1",
                "runtime_context": {
                    "user_id": "alice",
                    "team_id": "fredlab",
                    "trace_id": "trace-1",
                    "correlation_id": "corr-1",
                },
            },
        )

    assert response.status_code == 200
    assert seen["checkpoint_id"] == "cp-1"
    assert seen["context"] == {
        "session_id": "session-1",
        "checkpoint_id": "cp-1",
        "user_id": "alice",
        "team_id": "fredlab",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "execution_action": "execute",
    }


def test_local_registry_invoker_reuses_runtime_execute_projection(monkeypatch) -> None:
    """
    Ensure local agent invocation flows through the typed runtime request bridge.

    Why this exists:
    - the multi-agent memory work needs one request-projection path for HTTP and
      in-process agent calls, or new continuity fields will be duplicated again
    - this regression proves `LocalRegistryAgentInvoker` no longer hand-builds a
      separate private request payload

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    seen: dict[str, object] = {}

    async def _fake_iterate_runtime_event_payloads(
        definition,
        request,
        access_token=None,
        *,
        team_id=None,
        registry=None,
        exchange_id=None,
        **_kwargs,
    ):
        _ = (definition, access_token, team_id, registry, exchange_id)
        seen["checkpoint_id"] = request.checkpoint_id
        seen["context"] = dict(request.context or {})
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )

    definition = _EchoAgent()
    invoker = agent_app_module.LocalRegistryAgentInvoker(
        registry={definition.agent_id: definition},
        access_token="token-1",
    )

    result = asyncio.run(
        invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=PortableContext(
                    request_id="req-1",
                    correlation_id="corr-1",
                    actor="alice",
                    tenant="tenant-a",
                    environment=PortableEnvironment.DEV,
                    trace_id="trace-1",
                    session_id="session-1",
                    user_id="alice",
                    team_id="fredlab",
                ),
            )
        )
    )

    assert result.content == "ok"
    assert result.is_error is False
    assert seen["checkpoint_id"] is None
    context = seen["context"]
    assert isinstance(context, dict)
    assert context["request_id"] == "req-1"
    assert context["correlation_id"] == "corr-1"
    assert context["actor"] == "alice"
    assert context["tenant"] == "tenant-a"
    assert context["environment"] == "dev"
    assert context["trace_id"] == "trace-1"
    assert context["session_id"] == "session-1"
    assert context["user_id"] == "alice"
    assert context["team_id"] == "fredlab"
    assert context["execution_action"] == "execute"


def test_local_registry_invoker_applies_invocation_scope(monkeypatch) -> None:
    """
    RFC AGENT-INVOKE: a per-call ``InvocationScope`` narrows the callee's retrieval.

    Why this exists:
    - typed/scoped agent invocation lets one agent restrict the callee to specific
      documents/libraries; the scope must reach the callee's RuntimeContext, which is
      built from the context dict the invoker forwards
    - this proves the scope fields land on that context dict (and only when given)

    How to use it:
    - run in the default offline `fred-runtime` test suite
    """

    seen: dict[str, object] = {}

    async def _fake_iterate_runtime_event_payloads(
        definition,
        request,
        access_token=None,
        *,
        team_id=None,
        registry=None,
        exchange_id=None,
        **_kwargs,
    ):
        _ = (definition, access_token, team_id, registry, exchange_id)
        seen["context"] = dict(request.context or {})
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )

    definition = _EchoAgent()
    invoker = agent_app_module.LocalRegistryAgentInvoker(
        registry={definition.agent_id: definition},
        access_token="token-1",
    )

    def _portable() -> PortableContext:
        return PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="tenant-a",
            environment=PortableEnvironment.DEV,
            trace_id="trace-1",
            session_id="session-1",
            user_id="alice",
            team_id="fredlab",
        )

    # With scope → narrowing fields land on the forwarded context dict.
    asyncio.run(
        invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=_portable(),
                scope=InvocationScope(
                    document_uids=["doc-a", "doc-b"],
                    library_ids=["lib-1"],
                    search_policy="strict",
                ),
            )
        )
    )
    context = seen["context"]
    assert isinstance(context, dict)
    assert context["selected_document_uids"] == ["doc-a", "doc-b"]
    assert context["selected_document_libraries_ids"] == ["lib-1"]
    assert context["search_policy"] == "strict"

    # Without scope → no narrowing keys are injected (no regression).
    seen.clear()
    asyncio.run(
        invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=_portable(),
            )
        )
    )
    context = seen["context"]
    assert isinstance(context, dict)
    assert "selected_document_uids" not in context
    assert "search_policy" not in context


def test_resume_rejects_non_pending_checkpoint(monkeypatch, tmp_path) -> None:
    """
    Ensure resume requests fail fast when the checkpoint is not waiting for input.

    Why this exists:
    - stale or already-consumed checkpoints should not reach the agent runtime
    - the backend completeness gate requires explicit local validation here

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    async def _fake_load_checkpoint(
        checkpointer, *, thread_id, checkpoint_id=None, checkpoint_ns=""
    ):
        _ = (checkpointer, thread_id, checkpoint_id, checkpoint_ns)
        return {
            "id": "cp-1",
            "channel_values": {
                "runtime_kind": "graph_v2",
                "pending": False,
                "pending_checkpoint_id": "cp-1",
            },
        }

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(checkpointer=object(), audience=None)
        ),
    )
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    config = _build_test_config(tmp_path)
    app = create_agent_app(registry=registry, config=config)

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-1",
                "checkpoint_id": "cp-1",
                "resume_payload": {"choice_id": "confirm"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "checkpoint is not waiting for resume."


def test_no_security_resolves_personal_team_before_iterate(
    monkeypatch, tmp_path
) -> None:
    """
    _stream must resolve team_id to "personal" and pass it to
    _iterate_runtime_event_payloads when security is disabled and the caller
    omits team_id.

    Why this exists:
    - the resolution happens in _stream(), before calling _iterate; this test
      catches any regression where KPIs and history would receive team_id=None
    - the fake _iterate captures the team_id it was called with so we can assert
      without running a real agent

    How to use it:
    - pytest tests/test_agent_app.py::test_no_security_resolves_personal_team_before_iterate
    """

    captured: dict[str, object] = {}

    async def _fake_iterate(
        definition,
        request,
        access_token=None,
        *,
        team_id=None,
        registry=None,
        exchange_id=None,
        **_kwargs,
    ):
        captured["team_id"] = team_id
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),  # security.user.enabled=False
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream",
            # no team_id — _stream() must default to "personal"
            json={"agent_id": "rags.sample.echo", "input": "hello"},
        )

    assert response.status_code == 200
    assert captured["team_id"] == "personal"


def test_no_security_resolves_personal_team_in_portable_context(
    monkeypatch, tmp_path
) -> None:
    """
    When security is disabled and no team_id is provided, the agent's
    PortableContext must carry team_id="personal".

    Why this exists:
    - validates the full default chain end-to-end:
      no team_id in request → _iterate applies "personal" → PortableContext carries it
    - uses the _demo_team_scope authored tool as an observable side-effect
      (same pattern as test_create_agent_app_executes_managed_agent_instances)

    How to use it:
    - pytest tests/test_agent_app.py::test_no_security_resolves_personal_team_in_portable_context
    """

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "demo_team_scope",
                        "args": {},
                        "id": "call-team",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="team:personal"),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _TeamScopeAgent()
    app = create_agent_app(
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream",
            json={
                "agent_id": "sentinel.react.v2",
                "input": "what team?",
                # no team_id provided
            },
        )

    assert response.status_code == 200
    lines = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    tool_results = [e for e in lines if e.get("kind") == "tool_result"]
    assert any("team:personal" in e.get("content", "") for e in tool_results), (
        f"Expected team:personal in tool_result events, got: {tool_results}"
    )


def test_apply_runtime_tuning_applies_system_prompt_from_values() -> None:
    """
    Ensure _apply_runtime_tuning writes prompts.system into system_prompt_template.

    Why this exists:
    - control-plane stores user-set field values in AgentTuning.values; the
      runtime must apply them at execution time, not silently drop them

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_apply_runtime_tuning_applies_system_prompt_from_values -q`
    """
    from fred_runtime.app.agent_app import _apply_runtime_tuning
    from fred_sdk.contracts.models import AgentTuning

    definition = _EchoAgent()
    assert (
        definition.system_prompt_template
        == "Use the demo_echo tool, then answer briefly."
    )

    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        values={"prompts.system": "Custom override prompt."},
    )
    result = cast(_EchoAgent, _apply_runtime_tuning(definition, tuning))
    assert result.system_prompt_template == "Custom override prompt."
    assert result.policy().system_prompt_template == "Custom override prompt."


def test_apply_runtime_tuning_ignores_blank_system_prompt() -> None:
    """
    Ensure _apply_runtime_tuning does not override when prompts.system is blank.

    Why this exists:
    - an empty or whitespace-only value means "use the agent default"; the
      control-plane UI stores an empty string when the field is cleared

    How to use it:
    - run in the default offline fred-runtime test suite
    """
    from fred_runtime.app.agent_app import _apply_runtime_tuning
    from fred_sdk.contracts.models import AgentTuning

    definition = _EchoAgent()
    original = definition.system_prompt_template

    for blank in ("", "   "):
        tuning = AgentTuning(
            role=definition.role,
            description=definition.description,
            values={"prompts.system": blank},
        )
        result = cast(_EchoAgent, _apply_runtime_tuning(definition, tuning))
        assert result.system_prompt_template == original, (
            f"blank {blank!r} should not override"
        )


def test_apply_runtime_tuning_treats_empty_mcp_selection_as_activate_none() -> None:
    """
    Ensure _apply_runtime_tuning distinguishes None from [] for MCP activation.

    Why this exists:
    - #1978 retired the MCP tuning trio: MCP servers are now selected through
      `mcp:<id>` entries in `selected_capability_ids`, but the tri-state
      semantics survive the migration — None=inherited template default (all
      of `definition.default_mcp_servers`), []=activate none, a non-empty list
      of `mcp:<id>` ids=exact subset
    - runtime execution must therefore not collapse an explicit empty
      selection back to "all tools"

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_apply_runtime_tuning_treats_empty_mcp_selection_as_activate_none -q`
    """
    from fred_runtime.app.agent_app import _apply_runtime_tuning
    from fred_sdk.contracts.models import AgentTuning, MCPServerRef

    definition = _EchoAgent().model_copy(
        update={
            "default_mcp_servers": (
                MCPServerRef(id="mcp-search"),
                MCPServerRef(id="mcp-storage"),
            )
        }
    )

    inherited = cast(
        _EchoAgent,
        _apply_runtime_tuning(
            definition,
            AgentTuning(
                role=definition.role,
                description=definition.description,
                selected_capability_ids=None,
            ),
        ),
    )
    disabled = cast(
        _EchoAgent,
        _apply_runtime_tuning(
            definition,
            AgentTuning(
                role=definition.role,
                description=definition.description,
                selected_capability_ids=[],
            ),
        ),
    )

    assert [server.id for server in inherited.default_mcp_servers] == [
        "mcp-search",
        "mcp-storage",
    ]
    assert list(disabled.default_mcp_servers) == []


def test_capability_block_delivers_mcp_agent_instructions_for_active_server() -> None:
    """
    Ensure `_build_capability_block` delivers an active MCP server's catalog
    `agent_instructions` as a prompt-fragment middleware.

    Why this exists:
    - #1978 moved `agent_instructions` delivery off `_apply_runtime_tuning`
      (which no longer touches the system prompt for MCP at all) and onto each
      `mcp:<id>` capability's `_McpInstructionsMiddleware` — assembled by
      `_build_capability_block` from the agent's selected capabilities. The
      instructions must stay enforced even when an operator overrides
      `prompts.system`, since they are delivered as a separate middleware
      layer, not folded into `system_prompt_template`.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_delivers_mcp_agent_instructions_for_active_server -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
    from fred_runtime.capabilities.mcp import _McpInstructionsMiddleware
    from fred_sdk.contracts.capability import mcp_capability_id
    from fred_sdk.contracts.models import (
        AgentTuning,
        MCPServerConfiguration,
        MCPServerRef,
    )
    from fred_sdk.contracts.runtime import RuntimeServices

    definition = _EchoAgent().model_copy(
        update={"default_mcp_servers": (MCPServerRef(id="mcp-search"),)}
    )
    registry = CapabilityRegistry()
    register_mcp_capabilities(
        registry,
        [
            MCPServerConfiguration.model_validate(
                {
                    "id": "mcp-search",
                    "name": "Search",
                    "agent_instructions": "Always cite retrieved claims.",
                }
            )
        ],
    )
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=[mcp_capability_id("mcp-search")],
        values={"prompts.system": "Custom override prompt."},
    )

    block = _build_capability_block(
        registry,
        tuning,
        definition=definition,
        services=RuntimeServices(),
        user_id=None,
        session_id=None,
        team_id=None,
        agent_instance_id=None,
    )

    assert block is not None
    fragments = [
        mw._fragment
        for mw in block.middleware
        if isinstance(mw, _McpInstructionsMiddleware)
    ]
    assert fragments == ["Always cite retrieved claims."]


def test_capability_block_skips_mcp_agent_instructions_for_inactive_server() -> None:
    """
    Ensure `_build_capability_block` skips a non-selected MCP server's
    behavioral instructions.

    Why this exists:
    - tool contracts should disappear when the corresponding MCP server is not
      part of the agent's effective `selected_capability_ids` — even though
      the pod's capability registry still advertises the `mcp:<id>` capability
      for other agents

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_skips_mcp_agent_instructions_for_inactive_server -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
    from fred_runtime.capabilities.mcp import _McpInstructionsMiddleware
    from fred_sdk.contracts.capability import mcp_capability_id
    from fred_sdk.contracts.models import (
        AgentTuning,
        MCPServerConfiguration,
        MCPServerRef,
    )
    from fred_sdk.contracts.runtime import RuntimeServices

    definition = _EchoAgent().model_copy(
        update={
            "default_mcp_servers": (
                MCPServerRef(id="mcp-search"),
                MCPServerRef(id="mcp-storage"),
            )
        }
    )
    registry = CapabilityRegistry()
    register_mcp_capabilities(
        registry,
        [
            MCPServerConfiguration.model_validate(
                {
                    "id": "mcp-search",
                    "name": "Search",
                    "agent_instructions": "Always cite retrieved claims.",
                }
            ),
            MCPServerConfiguration.model_validate(
                {"id": "mcp-storage", "name": "Storage"}
            ),
        ],
    )
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=[mcp_capability_id("mcp-storage")],
    )

    block = _build_capability_block(
        registry,
        tuning,
        definition=definition,
        services=RuntimeServices(),
        user_id=None,
        session_id=None,
        team_id=None,
        agent_instance_id=None,
    )

    fragments = [
        mw._fragment
        for mw in (block.middleware if block is not None else ())
        if isinstance(mw, _McpInstructionsMiddleware)
    ]
    assert fragments == []


# ---------------------------------------------------------------------------
# RUNTIME-07 rev. 2 (C1) — pod-side OpenFGA authorization
# ---------------------------------------------------------------------------


class _FakeRebacEngine:
    """Minimal RebacEngine stand-in for `_authorize_execution_or_raise` tests."""

    def __init__(self, *, enabled: bool, deny: bool = False) -> None:
        self._enabled = enabled
        self._deny = deny
        self.calls: list[tuple[str, TeamPermission, str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def check_user_team_permission_or_raise(
        self, user: KeycloakUser, permission: TeamPermission, team_id: str
    ) -> str | None:
        self.calls.append((user.uid, permission, team_id))
        if self._deny:
            raise AuthorizationError(user.uid, permission.value, Resource.RESOURCES)
        return None


def _managed_request(team_id: str | None = "fredlab") -> RuntimeExecuteRequest:
    body: dict[str, object] = {"input": "hi", "agent_instance_id": "inst-1"}
    ctx: dict[str, object] = {"user_id": "alice"}
    if team_id is not None:
        ctx["team_id"] = team_id
    body["runtime_context"] = ctx
    return RuntimeExecuteRequest.model_validate(body)


def _wire_engine(
    monkeypatch, engine: object | None, *, security_profile: str | None = None
) -> None:
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                rebac_engine=engine, security_profile=security_profile
            )
        ),
    )


_ALICE = KeycloakUser(uid="alice", username="alice", roles=[], email=None, groups=[])


@pytest.mark.asyncio
async def test_authorize_allows_when_user_holds_team_relation(
    monkeypatch, minimal_config
) -> None:
    """An enabled engine that grants CAN_READ lets the request proceed."""
    engine = _FakeRebacEngine(enabled=True, deny=False)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(), _ALICE, container
    )

    assert engine.calls == [("alice", TeamPermission.CAN_READ, "fredlab")]
    with container._audit_events_lock:
        events = list(container.audit_events_buffer)
    assert events[-1]["audit_event"] == "rebac_authorized"


@pytest.mark.asyncio
async def test_authorize_denies_with_403_when_openfga_refuses(
    monkeypatch, minimal_config
) -> None:
    """An enabled engine that refuses maps to HTTP 403 and a denial audit event."""
    engine = _FakeRebacEngine(enabled=True, deny=True)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(
            _managed_request(), _ALICE, container
        )

    assert exc.value.status_code == 403
    with container._audit_events_lock:
        events = list(container.audit_events_buffer)
    assert events[-1]["audit_event"] == "rebac_denied"


@pytest.mark.asyncio
async def test_authorize_skips_when_security_disabled(
    monkeypatch, minimal_config
) -> None:
    """No authenticated user (dev mode) → no OpenFGA call, no raise."""
    engine = _FakeRebacEngine(enabled=True, deny=True)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(), None, container
    )

    assert engine.calls == []


@pytest.mark.asyncio
async def test_authorize_skips_when_engine_disabled(
    monkeypatch, minimal_config
) -> None:
    """A disabled (Noop) engine → identity-only, no check even with a user."""
    engine = _FakeRebacEngine(enabled=False, deny=True)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(), _ALICE, container
    )

    assert engine.calls == []


@pytest.mark.asyncio
async def test_authorize_denies_managed_without_team(
    monkeypatch, minimal_config
) -> None:
    """Managed execution with ReBAC active but no team scope → 403 (F-D)."""
    engine = _FakeRebacEngine(enabled=True, deny=False)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(
            _managed_request(team_id=None), _ALICE, container
        )

    assert exc.value.status_code == 403
    assert engine.calls == []


@pytest.mark.asyncio
async def test_authorize_forbids_direct_agent_id_under_c3(
    monkeypatch, minimal_config
) -> None:
    """Direct agent_id execution is forbidden under the c3 profile (F-D)."""
    engine = _FakeRebacEngine(enabled=True, deny=False)
    _wire_engine(monkeypatch, engine, security_profile="c3")
    container = PodApplicationContext(minimal_config)
    direct = RuntimeExecuteRequest.model_validate(
        {"input": "hi", "agent_id": "demo.agent"}
    )

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(direct, _ALICE, container)

    assert exc.value.status_code == 403
    assert engine.calls == []


@pytest.mark.asyncio
async def test_authorize_allows_direct_agent_id_without_c3(
    monkeypatch, minimal_config
) -> None:
    """Direct agent_id execution stays identity-only in dev/non-c3 (no OpenFGA)."""
    engine = _FakeRebacEngine(enabled=True, deny=True)
    _wire_engine(monkeypatch, engine, security_profile=None)
    container = PodApplicationContext(minimal_config)
    direct = RuntimeExecuteRequest.model_validate(
        {"input": "hi", "agent_id": "demo.agent"}
    )

    await agent_app_module._authorize_execution_or_raise(direct, _ALICE, container)


_WORKER = KeycloakUser(
    uid="svc-worker",
    username="service-account-fred-evaluation-worker",
    roles=["service_agent"],
    email=None,
    groups=[],
)


@pytest.mark.asyncio
async def test_authorize_allows_service_agent_scoped_to_team(
    monkeypatch, minimal_config
) -> None:
    """A service_agent caller is authorized for the request team WITHOUT any
    OpenFGA check (RFC EVAL-AUTH, Solution A) — audited as service_agent_authorized."""
    engine = _FakeRebacEngine(enabled=True, deny=True)  # would deny if consulted
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(), _WORKER, container
    )

    assert engine.calls == []  # OpenFGA never consulted for a service identity
    with container._audit_events_lock:
        events = list(container.audit_events_buffer)
    assert events[-1]["audit_event"] == "service_agent_authorized"
    assert events[-1].get("team_id") == "fredlab"


@pytest.mark.asyncio
async def test_authorize_service_agent_still_requires_team(
    monkeypatch, minimal_config
) -> None:
    """A service_agent without a team scope fails closed (403) — never global."""
    engine = _FakeRebacEngine(enabled=True, deny=False)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(
            _managed_request(team_id=None), _WORKER, container
        )

    assert exc.value.status_code == 403
    assert engine.calls == []

    assert engine.calls == []


# ---------------------------------------------------------------------------
# RUNTIME-07 rev. 2 (F-B / F-C) — JWT identity + private-per-owner sessions
# ---------------------------------------------------------------------------


class _FakeHistoryStore:
    """session_exists / session_belongs_to_user oracle for F-C tests."""

    def __init__(self, *, exists: bool, owner: str | None) -> None:
        self._exists = exists
        self._owner = owner

    async def session_exists(self, session_id: str) -> bool:
        return self._exists

    async def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        return self._owner is not None and user_id == self._owner


def _session_request(session_id: str = "s-1") -> RuntimeExecuteRequest:
    return RuntimeExecuteRequest.model_validate(
        {
            "input": "hi",
            "agent_instance_id": "inst-1",
            "session_id": session_id,
            "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
        }
    )


def _wire_history(monkeypatch, store: object) -> None:
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(history_store=store)),
    )


@pytest.mark.asyncio
async def test_session_ownership_denies_other_users_session(
    monkeypatch, minimal_config
) -> None:
    """An existing session owned by another user → 403 (private-per-owner, F-C)."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=True, owner="bob"))
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._enforce_session_ownership(
            _session_request(), _ALICE, container
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_session_ownership_allows_owner(monkeypatch, minimal_config) -> None:
    """The session owner may continue/resume their own session."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=True, owner="alice"))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        _session_request(), _ALICE, container
    )


@pytest.mark.asyncio
async def test_session_ownership_allows_new_session(
    monkeypatch, minimal_config
) -> None:
    """A brand-new session (no rows yet) → allowed; the caller becomes owner."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=False, owner=None))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        _session_request(), _ALICE, container
    )


@pytest.mark.asyncio
async def test_session_ownership_skipped_when_security_disabled(
    monkeypatch, minimal_config
) -> None:
    """No authenticated user (dev) → ownership not enforced."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=True, owner="bob"))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        _session_request(), None, container
    )


# --- CTRLP-12 C1: can_manage_platform admin branch on the delete endpoints -----


class _FakePlatformRebacEngine:
    """RebacEngine stand-in exposing has_user_permission for the C1 admin branch."""

    def __init__(self, *, enabled: bool, grant: bool) -> None:
        self._enabled = enabled
        self._grant = grant
        self.calls: list[tuple[str, object, str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def has_user_permission(
        self, user: KeycloakUser, permission: object, resource_id: str, **_kw: object
    ) -> bool:
        self.calls.append((user.uid, permission, resource_id))
        return self._grant


@pytest.mark.asyncio
async def test_caller_can_manage_platform_true_when_enabled_and_granted(
    monkeypatch,
) -> None:
    """An enforcing engine that grants can_manage_platform → admin branch active."""
    engine = _FakePlatformRebacEngine(enabled=True, grant=True)
    _wire_engine(monkeypatch, engine)

    assert await agent_app_module._caller_can_manage_platform(_ALICE) is True
    assert engine.calls == [
        ("alice", OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
    ]


@pytest.mark.asyncio
async def test_caller_can_manage_platform_false_when_denied(monkeypatch) -> None:
    """An enforcing engine that refuses the permission → no bypass (still owner-gated)."""
    engine = _FakePlatformRebacEngine(enabled=True, grant=False)
    _wire_engine(monkeypatch, engine)

    assert await agent_app_module._caller_can_manage_platform(_ALICE) is False


@pytest.mark.asyncio
async def test_caller_can_manage_platform_false_when_engine_disabled(
    monkeypatch,
) -> None:
    """A disabled (Noop) engine never grants the bypass — fails closed, dev unchanged."""
    engine = _FakePlatformRebacEngine(enabled=False, grant=True)
    _wire_engine(monkeypatch, engine)

    assert await agent_app_module._caller_can_manage_platform(_ALICE) is False
    assert engine.calls == []  # a disabled engine is never consulted


@pytest.mark.asyncio
async def test_caller_can_manage_platform_false_when_no_caller(monkeypatch) -> None:
    """No authenticated caller → no bypass (authentication is never waived)."""
    engine = _FakePlatformRebacEngine(enabled=True, grant=True)
    _wire_engine(monkeypatch, engine)

    assert await agent_app_module._caller_can_manage_platform(None) is False
    assert engine.calls == []


@pytest.mark.asyncio
async def test_identity_is_stamped_from_jwt_and_body_tokens_neutralized(
    monkeypatch, minimal_config
) -> None:
    """F-B: _authorize_and_resolve overwrites user_id from the JWT and drops
    body-supplied access_token/refresh_token in favour of the header token."""

    async def _noop(*args, **kwargs):
        return None

    target = SimpleNamespace(
        team_id="fredlab", definition=None, agent_instance_name=None
    )

    async def _fake_resolve(**kwargs):
        return target

    monkeypatch.setattr(agent_app_module, "_validate_session_checkpoint_access", _noop)
    monkeypatch.setattr(agent_app_module, "_enforce_session_ownership", _noop)
    monkeypatch.setattr(agent_app_module, "_authorize_execution_or_raise", _noop)
    monkeypatch.setattr(agent_app_module, "_resolve_agent_instance", _fake_resolve)
    monkeypatch.setattr(
        agent_app_module, "_validate_resolved_team", lambda *a, **k: None
    )
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(control_plane_url=None)),
    )

    request = RuntimeExecuteRequest.model_validate(
        {
            "input": "hi",
            "agent_instance_id": "inst-1",
            "runtime_context": {
                "user_id": "attacker",
                "team_id": "fredlab",
                "access_token": "body-token",
                "refresh_token": "body-refresh",
            },
        }
    )
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_and_resolve(
        request,
        authenticated_user=_ALICE,
        container=container,
        registry={},
        access_token="header-jwt",
    )

    assert request.runtime_context is not None
    assert request.runtime_context.user_id == "alice"  # from JWT, not body
    assert request.runtime_context.access_token == "header-jwt"
    assert request.runtime_context.refresh_token is None
    assert request.effective_user_id() == "alice"
