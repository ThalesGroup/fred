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
from typing import Any, cast

import httpx
import pytest
from conftest import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    migrate_test_config,
)
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fred_core.common.config_loader import get_config
from fred_core.common.team_id import personal_team_id
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
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
from fred_runtime.runtime_support.checkpoints import checkpoint_config
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    InvocationScope,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.execution import (
    RuntimeExecuteRequest,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import HistoryStorePort
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import empty_checkpoint


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


@tool("demo.team_routing", description="Return the bound team routing policy snapshot.")
async def _demo_team_routing(ctx: ToolContext) -> str:
    """
    Return the team routing policy fields bound to the current runtime context.

    Why this exists:
    - control-plane resolves a team's chat_default_profile_id/operation_route_rules
      at prepare-execution and the frontend forwards them unchanged, but the
      runtime rebuilt RuntimeContext from the request and silently dropped both
      fields — so no team's routing policy ever reached model selection
      (fred_runtime.model_routing.provider.resolve_team_override always saw None)

    How to use it:
    - invoked by the team-routing regression agent through the runtime
    """

    rc = ctx.binding.runtime_context
    rule_ids = ",".join(r.rule_id for r in (rc.operation_route_rules or []))
    return f"profile:{rc.chat_default_profile_id or 'none'}|rules:{rule_ids or 'none'}"


@tool("demo.reasoning", description="Return the bound reasoning activation snapshot.")
async def _demo_reasoning(ctx: ToolContext) -> str:
    """
    Return the platform reasoning activation bound to the current runtime context.

    Why this exists:
    - the admin's per-model reasoning toggle ships through the same
      three-hop channel the two probes above cover, and `RuntimeContext` is
      rebuilt field-by-field in `agent_app._iterate_runtime_event_payloads` —
      a field nobody names is silently dropped. Both neighbours here exist
      because that already happened twice in production.
    - The blast radius is specific: model routing strips the reasoning
      settings for every model absent from this list, so a dropped field
      pins reasoning permanently off and makes the admin toggle decorative.

    How to use it:
    - invoked by the reasoning regression agent through the runtime
    """

    rc = ctx.binding.runtime_context
    ids = rc.reasoning_enabled_model_ids
    return (
        f"reasoning:{','.join(ids) if ids else 'none'}"
        f"|turn:{'unset' if rc.reasoning is None else str(rc.reasoning).lower()}"
    )


class _ReasoningAgent(ReActAgent):
    """Tiny agent that surfaces the bound reasoning activation through a tool."""

    agent_id: str = "rags.sample.reasoning"
    role: str = "Reasoning activation probe"
    description: str = "Reports the reasoning activation snapshot it received."
    system_prompt_template: str = "Use the demo_reasoning tool, then answer."
    tools = (_demo_reasoning,)


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
    config = AgentPodConfig.model_validate(
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
    # The pod refuses to start against an unmigrated database (#2290) —
    # create the Alembic-owned schema first, as the deploy migration job does.
    return migrate_test_config(config)


def test_create_agent_app_lifespan_fails_when_sql_storage_is_unreachable(
    monkeypatch, tmp_path
) -> None:
    """
    A replica whose durable SQL storage is unreachable at boot must never
    finish starting — that is what stops Kubernetes from ever marking it
    Ready (RUNTIME-EXECUTION-CONTRACT.md §8, dated entry). Regression test
    for the finding: initialize_sql() used to swallow this failure and let
    the pod start "stateless" with checkpointer/history_store silently None.
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    import fred_core.sql.base_sql as base_sql_module

    def _raise(_config):
        raise ConnectionRefusedError("could not connect to server")

    monkeypatch.setattr(base_sql_module, "create_async_engine_from_config", _raise)

    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )

    with pytest.raises(ConnectionRefusedError):
        with TestClient(app):
            pytest.fail(
                "TestClient must not finish startup when SQL storage is unreachable"
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


def test_delete_checkpoint_thread_returns_deleted_count(monkeypatch, tmp_path) -> None:
    """
    `DELETE /agents/checkpoints/{session_id}` must report how many checkpoint
    rows it actually purged, mirroring the sibling `DELETE /agents/sessions/{id}`
    (history) endpoint's `{"deleted": n}` body.

    Why this exists:
    - before this fix the endpoint returned a bare 204 with no body, so
      `ConversationErasureService` (control-plane, CTRLP-12) could not report a
      real `deleted_count` for the `runtime_checkpoint` store in its erase
      receipt — every erasure looked identical whether it purged one
      checkpoint or a hundred.

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
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
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        execute_response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-checkpoint-delete",
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert execute_response.status_code == 200

        threads_before = client.get(
            "/pod/v1/agents/checkpoints/session-checkpoint-delete"
        )
        assert threads_before.status_code == 200
        assert len(threads_before.json()["checkpoints"]) > 0

        delete_response = client.delete(
            "/pod/v1/agents/checkpoints/session-checkpoint-delete"
        )
        assert delete_response.status_code == 200
        deleted = delete_response.json()["deleted"]
        assert deleted > 0

        threads_after = client.get(
            "/pod/v1/agents/checkpoints/session-checkpoint-delete"
        )
        assert threads_after.json()["checkpoints"] == []

        # Idempotent: a retry against an already-purged thread deletes nothing.
        retry_response = client.delete(
            "/pod/v1/agents/checkpoints/session-checkpoint-delete"
        )
        assert retry_response.status_code == 200
        assert retry_response.json() == {"deleted": 0}


class _ContextPromptAgent(ReActAgent):
    """Tiny agent that surfaces the bound context_prompt_text through a tool."""

    agent_id: str = "rags.sample.context_prompt"
    role: str = "Context prompt probe"
    description: str = "Reports the conversation context prompt it received."
    system_prompt_template: str = "Use the demo_context_prompt tool, then answer."
    tools = (_demo_context_prompt,)


class _TeamRoutingAgent(ReActAgent):
    """Tiny agent that surfaces the bound team routing policy through a tool."""

    agent_id: str = "rags.sample.team_routing"
    role: str = "Team routing probe"
    description: str = "Reports the team routing policy snapshot it received."
    system_prompt_template: str = "Use the demo_team_routing tool, then answer."
    tools = (_demo_team_routing,)


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


def test_execute_forwards_team_routing_policy_to_agent_binding(
    monkeypatch, tmp_path
) -> None:
    """
    Regression: `runtime_context.chat_default_profile_id`/`operation_route_rules`
    must reach the agent binding.

    Why this exists:
    - control-plane resolves a team's routing policy at prepare-execution and the
      frontend forwards it via `runtime_context`, but the runtime rebuilt
      `RuntimeContext` from the request and silently dropped both fields — so
      `fred_runtime.model_routing.provider.resolve_team_override` always saw
      `None`, and no team's routing policy (TEAM-ROUTING-POLICY-RFC.md §3/§8)
      ever affected a real chat turn's model selection, despite the full
      control-plane API + frontend settings panel resolving and storing it.

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
    """

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-routing-1",
                        "name": "demo_team_routing",
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

    definition = _TeamRoutingAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            json={
                "agent_id": "rags.sample.team_routing",
                "input": "hello",
                "session_id": "session-routing",
                "runtime_context": {
                    "user_id": "alice",
                    "chat_default_profile_id": "chat.anthropic.claude-sonnet",
                    "operation_route_rules": [
                        {
                            "rule_id": "planning-to-haiku",
                            "operation": "planning",
                            "target_profile_id": "chat.anthropic.claude-haiku",
                        }
                    ],
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
    # The tool echoed the bound routing policy — proving both fields survived
    # the request → RuntimeContext binding (not dropped → not "profile:none").
    echoed = " ".join(p.get("content", "") for p in tool_results)
    assert "profile:chat.anthropic.claude-sonnet" in echoed
    assert "rules:planning-to-haiku" in echoed


def _run_managed_reasoning_turn(
    monkeypatch, tmp_path, *, agent_reasoning_enabled: bool
) -> str:
    """Execute one managed-instance turn on `_ReasoningAgent` and return what the
    probe tool echoed about the reasoning activation it was bound with.

    Managed, not raw `agent_id`, because level 3 lives on the instance tuning
    control-plane resolves server-side — a raw-id turn has no author and so has
    no level 3 to test.
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

        async def aclose(self) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None):
            return _FakeResponse(
                {
                    "agent_instance_id": "instance-reasoning",
                    "template_agent_id": "rags.sample.reasoning",
                    "owner_scope": "team",
                    "owner_team_id": "fredlab",
                    "enabled": True,
                    "tuning": {
                        "role": "Reasoning activation probe",
                        "description": "Reports the activation it received.",
                        "tags": [],
                        "fields": [],
                        # The agent author's own switch, resolved server-side.
                        "reasoning_enabled": agent_reasoning_enabled,
                    },
                    # The trusted, control-plane-resolved reasoning snapshot —
                    # deliberately different from whatever the request below
                    # claims, so a test that still reads the request's copy
                    # instead of this one fails loudly.
                    "reasoning_enabled_model_ids": [
                        "model__openai__mistral-small-latest"
                    ],
                }
            )

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-reasoning-1",
                        "name": "demo_reasoning",
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
    monkeypatch.setattr(agent_app_module.httpx, "AsyncClient", _FakeAsyncClient)

    definition = _ReasoningAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane:8222/control-plane/v1",
        ),
    )

    with TestClient(app) as client:
        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer test-token"},
            json={
                "agent_instance_id": "instance-reasoning",
                "input": "hello",
                "session_id": "session-reasoning",
                "runtime_context": {
                    "user_id": "alice",
                    "team_id": "fredlab",
                    # Deliberately a DIFFERENT model id than the one the fake
                    # control-plane response carries above — the pod must use
                    # control-plane's answer, never this client-supplied copy.
                    "reasoning_enabled_model_ids": [
                        "model__spoofed__should-be-ignored"
                    ],
                    # Level 4: the user's per-question choice travels on the same
                    # context, and is dropped by the same field-by-field rebuild
                    # if nobody names it.
                    "reasoning": True,
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
    return " ".join(p.get("content", "") for p in tool_results)


def test_execute_forwards_reasoning_activation_to_agent_binding(
    monkeypatch, tmp_path
) -> None:
    """
    Regression: `runtime_context.reasoning_enabled_model_ids` must reach the
    agent binding, sourced from control-plane's own runtime-binding response —
    never from the client-supplied request context.

    Why this exists:
    - dropping the field entirely is not a degraded experience, it is a dead
      feature: model routing strips reasoning settings for any model NOT in
      this list, so an empty list here means no model ever reasons however
      the admin toggles it. `_iterate_runtime_event_payloads` rebuilds
      `RuntimeContext` field-by-field, so a field that's not named is
      silently dropped — this one dropped in an earlier cut of this feature.
    - the request below deliberately sends a DIFFERENT, bogus model id than
      the fake control-plane response — this only passes if the pod uses
      control-plane's answer and ignores the client's.

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
    """

    echoed = _run_managed_reasoning_turn(
        monkeypatch, tmp_path, agent_reasoning_enabled=True
    )
    # The tool echoed the bound activation — proving the field survived the
    # control-plane → RuntimeContext binding (not dropped → not "reasoning:none")
    # and that it came from control-plane, not the client's bogus request value.
    assert "reasoning:model__openai__mistral-small-latest" in echoed
    assert "turn:true" in echoed


def test_agent_with_reasoning_disabled_ignores_platform_activation(
    monkeypatch, tmp_path
) -> None:
    """
    Regression: an agent whose author left reasoning OFF must not reason, even
    when the platform enabled the model and the request says so.

    Why this exists:
    - an earlier cut gated only the *composer control* on the author's switch,
      so an agent with the switch off showed no toggle and reasoned anyway:
      the snapshot list rode the request untouched and model routing saw an
      open ceiling. Silent, and invisible in the UI by construction.
    - the fix must live pod-side, on the server-resolved tuning, not in what
      the request carries: `reasoning_enabled_model_ids` and `reasoning` below
      are both exactly what a client would send with the toggle on.

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`
    """

    echoed = _run_managed_reasoning_turn(
        monkeypatch, tmp_path, agent_reasoning_enabled=False
    )
    assert "reasoning:none" in echoed
    # Level 4 still travels — it is the user's answer, and it is not this level's
    # job to rewrite it. The empty ceiling above is what makes the turn not reason.
    assert "turn:true" in echoed


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

        async def aclose(self) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None):
            assert (
                url
                == "http://control-plane:8222/control-plane/v1/teams/fredlab/agent-instances/instance-1/runtime"
            )
            assert headers is not None
            assert headers["Authorization"] == "Bearer test-token"
            assert headers["X-Request-Id"]  # correlation id, TURN-01
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

        async def aclose(self) -> None:
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


def _managed_resolution_payload(owner_team_id: str = "fredlab") -> dict[str, object]:
    return {
        "agent_instance_id": "instance-1",
        "template_agent_id": "sentinel.react.v2",
        "owner_scope": "team",
        "owner_team_id": owner_team_id,
        "enabled": True,
        "tuning": {
            "role": "Sentinel",
            "description": "Reports the current team scope.",
            "tags": ["ops"],
            "fields": [],
        },
    }


class _RecordingResponse:
    """Minimal httpx.Response double — status_code/json()/text only, as used by _resolve_agent_instance."""

    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.reason_phrase = "error"

    def json(self) -> dict[str, object]:
        return self._payload


def _install_recording_async_client(monkeypatch, response_factory):
    """
    Swap `httpx.AsyncClient` itself for a bare `.get()`/`.aclose()` recorder —
    the same technique the control-plane execution tests above already use —
    so the returned instance keeps the static type `httpx.AsyncClient` and can
    be passed straight to `_resolve_agent_instance(http_client=...)`.

    Returns (client, calls): `calls` is the list of recorded {"url", "headers"}
    dicts, appended to in call order — safe to inspect for ordering/isolation.
    """
    calls: list[dict[str, Any]] = []

    class _RecordingAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def get(self, url: str, headers: dict[str, str] | None = None):
            call: dict[str, Any] = {
                "url": url,
                "headers": dict(headers) if headers else None,
            }
            calls.append(call)
            return response_factory(call)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(agent_app_module.httpx, "AsyncClient", _RecordingAsyncClient)
    client = agent_app_module.httpx.AsyncClient()
    return client, calls


def _managed_instance_request() -> "agent_app_module._AgentExecuteRequest":
    return agent_app_module._AgentExecuteRequest(
        agent_instance_id="instance-1", message="hi"
    )


@pytest.mark.asyncio
async def test_resolve_agent_instance_reuses_the_injected_client_across_calls(
    monkeypatch,
) -> None:
    """TURN-01: the function must only use the caller-supplied client, never build
    its own httpx.AsyncClient per resolution — that per-turn construction was the
    finding this fix removes."""
    client, calls = _install_recording_async_client(
        monkeypatch, lambda call: _RecordingResponse(_managed_resolution_payload())
    )
    registry = {_TeamScopeAgent().agent_id: _TeamScopeAgent()}

    for _ in range(3):
        await agent_app_module._resolve_agent_instance(
            request=_managed_instance_request(),
            registry=registry,
            access_token="token-a",
            control_plane_url="http://control-plane:8222/control-plane/v1",
            http_client=client,
            team_id="fredlab",
        )

    assert len(calls) == 3  # the one injected client served every resolution


@pytest.mark.asyncio
async def test_resolve_agent_instance_does_not_leak_headers_between_calls(
    monkeypatch,
) -> None:
    """Authorization/X-Request-Id stay per-request on the shared client — no
    default header must survive from one turn's resolution to the next."""
    client, calls = _install_recording_async_client(
        monkeypatch, lambda call: _RecordingResponse(_managed_resolution_payload())
    )
    registry = {_TeamScopeAgent().agent_id: _TeamScopeAgent()}

    await agent_app_module._resolve_agent_instance(
        request=_managed_instance_request(),
        registry=registry,
        access_token="token-alice",
        control_plane_url="http://control-plane:8222/control-plane/v1",
        http_client=client,
        team_id="fredlab",
        request_id="req-alice",
    )
    await agent_app_module._resolve_agent_instance(
        request=_managed_instance_request(),
        registry=registry,
        access_token="token-bob",
        control_plane_url="http://control-plane:8222/control-plane/v1",
        http_client=client,
        team_id="fredlab",
        request_id="req-bob",
    )

    first, second = calls
    assert first["headers"] == {
        "Authorization": "Bearer token-alice",
        "X-Request-Id": "req-alice",
    }
    assert second["headers"] == {
        "Authorization": "Bearer token-bob",
        "X-Request-Id": "req-bob",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [(404, 404), (403, 403), (500, 502)],
)
async def test_resolve_agent_instance_preserves_http_error_mapping(
    monkeypatch, upstream_status: int, expected_status: int
) -> None:
    """The control-plane status → pod HTTPException mapping (404/403/other→502)
    must be unchanged now that the call runs through an injected client."""
    client, _calls = _install_recording_async_client(
        monkeypatch, lambda call: _RecordingResponse({}, status_code=upstream_status)
    )
    registry = {_TeamScopeAgent().agent_id: _TeamScopeAgent()}

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._resolve_agent_instance(
            request=_managed_instance_request(),
            registry=registry,
            access_token="token",
            control_plane_url="http://control-plane:8222/control-plane/v1",
            http_client=client,
            team_id="fredlab",
        )
    assert exc.value.status_code == expected_status


@pytest.mark.asyncio
async def test_resolve_agent_instance_supports_concurrent_calls_on_one_client(
    monkeypatch,
) -> None:
    """Multiple in-flight turns must resolve concurrently against the single
    shared client without cross-talk between their request ids/headers."""
    client, calls = _install_recording_async_client(
        monkeypatch, lambda call: _RecordingResponse(_managed_resolution_payload())
    )
    registry = {_TeamScopeAgent().agent_id: _TeamScopeAgent()}

    async def _resolve(request_id: str):
        return await agent_app_module._resolve_agent_instance(
            request=_managed_instance_request(),
            registry=registry,
            access_token="token",
            control_plane_url="http://control-plane:8222/control-plane/v1",
            http_client=client,
            team_id="fredlab",
            request_id=request_id,
        )

    request_ids = [f"req-{i}" for i in range(10)]
    results = await asyncio.gather(*[_resolve(rid) for rid in request_ids])

    assert len(results) == 10
    assert {call["headers"]["X-Request-Id"] for call in calls} == set(request_ids)


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
        return {"id": checkpoint_id or "cp-1", "channel_values": {}}, []

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
        }, []

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                checkpointer=object(), audience=None, history_store=None
            )
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


async def _write_react_v2_checkpoint(
    checkpointer, *, thread_id: str, channel_values: dict[str, Any]
):
    """
    Write one ReAct-V2-shaped checkpoint through the real `FredSqlCheckpointer`
    (the same `aput` production code uses, `graph_runtime.py::_store_pending_checkpoint`'s
    non-legacy counterpart) — no `runtime_kind`/`pending` markers, since ReAct
    V2's `create_agent()` never stamps those (#2179).
    """

    checkpoint = empty_checkpoint()
    checkpoint_id = checkpoint["id"]
    checkpoint["channel_values"] = channel_values
    checkpoint["channel_versions"] = {key: checkpoint_id for key in channel_values}
    return await checkpointer.aput(
        checkpoint_config(thread_id=thread_id),
        checkpoint,
        {"source": "update", "step": 0, "parents": {}},
        dict(checkpoint["channel_versions"]),
    )


async def _write_react_v2_interrupt(
    checkpointer,
    *,
    thread_id: str,
    interrupt_id: str,
    task_id: str = "task-1",
    channel_values: dict[str, Any] | None = None,
):
    """
    Write one ReAct-V2 checkpoint with a pending `"__interrupt__"` write
    carrying `interrupt_id` as LangGraph's own `Interrupt.id` (#2216) — the
    id `_validate_session_checkpoint_access` now requires an exact match
    against before accepting a resume. Mirrors the real production shape
    closely enough for `_pending_react_v2_interrupt_id` to read it back
    (`{"value": ..., "id": ...}`, matching the dict-shaped branch that
    function handles alongside real `Interrupt` dataclass instances).
    """

    stored_config = await _write_react_v2_checkpoint(
        checkpointer,
        thread_id=thread_id,
        channel_values=channel_values or {"messages": []},
    )
    await checkpointer.aput_writes(
        stored_config,
        [("__interrupt__", {"value": {"question": "proceed?"}, "id": interrupt_id})],
        task_id=task_id,
    )
    return stored_config


async def _hitl_claim_rows(checkpointer) -> list:
    """All rows currently in `checkpoint_hitl_claim`, for asserting a
    setup/pre-invocation failure left no claim behind (#2216)."""
    from sqlalchemy import select

    async with checkpointer.store.begin() as conn:
        return list(
            (await conn.execute(select(checkpointer.hitl_claim_table))).fetchall()
        )


def test_resume_accepts_react_v2_checkpoint_via_pending_interrupt_write(
    monkeypatch, tmp_path
) -> None:
    """
    Regression for #2179: a ReAct V2 checkpoint never carries `runtime_kind:
    graph_v2`, and the `checkpoint_id` its frontend echoes back on resume is
    actually LangGraph's `Interrupt.id` — never a real stored checkpoint id,
    so the primary exact-id lookup always misses. `_validate_session_checkpoint_access`
    must fall back to the thread's latest checkpoint and accept the resume by
    finding its pending `"__interrupt__"` write whose `Interrupt.id` matches
    the client-supplied `checkpoint_id` (#2216 tightened this from "any
    pending interrupt" to an exact id match).

    Written and read through the real `FredSqlCheckpointer` (SQLite), not a
    mock — #2179 flagged the missing coverage as exactly this gap: no test
    exercised a real write-then-read checkpoint round trip.
    """

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
        yield {"kind": "final", "sequence": 0, "content": "resumed"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )
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
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id="session-react-v2",
                interrupt_id="xxh3-routing-hash-not-a-real-checkpoint-id",
            )
        )

        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-react-v2",
                # LangGraph's Interrupt.id — never a real stored checkpoint
                # id (#2179's root cause) — but exactly the id the pending
                # write above carries (#2216's exact-match requirement).
                "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 200


def test_resume_rejects_react_v2_checkpoint_without_pending_interrupt(
    monkeypatch, tmp_path
) -> None:
    """
    The mirror-negative of the acceptance test above: a ReAct V2 checkpoint
    with no pending `"__interrupt__"` write (turn simply finished, nothing
    waiting for approval) must still 409 — the fallback lookup must not
    turn into "always accept a non-graph_v2 checkpoint".
    """

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
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        asyncio.run(
            _write_react_v2_checkpoint(
                checkpointer,
                thread_id="session-react-v2-done",
                channel_values={"messages": []},
            )
        )

        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-react-v2-done",
                "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "checkpoint is not waiting for resume."


def test_react_v2_interrupt_channel_constant_matches_langgraph() -> None:
    """
    Pins `agent_app._REACT_V2_INTERRUPT_CHANNEL` against LangGraph's own
    value. Hardcoded rather than imported in production code because the
    public `langgraph.constants.INTERRUPT` is itself deprecated ("removed in
    V2.0") — this test is the tripwire: if a LangGraph upgrade changes or
    removes that value, this fails loudly instead of silently reopening
    #2179.
    """

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.constants import INTERRUPT

    assert agent_app_module._REACT_V2_INTERRUPT_CHANNEL == INTERRUPT


def test_resume_builds_react_input_without_raising(monkeypatch, tmp_path) -> None:
    """
    Regression for the bug found immediately behind #2179's checkpoint fix
    (live-tested manually): `_iterate_runtime_event_payloads` builds
    `ReActInput(messages=())` unconditionally on a HITL resume
    (`agent_app.py`, "messages are ignored by the codec"), but
    `ReActInput.validate_messages` (`react_contract.py`) rejects an empty
    tuple — every ReAct V2 resume crashed with `ReActInput.messages must
    contain at least one message` the instant #2179's checkpoint 409 was
    fixed and this line became reachable for the first time. Fixed by
    bypassing validation with `model_construct` on resume, mirroring the
    Graph-agent branch just above it, which already did this.

    Uses a fake `AgentRuntime`/`Executor` (not a fake chat model) so this
    exercises the exact `react_input` object `_iterate_runtime_event_payloads`
    builds and passes to `executor.stream(...)`, without depending on
    LangGraph's own interrupt/resume mechanics.
    """

    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.react_contract import ReActInput, ReActOutput
    from fred_sdk.contracts.runtime import AgentRuntime, Executor, FinalRuntimeEvent

    seen: dict[str, object] = {}

    class _RecordingExecutor(Executor[ReActInput, ReActOutput]):
        async def invoke(self, input_model, config):  # noqa: ANN001
            raise NotImplementedError

        async def stream(self, input_model, config):  # noqa: ANN001
            seen["messages"] = input_model.messages
            yield FinalRuntimeEvent(content="resumed")

    class _FakeReActRuntime(
        AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]
    ):
        def __init__(self, *, definition, services, capability_block=None):
            super().__init__(definition=definition, services=services)
            _ = capability_block

        async def build_executor(self, binding: BoundRuntimeContext):
            return _RecordingExecutor()

    monkeypatch.setattr(agent_app_module, "ReActRuntime", _FakeReActRuntime)
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
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id="session-react-input-resume",
                interrupt_id="xxh3-routing-hash-not-a-real-checkpoint-id",
            )
        )

        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-react-input-resume",
                "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 200
    assert seen["messages"] == ()


@pytest.mark.asyncio
async def test_resolve_exchange_id_reuses_previous_on_resume() -> None:
    """
    A HITL resume must reuse the interrupted turn's exchange_id, not mint a
    fresh one — otherwise the pre-pause tool_call and the post-resume
    tool_result carry different exchange_ids, and the chat UI's per-exchange
    grouping (`toThreadMessages.ts`) can never reunite them: the trace step
    stays "in progress" forever even though the tool result did arrive
    (found via manual live testing of the #2179 fix).
    """

    class _FakeHistory:
        async def latest_exchange_id(self, session_id: str) -> str | None:
            assert session_id == "s1"
            return "exchange-42"

    resolved = await agent_app_module._resolve_exchange_id(
        resume_payload={"choice_id": "proceed"},
        session_id="s1",
        history_store=cast(HistoryStorePort, _FakeHistory()),
    )

    assert resolved == "exchange-42"


@pytest.mark.asyncio
async def test_resolve_exchange_id_does_not_query_history_for_a_normal_turn() -> None:
    """A normal (non-resume) turn always mints a fresh exchange_id and must
    not pay for a history lookup it doesn't need."""

    class _FailingHistory:
        async def latest_exchange_id(self, session_id: str) -> str | None:
            raise AssertionError("must not be queried for a normal turn")

    resolved = await agent_app_module._resolve_exchange_id(
        resume_payload=None,
        session_id="s1",
        history_store=cast(HistoryStorePort, _FailingHistory()),
    )

    assert resolved


@pytest.mark.asyncio
async def test_resolve_exchange_id_falls_back_when_nothing_persisted_yet() -> None:
    """Defensive fallback: a resume against a session with no persisted
    history yet (should not happen in practice) still gets a usable id
    instead of `None` reaching the runtime."""

    class _EmptyHistory:
        async def latest_exchange_id(self, session_id: str) -> str | None:
            return None

    resolved = await agent_app_module._resolve_exchange_id(
        resume_payload={"choice_id": "proceed"},
        session_id="s1",
        history_store=cast(HistoryStorePort, _EmptyHistory()),
    )

    assert resolved


def test_resume_reuses_exchange_id_from_the_interrupted_turn(
    monkeypatch, tmp_path
) -> None:
    """
    End-to-end proof through the real SQL history store: the first (pausing)
    call and the resume that completes it must persist under the SAME
    exchange_id.
    """

    call_count = 0

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
        nonlocal call_count
        call_count += 1
        _ = (definition, access_token, team_id, registry)
        yield {"kind": "final", "sequence": 0, "content": f"turn-{call_count}"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )
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
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        first = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-exchange-continuity",
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert first.status_code == 200

        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id="session-exchange-continuity",
                interrupt_id="xxh3-routing-hash-not-a-real-checkpoint-id",
            )
        )

        resume = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-exchange-continuity",
                "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert resume.status_code == 200

        history_store = get_runtime_context().config.history_store
        assert history_store is not None
        rows = asyncio.run(history_store.get("session-exchange-continuity"))

    exchange_ids = {row.exchange_id for row in rows}
    assert len(exchange_ids) == 1, (
        f"expected one shared exchange_id across the interrupted turn and its "
        f"resume, got {exchange_ids}"
    )


# ---------------------------------------------------------------------------
# #2216 P1 — HITL resume bound to a unique interrupt occurrence
# ---------------------------------------------------------------------------


def _make_counting_fake_iterate():
    """
    Shared fake `_iterate_runtime_event_payloads` for tests that only
    exercise the READ-ONLY early gate (`_validate_session_checkpoint_access`
    — the interrupt_id exact-match check): records every call's
    `interrupt_id` so a test can assert exactly which (and how many)
    resumes reached the runtime — a request rejected by that gate never
    reaches this function at all.

    Do NOT use this for tests that need the durable single-use CLAIM to be
    exercised (replay-after-success, concurrent duplicates): the claim is
    acquired deep inside the real `_iterate_runtime_event_payloads`, so
    faking that whole function out bypasses it entirely. Use
    `_make_counting_react_runtime` instead for those — it fakes only
    `ReActRuntime`/`Executor`, leaving the real claim code path intact.
    """

    calls: list[str | None] = []

    async def _fake(
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
        calls.append(request.interrupt_id)
        yield {"kind": "final", "sequence": 0, "content": f"turn-{len(calls)}"}

    return _fake, calls


def _make_counting_react_runtime():
    """
    Controllable `ReActRuntime`/`Executor` double that lets the REAL claim
    acquisition code in `_iterate_runtime_event_payloads` run (unlike
    `_make_counting_fake_iterate`, which bypasses that whole function).
    `calls` records one entry per actual `executor.stream(...)` — the real
    proof that a rejected or duplicate resume never executes the tool loop.
    """

    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.react_contract import ReActInput, ReActOutput
    from fred_sdk.contracts.runtime import AgentRuntime, Executor, FinalRuntimeEvent

    calls: list[int] = []

    class _RecordingExecutor(Executor[ReActInput, ReActOutput]):
        async def invoke(self, input_model, config):  # noqa: ANN001
            raise NotImplementedError

        async def stream(self, input_model, config):  # noqa: ANN001
            calls.append(len(calls) + 1)
            yield FinalRuntimeEvent(content=f"resumed-{len(calls)}")

    class _RecordingReActRuntime(
        AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]
    ):
        def __init__(self, *, definition, services, capability_block=None):
            super().__init__(definition=definition, services=services)
            _ = capability_block

        async def build_executor(self, binding: BoundRuntimeContext):
            return _RecordingExecutor()

    return _RecordingReActRuntime, calls


def test_resume_stale_response_cannot_approve_a_later_interrupt(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 P1 — the sequential stale-response attack:
    1. interrupt A is pending and gets resumed with its own id.
    2. the thread later reaches interrupt B — a DIFFERENT id.
    3. a delayed/duplicated response carrying A's stale id must be rejected
       (409) without ever reaching the runtime — B stays pending.
    4. resuming with B's own id succeeds and reaches the runtime exactly
       once.
    """

    fake_iterate, calls = _make_counting_fake_iterate()
    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", fake_iterate
    )
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-stale-attack"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        # 1. interrupt A is pending; resume it with its own id.
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
            )
        )
        resume_a = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert resume_a.status_code == 200
        assert calls == ["interrupt-a"]

        # 2. the thread later reaches interrupt B — a different id.
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-b"
            )
        )
        assert "interrupt-a" != "interrupt-b"

        # 3. a stale/duplicated response for A must be rejected — and must
        # never reach the runtime (B's tool has not executed).
        stale_resume = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert stale_resume.status_code == 409
        assert stale_resume.json()["detail"] == (
            "interrupt_id does not match the pending HITL request for this session."
        )
        assert calls == ["interrupt-a"]  # unchanged — B never executed

        # 4. resuming with B's own id succeeds, exactly once.
        resume_b = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-b",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )
        assert resume_b.status_code == 200
        assert calls == ["interrupt-a", "interrupt-b"]


def test_resume_replay_after_success_does_not_execute_again(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 P1 — once an interrupt occurrence has been resumed successfully,
    replaying the SAME response (same interrupt_id) must not execute the
    tool a second time.

    The interrupt_id match check alone would NOT catch this: nothing in
    this fake advances the underlying checkpoint, so the replay still
    matches the (unchanged) pending interrupt at the early, read-only gate.
    It is the durable single-use CLAIM — acquired deep inside
    `_iterate_runtime_event_payloads`, immediately before invocation — that
    actually rejects it. That is also why the replay surfaces as a
    `RuntimeErrorEvent` (HTTP 200, kind="execution_error") rather than a
    clean 409: by the time the claim step runs, the streaming endpoint's
    response has already started (see `_claim_hitl_resume_before_invocation`'s
    docstring). Uses `_make_counting_react_runtime`, NOT
    `_make_counting_fake_iterate`, specifically so the real claim code path
    is exercised instead of bypassed.
    """

    RecordingReActRuntime, calls = _make_counting_react_runtime()
    monkeypatch.setattr(agent_app_module, "ReActRuntime", RecordingReActRuntime)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-replay"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
            )
        )
        payload = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "interrupt_id": "interrupt-a",
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }

        first = client.post("/pod/v1/agents/execute", json=payload)
        assert first.status_code == 200
        assert first.json().get("kind") == "final"
        assert calls == [1]

        replay = client.post("/pod/v1/agents/execute", json=payload)

    assert replay.status_code == 200
    assert replay.json().get("kind") == "execution_error"
    assert replay.json().get("message") == "This HITL request is already being resumed."
    assert calls == [1]  # unchanged — no second execution


@pytest.mark.parametrize(
    "interrupt_id",
    [
        pytest.param(None, id="missing"),
        pytest.param("", id="empty"),
        pytest.param("not-a-real-interrupt-id", id="malformed"),
        pytest.param("a" * 32, id="unknown-but-well-formed"),
    ],
)
def test_resume_rejects_non_matching_interrupt_id_variants(
    monkeypatch, tmp_path, interrupt_id
) -> None:
    """
    #2216 P1 fail-closed matrix: missing, empty, malformed, or simply
    unknown `interrupt_id` values must all be rejected the same way as a
    genuinely stale one — never treated as "some interrupt is pending, so
    let it through" (the pre-#2216 behavior).
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-invalid-input"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-real"
            )
        )

        body: dict[str, Any] = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }
        if interrupt_id is not None:
            body["interrupt_id"] = interrupt_id

        response = client.post("/pod/v1/agents/execute", json=body)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "interrupt_id does not match the pending HITL request for this session."
    )


def test_resume_rejects_token_belonging_to_another_thread(
    monkeypatch, tmp_path
) -> None:
    """A token that is genuinely valid — but for a DIFFERENT thread's
    pending interrupt — must not resume this thread's own pending
    interrupt."""

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
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id="session-thread-a", interrupt_id="interrupt-a"
            )
        )
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id="session-thread-b", interrupt_id="interrupt-b"
            )
        )

        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": "session-thread-a",
                "interrupt_id": "interrupt-b",  # belongs to thread B, not A
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "interrupt_id does not match the pending HITL request for this session."
    )


@pytest.mark.asyncio
async def test_concurrent_duplicate_resumes_have_exactly_one_winner(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 P1 — two simultaneous resume requests for the SAME pending
    interrupt: the atomic claim (`_claim_hitl_resume_before_invocation`,
    which `_iterate_runtime_event_payloads` calls immediately before
    invoking the graph) must let exactly one through and reject every
    other one, deterministically (first writer wins), never both.
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    with TestClient(app):
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        await _write_react_v2_interrupt(
            checkpointer, thread_id="session-concurrent", interrupt_id="interrupt-a"
        )

        async def _attempt():
            try:
                claim = await agent_app_module._claim_hitl_resume_before_invocation(
                    session_id="session-concurrent", interrupt_id="interrupt-a"
                )
                return "ok" if claim is not None else "none"
            except RuntimeError:
                return "rejected"

        results = await asyncio.gather(*[_attempt() for _ in range(5)])

    assert results.count("ok") == 1
    assert results.count("rejected") == 4


@pytest.mark.asyncio
async def test_concurrent_duplicate_resumes_execute_the_tool_at_most_once(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 — end to end through the real HTTP surface, not just the claim
    primitive: two GENUINELY concurrent `/agents/execute` requests
    resuming the SAME pending interrupt must result in
    `executor.stream(...)` — the tool loop itself — running at most once.

    Uses `httpx.AsyncClient` over `ASGITransport` (real concurrent
    coroutines racing the same running app), not two `TestClient` calls
    (synchronous, cannot overlap) and not two separate `create_agent_app`
    instances (`get_runtime_context()` is a single process-wide global —
    see `test_concurrent_claims_across_separate_checkpointer_instances_have_one_winner`
    in `test_sql_checkpointer_hitl_claim.py` for the cross-replica proof at
    the layer that constraint actually allows testing).
    """

    RecordingReActRuntime, calls = _make_counting_react_runtime()
    monkeypatch.setattr(agent_app_module, "ReActRuntime", RecordingReActRuntime)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-dup-http-concurrent"

    with TestClient(app):
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        await _write_react_v2_interrupt(
            checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
        )

        payload = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "interrupt_id": "interrupt-a",
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            responses = await asyncio.gather(
                async_client.post("/pod/v1/agents/execute", json=payload),
                async_client.post("/pod/v1/agents/execute", json=payload),
            )

    kinds = sorted(r.json().get("kind") for r in responses)
    assert [r.status_code for r in responses] == [200, 200]
    assert kinds == ["execution_error", "final"]
    assert calls == [1]  # the tool loop ran exactly once


def test_resume_runtime_setup_failure_leaves_no_claim_and_retry_succeeds(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 — a runtime construction failure happens BEFORE the claim is ever
    acquired (the claim is acquired as late as possible, immediately
    before `executor.stream(...)` — see
    `_claim_hitl_resume_before_invocation`'s docstring and
    `_validate_session_checkpoint_access`'s read-only guarantee). A setup
    failure must therefore leave no claim row behind at all, so an
    immediate retry (once the failure condition clears) succeeds without
    waiting out any TTL.
    """

    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.react_contract import ReActInput, ReActOutput
    from fred_sdk.contracts.runtime import AgentRuntime, Executor, FinalRuntimeEvent

    attempt = 0

    class _FlakyReActRuntime(
        AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]
    ):
        def __init__(self, *, definition, services, capability_block=None):
            super().__init__(definition=definition, services=services)
            _ = capability_block

        async def build_executor(self, binding: BoundRuntimeContext):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise RuntimeError("forced setup failure")

            class _RecordingExecutor(Executor[ReActInput, ReActOutput]):
                async def invoke(self, input_model, config):  # noqa: ANN001
                    raise NotImplementedError

                async def stream(self, input_model, config):  # noqa: ANN001
                    yield FinalRuntimeEvent(content="resumed")

            return _RecordingExecutor()

    monkeypatch.setattr(agent_app_module, "ReActRuntime", _FlakyReActRuntime)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-setup-failure"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
            )
        )
        payload = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "interrupt_id": "interrupt-a",
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }

        first = client.post("/pod/v1/agents/execute", json=payload)
        # The runtime construction failure surfaces as a RuntimeErrorEvent
        # payload (see `_iterate_runtime_event_payloads`'s outer except), not
        # an HTTP error — the terminal-payload contract for a mid-turn
        # failure on the non-streaming endpoint.
        assert first.status_code == 200
        assert first.json().get("kind") == "execution_error"

        claim_rows = asyncio.run(_hitl_claim_rows(checkpointer))
        assert claim_rows == []  # setup failed before any claim was acquired

        retry = client.post("/pod/v1/agents/execute", json=payload)

    assert retry.status_code == 200
    assert retry.json().get("kind") == "final"
    assert attempt == 2


def test_resume_start_failure_releases_the_claim_for_a_retry(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 — if `astart_hitl_resume` itself fails (a transient DB error)
    while the caller still legitimately holds 'claimed' status,
    `_claim_hitl_resume_before_invocation` releases the row so a retry
    does not have to wait out the TTL. Forces the failure by monkeypatching
    `FredSqlCheckpointer.astart_hitl_resume` to raise exactly once.
    """

    RecordingReActRuntime, calls = _make_counting_react_runtime()
    monkeypatch.setattr(agent_app_module, "ReActRuntime", RecordingReActRuntime)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    real_astart = agent_app_module.FredSqlCheckpointer.astart_hitl_resume
    attempts = 0

    async def _flaky_astart(self, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("forced transient DB failure")
        return await real_astart(self, **kwargs)

    monkeypatch.setattr(
        agent_app_module.FredSqlCheckpointer, "astart_hitl_resume", _flaky_astart
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-start-failure"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
            )
        )
        payload = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "interrupt_id": "interrupt-a",
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }

        first = client.post("/pod/v1/agents/execute", json=payload)
        assert first.status_code == 200
        assert first.json().get("kind") == "execution_error"
        assert calls == []  # never reached executor.stream(...)

        claim_rows = asyncio.run(_hitl_claim_rows(checkpointer))
        assert claim_rows == []  # released, not left stranded

        retry = client.post("/pod/v1/agents/execute", json=payload)

    assert retry.status_code == 200
    assert retry.json().get("kind") == "final"
    assert calls == [1]
    assert attempts == 2


@pytest.mark.asyncio
async def test_cancellation_after_start_leaves_the_claim_stuck_not_released(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 item 3 — a cancelled turn (task cancellation, an SSE/browser
    disconnect, or the frontend's `AbortController` firing) after the claim
    reaches 'started' but before the turn finishes must NOT release or
    steal the claim. This is the documented, deliberate safety-first
    limitation (see `FredSqlCheckpointer.aclaim_hitl_resume`'s "Explicitly
    NOT guaranteed" section): a 'started' row has no automatic recovery —
    the occurrence stays permanently claimed until an operator purges the
    thread. Proves both halves of that limitation directly:
    (a) the claim row is still 'started', completely unchanged, after
    cancellation, and
    (b) a duplicate resume attempt for the same occurrence cannot enter the
    executor while that claim is held.

    `/agents/execute` consumes `_iterate_runtime_event_payloads` with a
    plain `[payload async for payload in ...]` in the SAME task as the ASGI
    request handling (no shielding, no background task) — so cancelling
    the outer coroutine that's `await`ing the HTTP call (exactly what
    happens when `httpx.ASGITransport` runs the app in-process) delivers a
    real `asyncio.CancelledError` at whatever point the generator is
    currently suspended, which is the same mechanism a real client
    disconnect or `AbortController` ultimately triggers server-side.
    """

    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.react_contract import ReActInput, ReActOutput
    from fred_sdk.contracts.runtime import AgentRuntime, Executor, FinalRuntimeEvent

    calls: list[int] = []
    started_running = asyncio.Event()

    class _HangingExecutor(Executor[ReActInput, ReActOutput]):
        async def invoke(self, input_model, config):  # noqa: ANN001
            raise NotImplementedError

        async def stream(self, input_model, config):  # noqa: ANN001
            calls.append(len(calls) + 1)
            started_running.set()
            # Never set — blocks forever, simulating a genuinely in-flight
            # invocation. The claim is already 'started' by the time this
            # runs (`_iterate_runtime_event_payloads` acquires it BEFORE
            # entering `executor.stream(...)`).
            await asyncio.Event().wait()
            yield FinalRuntimeEvent(content="unreachable")  # pragma: no cover

    class _HangingReActRuntime(
        AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]
    ):
        def __init__(self, *, definition, services, capability_block=None):
            super().__init__(definition=definition, services=services)
            _ = capability_block

        async def build_executor(self, binding: BoundRuntimeContext):
            return _HangingExecutor()

    monkeypatch.setattr(agent_app_module, "ReActRuntime", _HangingReActRuntime)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))
    session_id = "session-cancel-mid-invocation"

    with TestClient(app):
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        await _write_react_v2_interrupt(
            checkpointer, thread_id=session_id, interrupt_id="interrupt-a"
        )
        payload = {
            "agent_id": "rags.sample.echo",
            "input": "",
            "session_id": session_id,
            "interrupt_id": "interrupt-a",
            "resume_payload": {"choice_id": "proceed"},
            "runtime_context": {"user_id": "alice"},
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            request_task = asyncio.ensure_future(
                async_client.post("/pod/v1/agents/execute", json=payload)
            )
            await asyncio.wait_for(started_running.wait(), timeout=5.0)

            request_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request_task

            assert calls == [1]  # the executor started exactly once

            claim_rows = await _hitl_claim_rows(checkpointer)
            assert len(claim_rows) == 1
            assert claim_rows[0].status == "started"  # not released, not consumed

            # A duplicate resume attempt must not enter the executor while
            # the claim from the cancelled attempt is still held.
            duplicate = await async_client.post("/pod/v1/agents/execute", json=payload)

    assert duplicate.status_code == 200
    assert duplicate.json().get("kind") == "execution_error"
    assert (
        duplicate.json().get("message") == "This HITL request is already being resumed."
    )
    assert calls == [1]  # the duplicate never reached the executor

    # The claim is still 'started', exactly as it was right after
    # cancellation — nothing about a rejected duplicate attempt changes it.
    claim_rows = await _hitl_claim_rows(checkpointer)
    assert len(claim_rows) == 1
    assert claim_rows[0].status == "started"


def test_normal_react_turn_without_resume_is_unaffected(monkeypatch, tmp_path) -> None:
    """#2216 non-regression: a plain ReAct turn with no interrupt at all
    must complete normally — the new checkpoint/claim logic is only reached
    when `resume_payload` is set."""

    fake_iterate, calls = _make_counting_fake_iterate()
    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", fake_iterate
    )
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
                "session_id": "session-normal-turn",
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 200
    assert calls == [None]


@pytest.mark.asyncio
async def test_normal_turn_does_not_query_the_checkpointer(monkeypatch) -> None:
    """#2216 non-regression: `_validate_session_checkpoint_access` must
    return immediately (no checkpointer lookup at all) for a turn that sets
    neither `checkpoint_id` nor `resume_payload` — matching the existing
    fast-path contract this function has always had."""

    def _boom():
        raise AssertionError(
            "a normal turn must not touch get_runtime_context() at all"
        )

    request = RuntimeExecuteRequest(
        agent_id="rags.sample.echo",
        input="hello",
        session_id="session-normal-fastpath",
        runtime_context=RuntimeContext(user_id="alice"),
    )

    monkeypatch.setattr(agent_app_module, "get_runtime_context", _boom)
    await agent_app_module._validate_session_checkpoint_access(request)


def test_execute_rejects_checkpoint_id_and_interrupt_id_together(
    monkeypatch, tmp_path
) -> None:
    """
    #2216 — `checkpoint_id` (legacy Graph V2) and `interrupt_id` (ReAct V2)
    are mutually exclusive on the wire contract itself
    (`RuntimeExecuteRequest._validate_execution_target`), so a request
    naming both fails FastAPI's request-body validation (422) before
    `_validate_session_checkpoint_access` — or any checkpointer lookup — is
    ever reached.
    """

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
                "input": "",
                "session_id": "session-both-ids",
                "checkpoint_id": "cp-1",
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 422


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
      plain server-id entries in `selected_capability_ids` (#1988 dropped the
      `mcp:` id prefix — the capability id IS the catalog server id), but the
      tri-state semantics survive the migration — None=inherited template
      default (all of `definition.default_mcp_servers`), []=activate none, a
      non-empty list of server ids=exact subset
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
      MCP server's own capability `_McpInstructionsMiddleware` — assembled by
      `_build_capability_block` from the agent's selected capabilities. #1988
      dropped the `mcp:` id prefix: the capability id IS the catalog server
      id (`server.id`). The instructions must stay enforced even when an
      operator overrides `prompts.system`, since they are delivered as a
      separate middleware layer, not folded into `system_prompt_template`.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_delivers_mcp_agent_instructions_for_active_server -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
    from fred_runtime.capabilities.mcp import _McpInstructionsMiddleware
    from fred_sdk.contracts.capability import TeamScopePolicy
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
    # #1988: the capability id IS the plain catalog server id (no `mcp:`
    # prefix), and team_scope flows from the catalog entry's default.
    registered = registry.capability("mcp-search")
    assert registered.manifest.id == "mcp-search"
    assert registered.manifest.team_scope is TeamScopePolicy.ADMIN_GATED
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["mcp-search"],
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
      the pod's capability registry still advertises the server's capability
      (keyed by its plain server id, #1988) for other agents

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_skips_mcp_agent_instructions_for_inactive_server -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
    from fred_runtime.capabilities.mcp import _McpInstructionsMiddleware
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
        selected_capability_ids=["mcp-storage"],
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


def test_build_capability_block_for_graph_agent_returns_tools() -> None:
    """
    Ensure `_build_capability_block` builds a non-empty block for a Graph agent
    (Phase 3, NOTES-GRAPH-CAPABILITY-BRIDGE.md).

    Why this exists:
    - `_build_capability_block` and `_effective_capability_ids` used to gate
      capabilities to `ReActAgentDefinition` only, raising `CapabilityError`
      for any `GraphAgentDefinition` selecting a real (non-MCP) capability.
      That gate is gone: a Graph agent can now select a capability and get
      its `tools()` output collected into `block.tools`, exactly like a
      ReAct agent would. Nothing yet reads `block.tools` on the Graph
      execution path — `GraphRuntime` still ignores `capability_block`
      entirely (Phase 4) — so this only proves the block builds without
      error, not that a graph node can invoke the tool.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_build_capability_block_for_graph_agent_returns_tools -q`
    """
    from collections.abc import Mapping as _Mapping

    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityContext,
        CapabilityManifest,
        EmptyModel,
    )
    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.models import (
        AgentTuning,
        GraphAgentDefinition,
        GraphDefinition,
        GraphNodeDefinition,
    )
    from fred_sdk.contracts.runtime import RuntimeServices
    from langchain_core.tools import BaseTool
    from langchain_core.tools import tool as lc_tool
    from pydantic import BaseModel

    class _NoConfig(BaseModel):
        pass

    class _GraphToolCapability(AgentCapability[_NoConfig, _NoConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="graph_tool_cap",
            version="1.0.0",
            name="cap.graph_tool_cap.name",
            description="cap.graph_tool_cap.description",
            icon="Build",
        )
        ConfigModel = _NoConfig

        def tools(
            self, ctx: CapabilityContext[_NoConfig, EmptyModel]
        ) -> list[BaseTool]:
            del ctx

            @lc_tool
            def graph_probe(text: str) -> str:
                """Echo text back."""
                return text

            return [graph_probe]

    class _MinInput(BaseModel):
        message: str = ""

    class _MinState(BaseModel):
        message: str = ""

    class _MinGraphAgent(GraphAgentDefinition):
        agent_id: str = "test.graph_capability"
        role: str = "test"
        description: str = "test"

        def build_graph(self) -> GraphDefinition:
            return GraphDefinition(
                state_model_name="MinState",
                entry_node="n",
                nodes=(GraphNodeDefinition(node_id="n", title="N"),),
            )

        def input_model(self) -> type[BaseModel]:
            return _MinInput

        def state_model(self) -> type[BaseModel]:
            return _MinState

        def output_model(self) -> type[BaseModel]:
            return _MinInput

        def build_initial_state(
            self, input_model: BaseModel, binding: BoundRuntimeContext
        ) -> BaseModel:
            return _MinState(message=getattr(input_model, "message", ""))

        def node_handlers(self) -> _Mapping[str, object]:
            return {}

        def build_output(self, state: BaseModel) -> BaseModel:
            return _MinInput(message=getattr(state, "message", ""))

    definition = _MinGraphAgent()
    registry = CapabilityRegistry()
    registry.register(_GraphToolCapability())
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["graph_tool_cap"],
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
    assert [t.name for t in block.tools] == ["graph_probe"]


def test_build_capability_block_rejects_react_only_capability_for_graph_agent() -> None:
    """
    A capability declaring `execution_models=("react",)` (a `middleware()`-only
    hook `tools()` can't express) must fail LOUDLY when a Graph agent selects
    it — never silently build with zero tools (CAPAB-02, RFC §3.9 "never
    silently degrade"). Companion to
    `test_build_capability_block_for_graph_agent_returns_tools` above, which
    proves the graph-capable ("react", "graph") case still works.

    Example:
    - `pytest tests/test_agent_app.py::test_build_capability_block_rejects_react_only_capability_for_graph_agent -q`
    """
    from collections.abc import Mapping as _Mapping

    from fred_runtime.app.agent_app import CapabilityError, _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityContext,
        CapabilityManifest,
        EmptyModel,
    )
    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.models import (
        AgentTuning,
        GraphAgentDefinition,
        GraphDefinition,
        GraphNodeDefinition,
    )
    from fred_sdk.contracts.runtime import RuntimeServices
    from langchain.agents.middleware import AgentMiddleware
    from pydantic import BaseModel

    class _NoConfig(BaseModel):
        pass

    class _ReactOnlyCapability(AgentCapability[_NoConfig, _NoConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="react_only_cap",
            version="1.0.0",
            name="cap.react_only_cap.name",
            description="cap.react_only_cap.description",
            icon="Build",
            execution_models=("react",),
        )
        ConfigModel = _NoConfig

        def middleware(
            self, ctx: CapabilityContext[_NoConfig, EmptyModel]
        ) -> list[AgentMiddleware]:
            del ctx
            return []

    class _MinInput(BaseModel):
        message: str = ""

    class _MinState(BaseModel):
        message: str = ""

    class _MinGraphAgent(GraphAgentDefinition):
        agent_id: str = "test.graph_capability_react_only"
        role: str = "test"
        description: str = "test"

        def build_graph(self) -> GraphDefinition:
            return GraphDefinition(
                state_model_name="MinState",
                entry_node="n",
                nodes=(GraphNodeDefinition(node_id="n", title="N"),),
            )

        def input_model(self) -> type[BaseModel]:
            return _MinInput

        def state_model(self) -> type[BaseModel]:
            return _MinState

        def output_model(self) -> type[BaseModel]:
            return _MinInput

        def build_initial_state(
            self, input_model: BaseModel, binding: BoundRuntimeContext
        ) -> BaseModel:
            return _MinState(message=getattr(input_model, "message", ""))

        def node_handlers(self) -> _Mapping[str, object]:
            return {}

        def build_output(self, state: BaseModel) -> BaseModel:
            return _MinInput(message=getattr(state, "message", ""))

    definition = _MinGraphAgent()
    registry = CapabilityRegistry()
    registry.register(_ReactOnlyCapability())
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["react_only_cap"],
    )

    with pytest.raises(CapabilityError, match="react_only_cap"):
        _build_capability_block(
            registry,
            tuning,
            definition=definition,
            services=RuntimeServices(),
            user_id=None,
            session_id=None,
            team_id=None,
            agent_instance_id=None,
        )


def test_build_capability_block_rejects_hitl_gated_capability_for_graph_agent() -> None:
    """
    CAPAB-02 stopgap: `GraphRuntime` never consults `CapabilityAgentBlock.hitl`
    (`invoke_runtime_tool` calls the tool directly) — a capability declaring a
    `HitlSpec` approval gate would silently run ungated on a Graph agent. Full
    Graph HITL enforcement is deferred (see AGENT-CAPABILITY-RFC.md §3.9);
    until then, selecting such a capability on a Graph agent must fail loudly,
    not run unapproved.

    Example:
    - `pytest tests/test_agent_app.py::test_build_capability_block_rejects_hitl_gated_capability_for_graph_agent -q`
    """
    from collections.abc import Mapping as _Mapping

    from fred_runtime.app.agent_app import CapabilityError, _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityContext,
        CapabilityManifest,
        EmptyModel,
        HitlSpec,
    )
    from fred_sdk.contracts.context import BoundRuntimeContext
    from fred_sdk.contracts.models import (
        AgentTuning,
        GraphAgentDefinition,
        GraphDefinition,
        GraphNodeDefinition,
    )
    from fred_sdk.contracts.runtime import RuntimeServices
    from langchain_core.tools import BaseTool
    from langchain_core.tools import tool as lc_tool
    from pydantic import BaseModel

    class _NoConfig(BaseModel):
        pass

    class _HitlGatedCapability(AgentCapability[_NoConfig, _NoConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="hitl_gated_cap",
            version="1.0.0",
            name="cap.hitl_gated_cap.name",
            description="cap.hitl_gated_cap.description",
            icon="Build",
        )
        ConfigModel = _NoConfig

        def tools(
            self, ctx: CapabilityContext[_NoConfig, EmptyModel]
        ) -> list[BaseTool]:
            del ctx

            @lc_tool
            def gated_probe(text: str) -> str:
                """Echo text back."""
                return text

            return [gated_probe]

        def hitl_specs(self) -> list[HitlSpec]:
            return [HitlSpec(tool="gated_probe", require=True)]

    class _MinInput(BaseModel):
        message: str = ""

    class _MinState(BaseModel):
        message: str = ""

    class _MinGraphAgent(GraphAgentDefinition):
        agent_id: str = "test.graph_capability_hitl_gated"
        role: str = "test"
        description: str = "test"

        def build_graph(self) -> GraphDefinition:
            return GraphDefinition(
                state_model_name="MinState",
                entry_node="n",
                nodes=(GraphNodeDefinition(node_id="n", title="N"),),
            )

        def input_model(self) -> type[BaseModel]:
            return _MinInput

        def state_model(self) -> type[BaseModel]:
            return _MinState

        def output_model(self) -> type[BaseModel]:
            return _MinInput

        def build_initial_state(
            self, input_model: BaseModel, binding: BoundRuntimeContext
        ) -> BaseModel:
            return _MinState(message=getattr(input_model, "message", ""))

        def node_handlers(self) -> _Mapping[str, object]:
            return {}

        def build_output(self, state: BaseModel) -> BaseModel:
            return _MinInput(message=getattr(state, "message", ""))

    definition = _MinGraphAgent()
    registry = CapabilityRegistry()
    registry.register(_HitlGatedCapability())
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["hitl_gated_cap"],
    )

    with pytest.raises(CapabilityError, match="hitl_gated_cap"):
        _build_capability_block(
            registry,
            tuning,
            definition=definition,
            services=RuntimeServices(),
            user_id=None,
            session_id=None,
            team_id=None,
            agent_instance_id=None,
        )


def test_capability_block_gives_each_mcp_instructions_middleware_a_unique_name() -> (
    None
):
    """
    Ensure two selected MCP servers with `agent_instructions` yield middleware
    with DISTINCT `.name`s.

    Why this exists:
    - `create_agent` rejects a middleware list with duplicate `.name`s
      ("Please remove duplicate middleware instances."). `AgentMiddleware.name`
      defaults to the class name, so before the per-server `.name` override two
      `_McpInstructionsMiddleware` instances collided and blew up executor
      build for any agent selecting >1 MCP server with `agent_instructions`.
    - guards the fix: `.name` keys on the catalog server id.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_gives_each_mcp_instructions_middleware_a_unique_name -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
    from fred_runtime.capabilities.mcp import _McpInstructionsMiddleware
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
                {
                    "id": "mcp-storage",
                    "name": "Storage",
                    "agent_instructions": "Prefer the newest object version.",
                }
            ),
        ],
    )
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["mcp-search", "mcp-storage"],
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
    names = [
        mw.name for mw in block.middleware if isinstance(mw, _McpInstructionsMiddleware)
    ]
    assert names == ["McpInstructions[mcp-search]", "McpInstructions[mcp-storage]"]
    # The invariant create_agent enforces: no duplicate middleware names.
    assert len(set(names)) == len(names)


def test_build_mcp_capability_id_and_team_scope_come_from_the_catalog_server() -> None:
    """
    Ensure `build_mcp_capability` sets the manifest id to the plain catalog
    server id and forwards the server's `team_scope` verbatim.

    Why this exists:
    - #1988 removed the `mcp:` capability id prefix — the capability id IS
      `server.id`, unprefixed, so it survives `CAPABILITY_ID_PATTERN` (which
      rejects `:`) and can be written straight into OpenFGA tuples
    - `team_scope` must flow from the catalog entry, not default silently:
      an `admin_gated` server must stay admin-gated once registered as a
      capability, and a `default_on` server must stay default-on

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_build_mcp_capability_id_and_team_scope_come_from_the_catalog_server -q`
    """
    from fred_runtime.capabilities.mcp import build_mcp_capability
    from fred_sdk.contracts.capability import TeamScopePolicy
    from fred_sdk.contracts.models import MCPServerConfiguration

    admin_gated_server = MCPServerConfiguration.model_validate(
        {"id": "mcp-search", "name": "Search"}
    )
    default_on_server = MCPServerConfiguration.model_validate(
        {"id": "mcp-storage", "name": "Storage", "team_scope": "default_on"}
    )

    admin_gated_capability = build_mcp_capability(admin_gated_server)
    default_on_capability = build_mcp_capability(default_on_server)

    assert admin_gated_capability.manifest.id == "mcp-search"
    assert admin_gated_capability.manifest.team_scope is TeamScopePolicy.ADMIN_GATED
    assert default_on_capability.manifest.id == "mcp-storage"
    assert default_on_capability.manifest.team_scope is TeamScopePolicy.DEFAULT_ON


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


_ALICE = KeycloakUser(uid="alice", username="alice", roles=[], email=None)


@pytest.mark.asyncio
async def test_authorize_allows_when_user_holds_team_relation(
    monkeypatch, minimal_config
) -> None:
    """An enabled engine that grants CAN_USE_TEAM_AGENTS lets the request proceed."""
    engine = _FakeRebacEngine(enabled=True, deny=False)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(), _ALICE, container
    )

    assert engine.calls == [("alice", TeamPermission.CAN_USE_TEAM_AGENTS, "fredlab")]
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


_BOB = KeycloakUser(uid="bob", username="bob", roles=[], email=None)


@pytest.mark.asyncio
async def test_authorize_allows_personal_space_owner_via_rebac_check(
    monkeypatch, minimal_config
) -> None:
    """A human caller acting on their own canonical personal_team_id is authorized
    through the plain `CAN_USE_TEAM_AGENTS` team check — no special-casing here
    (AUTHZ-08, supersedes AUTHZ-05 item 8b). In the real system this succeeds
    because `RebacEngine.check_user_team_permission_or_raise` self-heals the
    owner's own `team_editor` tuple on first touch (which implies `team_member`,
    which `CAN_USE_TEAM_AGENTS` requires); this test only proves agent_app.py no
    longer short-circuits before the check, i.e. the engine IS consulted."""
    engine = _FakeRebacEngine(enabled=True, deny=False)  # models the self-healed tuple
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    await agent_app_module._authorize_execution_or_raise(
        _managed_request(team_id=personal_team_id(_ALICE.uid)), _ALICE, container
    )

    assert engine.calls == [
        ("alice", TeamPermission.CAN_USE_TEAM_AGENTS, personal_team_id(_ALICE.uid))
    ]
    with container._audit_events_lock:
        events = list(container.audit_events_buffer)
    assert events[-1]["audit_event"] == "rebac_authorized"
    assert events[-1].get("team_id") == personal_team_id(_ALICE.uid)


@pytest.mark.asyncio
async def test_authorize_denies_other_users_personal_space_via_rebac_check(
    monkeypatch, minimal_config
) -> None:
    """Alice requesting Bob's personal space is denied — via the plain
    `CAN_USE_TEAM_AGENTS` team check, not a local identity guard. In the real
    system no tuple is ever provisioned for Alice on Bob's space (self-heal
    only ever grants the space's own owner), and `RebacEngine.add_relation`'s
    write-guard refuses any other
    shape naming a personal team (AUTHZ-08) — that invariant is proven in
    fred-core's own test suite, not here. This test only proves agent_app.py
    defers to the check rather than special-casing the outcome."""
    engine = _FakeRebacEngine(enabled=True, deny=True)  # models "no tuple exists"
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(
            _managed_request(team_id=personal_team_id(_BOB.uid)), _ALICE, container
        )

    assert exc.value.status_code == 403
    assert engine.calls == [
        ("alice", TeamPermission.CAN_USE_TEAM_AGENTS, personal_team_id(_BOB.uid))
    ]
    with container._audit_events_lock:
        events = list(container.audit_events_buffer)
    assert events[-1]["audit_event"] == "rebac_denied"
    assert events[-1].get("user_id") == "alice"


@pytest.mark.asyncio
async def test_authorize_denies_bare_personal_alias(
    monkeypatch, minimal_config
) -> None:
    """The bare "personal" alias is not `is_personal_team_id`-shaped, so it is
    just an ordinary (always-tupleless) team id post-AUTHZ-08 — denied by the
    plain check like any other unknown team, not by a dedicated alias guard."""
    engine = _FakeRebacEngine(enabled=True, deny=True)
    _wire_engine(monkeypatch, engine)
    container = PodApplicationContext(minimal_config)

    with pytest.raises(agent_app_module.HTTPException) as exc:
        await agent_app_module._authorize_execution_or_raise(
            _managed_request(team_id="personal"), _ALICE, container
        )

    assert exc.value.status_code == 403
    assert engine.calls == [("alice", TeamPermission.CAN_USE_TEAM_AGENTS, "personal")]


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
    """RebacEngine stand-in exposing has_user_permission for the C1 admin branch,
    plus check_user_permission_or_raise for the /kpi-turns and /audit-events
    ring-buffer endpoints' CAN_MANAGE_PLATFORM gate."""

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

    async def check_user_permission_or_raise(
        self, user: KeycloakUser, permission: object, resource_id: str, **_kw: object
    ) -> None:
        self.calls.append((user.uid, permission, resource_id))
        if not self._grant:
            raise AuthorizationError(user.uid, str(permission), Resource.RESOURCES)


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


def _get_kpi_turns_endpoint():
    """Grab the `/kpi-turns` route's raw endpoint function, bypassing FastAPI's
    dependency-injection layer so it can be called directly with explicit args."""
    router = agent_app_module._build_agent_router(registry={}, security_enabled=True)
    return next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.endpoint.__name__ == "get_kpi_turns"
    )


@pytest.mark.asyncio
async def test_get_kpi_turns_requires_can_manage_platform_when_enforcing(
    monkeypatch, minimal_config
) -> None:
    """AUTHZ-05 review finding: item 8a's blanket removal of the org-level
    CAN_READ_METRICS check does not apply to this ring buffer — it exposes
    cross-user/cross-team session_id/user_id/team_id/token data for every
    caller that has hit this pod, unlike the tier-2 capabilities item 8a
    correctly deleted elsewhere. Gated on CAN_MANAGE_PLATFORM, same as the
    sibling `get_audit_events`, when ReBAC is actually enforcing."""
    endpoint = _get_kpi_turns_endpoint()
    container = PodApplicationContext(minimal_config)

    denying_engine = _FakePlatformRebacEngine(enabled=True, grant=False)
    _wire_engine(monkeypatch, denying_engine)
    with pytest.raises(AuthorizationError):
        await endpoint(limit=10, container=container, caller=_ALICE)
    assert denying_engine.calls == [
        ("alice", OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
    ]

    granting_engine = _FakePlatformRebacEngine(enabled=True, grant=True)
    _wire_engine(monkeypatch, granting_engine)
    assert await endpoint(limit=10, container=container, caller=_ALICE) == []


@pytest.mark.asyncio
async def test_get_kpi_turns_unchanged_in_dev_mode(monkeypatch, minimal_config) -> None:
    """Dev/no-security mode (no caller, or ReBAC disabled) stays exactly as
    before this fix: the diagnostic buffer remains reachable without a grant."""
    endpoint = _get_kpi_turns_endpoint()
    container = PodApplicationContext(minimal_config)

    _wire_engine(monkeypatch, None)
    assert await endpoint(limit=10, container=container, caller=None) == []

    disabled_engine = _FakePlatformRebacEngine(enabled=False, grant=False)
    _wire_engine(monkeypatch, disabled_engine)
    assert await endpoint(limit=10, container=container, caller=_ALICE) == []
    assert disabled_engine.calls == []  # a disabled engine is never consulted


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
    container._kpi_writer = NoOpKPIWriter()
    container.initialize_control_plane_client()

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


@pytest.mark.asyncio
async def test_authorize_and_resolve_times_pod_authz_and_runtime_binding_phases(
    monkeypatch, minimal_config
) -> None:
    """
    TURN-01 instrumentation: `_authorize_and_resolve` must time pod-side
    OpenFGA authorization and instance resolution as two distinct
    `runtime.stage_latency_ms` stages (pod_authz, runtime_binding), both
    before `_stream()`'s own `turn_start` — additive only,
    `agent.turn_completed`'s total_ms is untouched. This is the dedicated,
    Prometheus-labelled `runtime_stage` mechanism (isolated from the generic,
    unlabelled `app.phase_latency_ms`/`phase` used by Graph/checkpoint/KF).

    The runtime_binding stage must also carry a `trace.trace_id`, and that
    same id must reach `_resolve_agent_instance` as `request_id` (the value
    later sent as `X-Request-Id` to control-plane, TURN-01 correlation).
    """
    emitted: list[dict] = []

    class _RecordingKPIWriter(NoOpKPIWriter):
        def emit(self, **kwargs) -> None:
            emitted.append(kwargs)

    async def _noop(*args, **kwargs):
        return None

    resolve_calls: list[dict] = []
    target = SimpleNamespace(
        team_id="fredlab", definition=None, agent_instance_name=None
    )

    async def _fake_resolve(**kwargs):
        resolve_calls.append(kwargs)
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
            "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
        }
    )
    container = PodApplicationContext(minimal_config)
    container._kpi_writer = _RecordingKPIWriter()
    container.initialize_control_plane_client()

    await agent_app_module._authorize_and_resolve(
        request,
        authenticated_user=_ALICE,
        container=container,
        registry={},
        access_token="header-jwt",
    )

    phases = {
        e["dims"]["runtime_stage"]: e
        for e in emitted
        if e["name"] == "runtime.stage_latency_ms"
    }
    assert set(phases) == {"pod_authz", "runtime_binding"}
    assert phases["pod_authz"].get("trace") is None

    binding_event = phases["runtime_binding"]
    assert binding_event["trace"] is not None
    trace_id = binding_event["trace"]["trace_id"]
    assert trace_id

    assert len(resolve_calls) == 1
    assert resolve_calls[0]["request_id"] == trace_id
