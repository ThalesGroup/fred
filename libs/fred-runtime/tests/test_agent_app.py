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
import logging
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import fred_core.security.oidc as oidc_module
import httpx
import pytest
from conftest import (
    StaticChatModelFactory,
    StaticWorkloadTokens,
    ToolFriendlyFakeChatModel,
    install_delegation_runtime,
    migrate_test_config,
)
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fred_core.common.config_loader import get_config
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore
from fred_core.security.delegation import (
    get_delegation_config,
    initialize_delegation,
)
from fred_core.security.structure import KeycloakUser
from fred_core.users.store import postgres_user_store
from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import context as context_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import get_pod_container_from_app
from fred_runtime.common.outbound_credentials import set_delegation_runtime
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.runtime_context import RuntimeConfig, get_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.checkpoints import checkpoint_config
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    BoundRuntimeContext,
    InvocationScope,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.execution import (
    RuntimeExecuteRequest,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import (
    ConversationScratchpadFileNotFoundError,
    HistoryStorePort,
)
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import empty_checkpoint
from pydantic import ValidationError
from weaver_fixtures import (
    INSTANCE_ID,
    SPACE_ID,
    active_turn,
    conversation_provenance,
    create_managed_app,
    invocation_context,
    managed_payload,
)

pytestmark = pytest.mark.usefixtures("offline_pod_infrastructure")


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


@tool("demo.team_routing", description="Return the requested Weaver selection.")
async def _demo_team_routing(ctx: ToolContext) -> str:
    rc = ctx.binding.runtime_context
    return f"space:{rc.space_id}|choice:{rc.model_choice}"


@tool("demo.reasoning", description="Return the bound reasoning activation snapshot.")
async def _demo_reasoning(ctx: ToolContext) -> str:
    """Return the per-turn reasoning choice and any retired model-id ceiling."""

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
    max_chat_input_chars: int = 5_000,
    user_security_enabled: bool = False,
    act_for_people: bool = False,
    accept_delegated_calls: bool = False,
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
                "runtime_id": "test-pod",
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                # OpenAI-compat is opt-in (off by default, RUNTIME-07 F-A); the
                # broad app test below asserts the /v1 surface, so enable it here.
                "openai_compat": True,
                "max_chat_input_chars": max_chat_input_chars,
            },
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-m2m",
                },
                "user": {
                    "enabled": user_security_enabled,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-user",
                },
                "authorized_origins": [],
                "delegation": {
                    "act_for_people": act_for_people,
                    "accept_delegated_calls": accept_delegated_calls,
                },
            },
            "ai": {
                "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v2",
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
                },
                "object_store": {
                    "type": "local",
                    "root": str(tmp_path / "filesystem"),
                },
            },
            "platform": {
                "control_plane_url": control_plane_url,
            },
        }
    )
    # The pod refuses to start against an unmigrated database (#2290) —
    # create the Alembic-owned schema first, as the deploy migration job does.
    return migrate_test_config(config)


def test_lifespan_identifies_this_pod_by_slug_in_logs_and_runtime_config(
    monkeypatch, tmp_path
) -> None:
    """Both telemetry streams must name the pod by `app.runtime_id`.

    `app.name` is a display string ("Test Pod"): sourcing an identifier from
    it puts spaces and capitals in a Prometheus label, and makes the log
    stream's `service` disagree with the KPI one so the two cannot be joined.
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    log_setup_calls: list[str] = []
    real_log_setup = agent_app_module.log_setup

    def _record_log_setup(*, service_name: str, **kwargs):
        log_setup_calls.append(service_name)
        return real_log_setup(service_name=service_name, **kwargs)

    monkeypatch.setattr(agent_app_module, "log_setup", _record_log_setup)

    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app):
        assert get_runtime_context().config.service_name == "test-pod"

    assert log_setup_calls == ["test-pod"]


@pytest.fixture
def _pod_inbound_security() -> Iterator[None]:
    """Keycloak validation and grant acceptance are process-wide in the shared
    library; restore both so a later test sees the offline defaults."""
    keycloak_enabled = oidc_module.KEYCLOAK_ENABLED
    acceptance = get_delegation_config()
    yield
    oidc_module.KEYCLOAK_ENABLED = keycloak_enabled
    initialize_delegation(acceptance)
    set_delegation_runtime(None)


_ACCESS_KIND = "Bearer"


def _secured_pod(
    monkeypatch,
    tmp_path,
    *,
    caller_client_id: str,
    requires_active_accounts: bool = True,
    account_status_model_error: Exception | None = None,
    accept_delegated_calls: bool = True,
    **token: object,
):
    """A pod whose door is the shared user dependency, with the token decoded
    locally and grant acceptance switched on the way a receiver has it.

    `accept_delegated_calls` off leaves a pod that only acts for people.
    `token` overrides what the decoded workload token carries."""
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        lambda bearer: KeycloakUser(
            uid="workload-caller",
            username="workload-caller",
            roles=["service_agent"],
            client_id=caller_client_id,
        ).model_copy(update=token),
    )
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(
            tmp_path,
            user_security_enabled=True,
            act_for_people=True,
            accept_delegated_calls=accept_delegated_calls,
        ),
    )
    # Installed after construction, so a run that reached admission would leave
    # a record to find.
    delegation = install_delegation_runtime(StaticWorkloadTokens())
    return app, delegation


def test_a_role_holder_whose_token_is_not_addressed_to_delegation_is_refused(
    monkeypatch, tmp_path, _pod_inbound_security
) -> None:
    """The role alone cannot authorize delegation: the token must be addressed to it."""
    app, delegation = _secured_pod(
        monkeypatch,
        tmp_path,
        caller_client_id="caller-1",
        token_issuer="http://localhost:8080/realms/fred",
        token_audiences=frozenset({"another-receiver"}),
        token_type=_ACCESS_KIND,
        caller_roles=frozenset({"delegation_caller"}),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            params={"person": "alice", "run": "run-1", "agent": "rags.sample.echo"},
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-asserted",
            },
            headers={"Authorization": "Bearer workload-bearer"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "delegation_not_allowed"
    assert len(delegation.records) == 0


def test_a_service_bearer_without_a_person_is_refused_under_delegation(
    monkeypatch, tmp_path, _pod_inbound_security
) -> None:
    """A service bearer alone cannot acquire Weaver execution authority."""
    app, delegation = _secured_pod(
        monkeypatch, tmp_path, caller_client_id="caller-1", accept_delegated_calls=False
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-service-caller",
                "runtime_context": {"team_id": "team-1"},
            },
            headers={"Authorization": "Bearer workload-bearer"},
        )
        admitted = [
            dict(event)
            for event in get_pod_container_from_app(app).audit_events_buffer
            if event["audit_event"] == "delegated_run_admitted"
        ]

    assert response.status_code == 403
    assert admitted == []
    assert len(delegation.records) == 0


@pytest.mark.parametrize(
    "accept_delegated_calls", [False, True], ids=["acting-only", "also-accepting"]
)
def test_a_role_holder_without_a_person_cannot_execute_under_delegation(
    monkeypatch, tmp_path, _pod_inbound_security, accept_delegated_calls: bool
) -> None:
    """The delegation role names no one: without a grant it is refused, not run as itself."""
    app, _ = _secured_pod(
        monkeypatch,
        tmp_path,
        caller_client_id="caller-1",
        accept_delegated_calls=accept_delegated_calls,
        roles=[],
        caller_roles=frozenset({"delegation_caller"}),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": "rags.sample.echo",
                "input": "hello",
                "session_id": "session-role-holder",
            },
            headers={"Authorization": "Bearer workload-bearer"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "delegated_person_required"


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


def test_lifespan_shutdown_releases_every_resource_even_when_a_step_raises(
    monkeypatch, tmp_path, caplog
) -> None:
    """A raising shutdown step must not strand the resources released after it.

    Shutdown used to be a bare sequence after `yield`. Two ways that lost the
    Keycloak refresh pool — a 32-connection httpx client — with nothing logged:
    an exception propagating out of the app skipped the whole sequence, and a
    `container.shutdown()` failure (a hung KPI task, a broken SQL dispose)
    skipped everything behind it. The pod is terminating either way; leaking a
    pool because an unrelated subsystem failed is the strictly worse outcome.
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    async def _raising_shutdown(self) -> None:
        raise RuntimeError("kpi task refused to cancel")

    monkeypatch.setattr(PodApplicationContext, "shutdown", _raising_shutdown)

    closed: list[str] = []

    async def _record_close() -> None:
        closed.append("keycloak")

    monkeypatch.setattr(agent_app_module, "aclose_token_refresh_client", _record_close)

    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )

    # Not `caplog`: the lifespan's own `log_setup()` re-wires logging during
    # startup and detaches pytest's capture handler, so records emitted at
    # SHUTDOWN never reach `caplog.records`. Attaching to the module logger
    # after startup is what actually observes them.
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    module_logger = logging.getLogger(agent_app_module.__name__)
    with TestClient(app):
        module_logger.addHandler(handler)
    module_logger.removeHandler(handler)

    # The step AFTER the failing one still ran...
    assert closed == ["keycloak"]
    # ...and the failure was reported rather than silently absorbed, naming
    # which step it was so a shutdown hang is diagnosable from pod logs alone.
    assert [
        r.levelname for r in records if "shutdown step failed" in r.getMessage()
    ] == ["ERROR"]
    assert "pod container" in records[0].getMessage()
    assert records[0].exc_info is not None


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
    app = create_managed_app(
        monkeypatch,
        registry=registry,
        config=_build_test_config(tmp_path, max_chat_input_chars=37),
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
        assert templates_response.json()[0]["max_chat_input_chars"] == 37

        configured_limit_response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload({"agent_id": "unknown", "input": "x" * 38}),
        )
        assert configured_limit_response.status_code == 422
        assert configured_limit_response.json()["detail"]["limit_chars"] == 37

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
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-execute",
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )
        assert execute_response.status_code == 200
        assert execute_response.json()["kind"] == "final"
        assert execute_response.json()["content"] == "Echo complete."

        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-stream",
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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


@pytest.mark.parametrize(
    "text_factory",
    [
        pytest.param(lambda size: "a" * size, id="ascii"),
        pytest.param(lambda size: "界" * size, id="cjk"),
        pytest.param(lambda size: "🙂" * size, id="emoji"),
    ],
)
def test_native_execution_routes_enforce_chat_input_limit_before_runtime_work(
    monkeypatch, tmp_path, text_factory
) -> None:
    """All native entry points share the 4,999/5,000/5,001 boundary."""

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    limit = 5_000
    app = create_agent_app(registry={}, config=_build_test_config(tmp_path))
    routes = (
        "/pod/v1/agents/execute",
        "/pod/v1/agents/execute/stream",
        "/pod/v1/agents/evaluate",
    )

    with TestClient(app) as client:
        for route in routes:
            for size in (limit - 1, limit):
                response = client.post(
                    route,
                    json={"agent_id": "unknown", "input": text_factory(size)},
                )
                assert response.status_code == 403

        exchange_lookup = AsyncMock()
        target_resolution = AsyncMock()
        history_write = AsyncMock()
        stream_construction = MagicMock()
        event_iteration = MagicMock()
        monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", exchange_lookup)
        monkeypatch.setattr(
            agent_app_module, "_authorize_and_resolve", target_resolution
        )
        monkeypatch.setattr(agent_app_module, "_write_turn_history", history_write)
        monkeypatch.setattr(agent_app_module, "_stream", stream_construction)
        monkeypatch.setattr(
            agent_app_module, "_iterate_runtime_event_payloads", event_iteration
        )

        rejected_text = text_factory(limit + 1)
        for route in routes:
            response = client.post(
                route,
                json={"agent_id": "unknown", "input": rejected_text},
            )
            assert response.status_code == 422
            assert response.json() == {
                "detail": {
                    "code": "chat_input_too_long",
                    "message": "Your message exceeds the 5,000-character limit.",
                    "limit_chars": limit,
                    "actual_chars": limit + 1,
                }
            }
            assert rejected_text not in response.text

        for route in routes:
            response = client.post(
                route,
                json={
                    "agent_id": "unknown",
                    "resume_payload": {
                        "choice_id": text_factory(2_000),
                        "answer": text_factory(2_000),
                        "text": text_factory(1_001),
                        "ignored": text_factory(limit + 1),
                    },
                },
            )
            assert response.status_code == 422
            assert response.json()["detail"]["actual_chars"] == limit + 1

    exchange_lookup.assert_not_awaited()
    target_resolution.assert_not_awaited()
    history_write.assert_not_awaited()
    stream_construction.assert_not_called()
    event_iteration.assert_not_called()


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
    monkeypatch.setattr(
        agent_app_module, "_caller_can_manage_platform", AsyncMock(return_value=False)
    )

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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        execute_response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-checkpoint-delete",
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
        assert threads_after.status_code == 404

        # Idempotent: a retry against an already-purged thread deletes nothing.
        retry_response = client.delete(
            "/pod/v1/agents/checkpoints/session-checkpoint-delete"
        )
        assert retry_response.status_code == 200
        assert retry_response.json() == {"deleted": 0}


def test_a_session_id_naming_a_graph_thread_is_refused_everywhere(
    monkeypatch, tmp_path
) -> None:
    """
    Graph threads are named "{session_id}:{agent}". A caller choosing the
    session id "S:N" must not reach session S's graph thread for agent N,
    whether by running a turn, reading or purging checkpoints, or through
    the OpenAI-compatible surface.
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="Hello.")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    stolen = "session-a:inst-1"

    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        execute = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": definition.agent_id,
                    "input": "hello",
                    "session_id": stolen,
                    "runtime_context": {"user_id": "bob"},
                }
            ),
        )
        assert execute.status_code == 422, execute.text
        checkpoints = client.get(f"/pod/v1/agents/checkpoints/{stolen}")
        assert checkpoints.status_code == 404
        deletion = client.delete(f"/pod/v1/agents/checkpoints/{stolen}")
        assert deletion.status_code == 422
        openai = client.post(
            "/v1/chat/completions",
            json={
                "model": definition.agent_id,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"X-Fred-Session-Id": stolen},
        )
        assert openai.status_code == 503, openai.text
        assert "not connected to Weaver" in openai.json()["detail"]


def test_a_turn_listing_more_prompt_commands_than_the_limit_is_refused(
    monkeypatch, tmp_path
) -> None:
    """The execute endpoint answers 422 and the model is never called."""

    from fred_sdk.contracts.context import MAX_TURN_PROMPTS

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="Hello.")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    def command(count: int) -> dict[str, object]:
        return {
            "command": "cmd0",
            "draft_text": " ".join(f"/cmd{index}" for index in range(count)),
            "draft_command_offset": 0,
            "prompts": [
                {
                    "command": f"cmd{index}",
                    "prompt_id": f"p-{index}",
                    "draft_offset": index * 6,
                    "text_offset": index * 3,
                    "text_length": 1,
                }
                for index in range(count)
            ],
        }

    def execute(client: TestClient, count: int):
        return client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": definition.agent_id,
                    "input": "\n\n".join("x" for _ in range(count)),
                    "session_id": f"session-prompts-{count}",
                    "runtime_context": {"user_id": "bob", "command": command(count)},
                }
            ),
        )

    with TestClient(app) as client:
        refused = execute(client, MAX_TURN_PROMPTS + 1)
        assert refused.status_code == 422, refused.text
        assert "prompts" in refused.text
        accepted = execute(client, MAX_TURN_PROMPTS)
        assert accepted.status_code == 200, accepted.text


def test_delete_session_filesystem_purges_both_runtime_namespaces(
    monkeypatch, tmp_path
) -> None:
    """The internal session erase endpoint removes both runtime-owned prefixes."""
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    app = create_agent_app(registry={}, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        filesystem = get_runtime_context().config.filesystem
        assert filesystem is not None
        service = ConversationFilesystemService(filesystem, "session-filesystem")
        asyncio.run(service.scratchpad().write_text("notes.md", "scratchpad"))
        asyncio.run(
            service.namespace(
                ".deep", max_bytes=1024 * 1024 * 1024, max_files=10000
            ).write_text("result.md", "deep")
        )

        response = client.delete(
            "/pod/v1/agents/sessions/session-filesystem/filesystem"
        )

        assert response.status_code == 200
        assert response.json() == {"purged": True}
        assert asyncio.run(service.scratchpad().exists("notes.md")) is False
        assert (
            asyncio.run(
                service.namespace(
                    ".deep", max_bytes=1024 * 1024 * 1024, max_files=10000
                ).exists("result.md")
            )
            is False
        )

        retry_response = client.delete(
            "/pod/v1/agents/sessions/session-filesystem/filesystem"
        )
        assert retry_response.status_code == 200
        assert retry_response.json() == {"purged": True}


def test_delete_session_filesystem_rejects_a_different_session_owner(
    monkeypatch, tmp_path
) -> None:
    """A caller cannot erase runtime files for a conversation they do not own."""
    monkeypatch.setattr(
        agent_app_module, "_caller_can_manage_platform", AsyncMock(return_value=False)
    )
    caller = KeycloakUser(uid="alice", username="alice", roles=[], email=None)
    monkeypatch.setattr(
        agent_app_module,
        "_make_user_dependency",
        lambda _fn, _enabled: lambda: caller,
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
    )
    app = create_agent_app(registry={}, config=_build_test_config(tmp_path))
    history_store = AsyncMock()
    history_store.session_belongs_to_user = AsyncMock(return_value=False)

    with TestClient(app) as client:
        current = get_runtime_context().config
        monkeypatch.setattr(
            agent_app_module,
            "get_runtime_context",
            lambda: FredRuntimeContext(
                RuntimeConfig(
                    knowledge_flow_url=current.knowledge_flow_url,
                    filesystem=current.filesystem,
                    history_store=history_store,
                )
            ),
        )
        response = client.delete("/pod/v1/agents/sessions/session-bob/filesystem")

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}
    history_store.session_belongs_to_user.assert_awaited_once_with(
        "session-bob", "alice"
    )


def test_delete_session_filesystem_reports_storage_failures(
    monkeypatch, tmp_path
) -> None:
    """Storage faults stay visible to the lifecycle caller instead of falling back."""

    class _FailingFilesystem:
        async def list(self, prefix: str = "") -> list[object]:
            del prefix
            return []

        async def delete(self, path: str) -> None:
            del path
            raise OSError("object storage unavailable")

    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
    )
    app = create_agent_app(registry={}, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        monkeypatch.setattr(
            agent_app_module,
            "get_runtime_context",
            lambda: FredRuntimeContext(
                RuntimeConfig(
                    knowledge_flow_url="http://localhost:8111/knowledge-flow/v2",
                    filesystem=cast(Any, _FailingFilesystem()),
                )
            ),
        )
        response = client.delete(
            "/pod/v1/agents/sessions/session-filesystem/filesystem"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Conversation filesystem storage is unavailable."
    }


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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(app) as client:
        stream_response = client.post(
            "/pod/v1/agents/execute/stream",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.context_prompt",
                    "input": "hello",
                    "session_id": "session-ctx",
                    "runtime_context": {
                        "user_id": "alice",
                        "context_prompt_text": "CTXMARKER-9f3a",
                    },
                }
            ),
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


def test_execute_forwards_ask_user_to_agent_tool_catalog(monkeypatch, tmp_path) -> None:
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-question-1",
                        "name": "ask_user",
                        "args": {
                            "question": "Choose one",
                            "choices": [
                                {"id": "a", "label": "A"},
                                {"id": "b", "label": "B"},
                            ],
                        },
                    }
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _EchoAgent()
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream",
            json=managed_payload(
                {
                    "agent_id": definition.agent_id,
                    "input": "Ask me",
                    "session_id": "session-question",
                    "runtime_context": {"user_id": "alice", "ask_user": True},
                }
            ),
        )
        assert response.status_code == 200

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        event.get("kind") == "awaiting_human"
        and event.get("request", {}).get("stage") == "agent_question"
        for event in payloads
    )


def test_execute_forwards_canonical_space_and_model_choice(monkeypatch, tmp_path):
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"id": "choice", "name": "demo_team_routing", "args": {}}],
            ),
            AIMessage(content="done"),
        ]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _TeamRoutingAgent()
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream",
            json=managed_payload(
                {
                    "input": "hello",
                    "runtime_context": {
                        "model_choice": {
                            "source_id": "a",
                            "upstream_model_id": "second",
                        }
                    },
                }
            ),
        )
    assert response.status_code == 200
    assert f"space:{SPACE_ID}" in response.text
    assert "second" in response.text


def _run_managed_reasoning_turn(
    monkeypatch,
    tmp_path,
    *,
    legacy_agent_reasoning_enabled: bool | None = None,
    definition_cls: type[_ReasoningAgent] = _ReasoningAgent,
) -> str:
    """Run the reasoning probe with trusted Weaver tuning and a forged legacy ceiling."""

    tuning: dict[str, object] = {
        "role": "Reasoning activation probe",
        "description": "Reports the activation it received.",
        "tags": [],
        "fields": [],
    }
    if legacy_agent_reasoning_enabled is not None:
        tuning["reasoning_enabled"] = legacy_agent_reasoning_enabled

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

    definition = definition_cls()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch,
        tuning=tuning,
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
            json=managed_payload(
                {
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
                }
            ),
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


def test_execute_forwards_reasoning_choice_and_ignores_legacy_model_ids(
    monkeypatch, tmp_path
) -> None:
    """The user reasoning choice survives; legacy model-id ceilings confer no authority."""

    echoed = _run_managed_reasoning_turn(monkeypatch, tmp_path)
    assert "reasoning:none" in echoed
    assert "turn:true" in echoed


def test_legacy_agent_reasoning_switch_no_longer_narrows_the_ceiling(
    monkeypatch, tmp_path
) -> None:
    """A retired tuning switch does not alter the per-turn reasoning choice."""

    echoed = _run_managed_reasoning_turn(
        monkeypatch, tmp_path, legacy_agent_reasoning_enabled=False
    )
    assert "reasoning:none" in echoed
    assert "turn:true" in echoed


class _LegacyReasoningAgent(_ReasoningAgent):
    """A third-party definition still setting the deprecated reasoning fields."""

    reasoning_enabled: bool = True
    reasoning_default_on: bool = True


def test_deprecated_definition_reasoning_fields_load_warn_and_change_nothing(
    monkeypatch, tmp_path
) -> None:
    from fred_sdk.contracts import models as sdk_models

    # The app's logging setup replaces root handlers, so record the call itself.
    warned: list[str] = []
    monkeypatch.setattr(
        sdk_models.logger,
        "warning",
        lambda msg, *args: warned.append(msg % args),
    )
    baseline = _run_managed_reasoning_turn(monkeypatch, tmp_path / "baseline")
    legacy = _run_managed_reasoning_turn(
        monkeypatch, tmp_path / "legacy", definition_cls=_LegacyReasoningAgent
    )
    assert legacy == baseline
    assert agent_app_module._definition_to_agent_tuning(
        _LegacyReasoningAgent()
    ) == agent_app_module._definition_to_agent_tuning(_ReasoningAgent())
    assert len(warned) == 1
    assert "_LegacyReasoningAgent" in warned[0]


def test_managed_execution_uses_trusted_platform_chat_binding_not_forged_request(
    monkeypatch, tmp_path
):
    from fred_runtime.model_routing.turn import current_turn

    observed = []
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])

    class Factory(StaticChatModelFactory):
        def build(self, definition, binding):
            observed.append(current_turn().binding.models.policy.default)
            return super().build(definition, binding)

    monkeypatch.setattr(
        agent_app_module, "_build_chat_model_factory", lambda config: Factory(model)
    )
    definition = _EchoAgent()
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "input": "hello",
                    "runtime_context": {
                        "platform_model_bindings": {
                            "chat": {"provider": "attacker", "name": "forged"}
                        }
                    },
                }
            ),
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "final"
    assert observed and all(
        key.source_id == "a" and key.upstream_model_id == "first" for key in observed
    )


def test_managed_resume_cannot_deserialize_turn_authority() -> None:
    from fred_runtime.app.agent_app import _AgentExecuteRequest

    request = _AgentExecuteRequest.model_validate(
        {"agent_instance_id": "instance", "message": "resume", "_turn_authority": {}}
    )
    assert request._turn_authority is None


def test_managed_execution_never_calls_llm_when_runtime_binding_resolution_fails(
    monkeypatch, tmp_path
) -> None:
    """An unavailable resolver returns 503 before any model construction."""

    factory_build_calls: list[object] = []

    class _CountingChatModelFactory(StaticChatModelFactory):
        def build(self, definition: object, binding: object):
            factory_build_calls.append(definition)
            return super().build(definition, binding)

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="should never run")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: _CountingChatModelFactory(model),
    )

    definition = _TeamRoutingAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch,
        resolver_status=500,
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
            json=managed_payload(
                {
                    "agent_instance_id": "instance-binding-failure",
                    "input": "hello",
                    "session_id": "session-binding-failure",
                    "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
                }
            ),
        )

    # Mapped from the upstream 500 (>=400, not 404/403) — see
    # `_resolve_agent_instance`'s status mapping.
    assert stream_response.status_code == 503
    assert factory_build_calls == []


@pytest.mark.parametrize("route", ["execute", "execute/stream", "evaluate"])
def test_direct_execution_cannot_acquire_authority_with_forged_binding(
    monkeypatch, tmp_path, route
):
    model = ToolFriendlyFakeChatModel(responses=[])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    definition = _EchoAgent()
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/pod/v1/agents/{route}",
            json={
                "agent_id": definition.agent_id,
                "input": "hi",
                "runtime_context": {
                    "platform_model_bindings": {
                        "chat": {"provider": "attacker", "name": "forged"}
                    }
                },
            },
        )
    assert response.status_code == 403
    assert "Direct template" in response.json()["detail"]
    assert app.state.resolver_requests == []


@pytest.mark.parametrize("stream", [False, True])
def test_create_agent_app_executes_managed_agent_instances_via_control_plane(
    monkeypatch, tmp_path, stream
) -> None:
    """Resolve a managed instance through Weaver and bind its canonical team to tools."""

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
    from fred_runtime.runtime_support.turn_steering import TurnSteeringMiddleware

    seen_turn_ids: list[str | None] = []
    original_before_model = TurnSteeringMiddleware.abefore_model

    async def capture_steering_turn(self, state, runtime):
        seen_turn_ids.append(self._turn_id)
        return await original_before_model(self, state, runtime)

    monkeypatch.setattr(TurnSteeringMiddleware, "abefore_model", capture_steering_turn)

    definition = _TeamScopeAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch,
        registry=registry,
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane:8222/control-plane/v1",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream" if stream else "/pod/v1/agents/execute",
            headers={"Authorization": "Bearer test-token"},
            json=managed_payload(
                {
                    "agent_instance_id": "instance-1",
                    "input": "what team am I in?",
                    "session_id": "managed-session",
                    "steering_turn_id": "managed-turn",
                    "runtime_context": {"user_id": "alice", "team_id": "fredlab"},
                }
            ),
        )

    assert response.status_code == 200
    payload = (
        next(
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ") and '"kind": "final"' in line
        )
        if stream
        else response.json()
    )
    assert payload["kind"] == "final"
    assert payload["content"] == "Managed execution complete."
    assert seen_turn_ids == ["managed-turn" if stream else None] * 2


def test_managed_execution_rejects_grant_with_mismatched_team(
    monkeypatch, tmp_path
) -> None:
    """Reject a trusted response whose team disagrees with the admitted request."""

    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="should not be reached")]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _TeamScopeAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch,
        binding_transform=lambda data: data["space"].update(
            team_id="00000000-0000-0000-0000-000000000099"
        ),
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
            json=managed_payload(
                {
                    "agent_instance_id": "instance-1",
                    "input": "what team am I in?",
                    "session_id": "managed-session",
                    "runtime_context": {"user_id": "alice", "team_id": "intruder-team"},
                }
            ),
        )

    assert response.status_code == 403
    assert "binding mismatch" in response.json()["detail"].lower()


def test_create_agent_app_does_not_initialize_swift_user_store(
    monkeypatch, tmp_path
) -> None:
    """Weaver admission reads Rust-owned terms and never initializes Swift users."""
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="startup ready")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(postgres_user_store, "_user_store", None)

    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app):
        assert postgres_user_store._user_store is None


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
    monkeypatch.setattr(agent_app_module, "require_permission", AsyncMock())
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
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        container = get_pod_container_from_app(app)
        container.kpi_turns_buffer.clear()

        resp = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload({"agent_id": "rags.sample.echo", "input": "ping"}),
        )
        assert resp.status_code == 200

        with container._kpi_turns_lock:
            turns = list(container.kpi_turns_buffer)

    assert len(turns) == 1
    assert "ts" in turns[0]
    assert "exchange_id" in turns[0]
    assert turns[0]["is_error"] is False


def test_emit_turn_completed_carries_session_id(monkeypatch, tmp_path) -> None:
    """
    `agent.turn_completed` must carry `dims.session_id` (issue #2426).

    Why this exists:
    - control-plane's `conversation_depth` preset groups turns by
      `dims.session_id`; without the dim the whole preset returns nothing, and
      nothing else in this suite asserts the dim reaches the KPI writer
    - the ring-buffer record sources `session_id` from the same `turn_dims`
      dict, and `KpiTurnRecord` requires that key while the surrounding `cast`
      hides its loss from the type checker — so it needs a runtime assertion

    How to use it:
    - run in the default offline `fred-runtime` test suite
    """
    emitted: list[dict] = []

    class _RecordingKPIWriter(NoOpKPIWriter):
        def emit(self, **kwargs) -> None:
            emitted.append(kwargs)

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
    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=_build_test_config(tmp_path),
    )

    with TestClient(app) as client:
        container = get_pod_container_from_app(app)
        container.kpi_turns_buffer.clear()
        # `_emit_turn_completed` reads the writer off the runtime context, which
        # only exists once the app has started — hence patching inside the
        # TestClient block. `RuntimeConfig` is a frozen dataclass, so the seam
        # is the accessor rather than the field.
        recording = _RecordingKPIWriter()
        monkeypatch.setattr(
            type(get_runtime_context()),
            "get_kpi_writer",
            lambda _self: recording,
        )

        resp = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "ping",
                    "session_id": "session-depth",
                }
            ),
        )
        assert resp.status_code == 200

        with container._kpi_turns_lock:
            turns = list(container.kpi_turns_buffer)

    turn_completed = [e for e in emitted if e.get("name") == "agent.turn_completed"]
    assert len(turn_completed) == 1
    assert turn_completed[0]["dims"]["session_id"] == "session-depth"
    # Deliberately NOT carried — see RUNTIME-EXECUTION-CONTRACT.md §8.58.
    assert "exchange_id" not in turn_completed[0]["dims"]
    assert "user_id" not in turn_completed[0]["dims"]

    assert len(turns) == 1
    assert turns[0]["session_id"] == "session-depth"


def test_execute_route_propagates_observability_context(monkeypatch, tmp_path) -> None:
    """
    Ensure the pod bridges observability fields into internal execution.

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
        seen["context"] = dict(request.context or {})
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )

    async def _fake_load_checkpoint(checkpointer, *, thread_id, checkpoint_ns=""):
        _ = (checkpointer, thread_id, checkpoint_ns)
        return {"id": "cp-1", "channel_values": {}}, []

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-1",
                    "runtime_context": {
                        "user_id": "alice",
                        "team_id": "fredlab",
                        "trace_id": "trace-1",
                        "correlation_id": "corr-1",
                    },
                }
            ),
        )

    assert response.status_code == 200
    assert seen["context"] == {
        "session_id": "session-1",
        "user_id": "alice",
        "team_id": SPACE_ID,
        "space_id": SPACE_ID,
        "agent_instance_id": INSTANCE_ID,
        "template_agent_id": "rags.sample.echo",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "execution_action": "execute",
    }


@pytest.mark.asyncio
async def test_local_registry_invoker_reuses_runtime_execute_projection(
    monkeypatch,
) -> None:
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

    with active_turn("rags.sample.echo", session="session-1"):
        result = await invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=invocation_context(
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

    assert result.content == "ok"
    assert result.is_error is False
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
    assert context["space_id"] == SPACE_ID
    assert context["agent_instance_id"] == INSTANCE_ID
    assert context["execution_action"] == "execute"


@pytest.mark.asyncio
async def test_local_registry_child_never_receives_the_user_chat_choice(
    monkeypatch,
) -> None:
    """A registry child gets only the parent's PortableContext: no user choice,
    no instance tuning (so no recommendation) and no team-disabled set, so it
    keeps its own model resolution."""

    seen: dict[str, object] = {}

    async def _fake_iterate_runtime_event_payloads(
        definition, request, access_token=None, **kwargs
    ):
        seen["context"] = dict(request.context or {})
        seen["kwargs"] = kwargs
        yield {"kind": "final", "sequence": 0, "content": "ok"}

    monkeypatch.setattr(
        agent_app_module,
        "_iterate_runtime_event_payloads",
        _fake_iterate_runtime_event_payloads,
    )

    definition = _EchoAgent()
    invoker = agent_app_module.LocalRegistryAgentInvoker(
        registry={definition.agent_id: definition}, access_token=None
    )
    with active_turn("rags.sample.echo", session=None):
        await invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=invocation_context(
                    request_id="req-1",
                    correlation_id="corr-1",
                    actor="alice",
                    tenant="tenant-a",
                    environment=PortableEnvironment.DEV,
                    team_id="fredlab",
                ),
            )
        )

    context = seen["context"]
    kwargs = seen["kwargs"]
    assert isinstance(context, dict) and isinstance(kwargs, dict)
    assert "chat_profile_id" not in context
    assert kwargs.get("tuning") is None
    assert not kwargs.get("team_disabled_model_ids")
    assert not kwargs.get("reasoning_enabled_model_ids")


@pytest.mark.asyncio
async def test_local_registry_invoker_drains_runtime_events_after_final(
    monkeypatch,
) -> None:
    """
    Ensure an in-process nested invocation lets the runtime generator finish.

    The runtime generator owns cleanup in its ``finally`` block. Returning from
    LocalRegistryAgentInvoker.invoke() as soon as the first FinalRuntimeEvent is
    observed can close the async generator prematurely and run that cleanup from
    a different asyncio context.
    """

    seen: dict[str, bool] = {
        "continued_after_final": False,
        "cleaned_up": False,
    }

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
        _ = (
            definition,
            request,
            access_token,
            team_id,
            registry,
            exchange_id,
        )
        try:
            yield {"kind": "final", "sequence": 0, "content": "ok"}
            seen["continued_after_final"] = True
        finally:
            seen["cleaned_up"] = True

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

    with active_turn("rags.sample.echo", session="session-1"):
        result = await invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=invocation_context(
                    request_id="req-1",
                    correlation_id="corr-1",
                    actor="alice",
                    tenant="tenant-a",
                    environment=PortableEnvironment.DEV,
                    session_id="session-1",
                    user_id="alice",
                    team_id="fredlab",
                ),
            )
        )

    assert result.content == "ok"
    assert result.is_error is False
    assert seen["continued_after_final"] is True
    assert seen["cleaned_up"] is True


@pytest.mark.asyncio
async def test_local_registry_invoker_applies_invocation_scope(monkeypatch) -> None:
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
        return invocation_context(
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
    with active_turn("rags.sample.echo", session="session-1"):
        await invoker.invoke(
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
    context = seen["context"]
    assert isinstance(context, dict)
    assert context["selected_document_uids"] == ["doc-a", "doc-b"]
    assert context["selected_document_libraries_ids"] == ["lib-1"]
    assert context["search_policy"] == "strict"

    # Without scope → no narrowing keys are injected (no regression).
    seen.clear()
    with active_turn("rags.sample.echo", session="session-1"):
        await invoker.invoke(
            AgentInvocationRequest(
                agent_id=definition.agent_id,
                message="hello",
                context=_portable(),
            )
        )
    context = seen["context"]
    assert isinstance(context, dict)
    assert "selected_document_uids" not in context
    assert "search_policy" not in context


@pytest.mark.asyncio
async def test_nested_invocation_cannot_replace_person_with_actor(monkeypatch):
    from fred_runtime.runtime_support.authority import AuthorityLostError

    iterate = AsyncMock(side_effect=AssertionError("Unbound person reached execution"))
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", iterate)
    definition = _EchoAgent()
    invoker = agent_app_module.LocalRegistryAgentInvoker(
        registry={definition.agent_id: definition}, access_token=None
    )
    with active_turn(definition.agent_id):
        with pytest.raises(AuthorityLostError):
            await invoker.invoke(
                AgentInvocationRequest(
                    agent_id=definition.agent_id,
                    message="hi",
                    context=invocation_context(
                        request_id="r",
                        correlation_id="c",
                        actor="alice",
                        tenant="default",
                        environment=PortableEnvironment.DEV,
                        user_id=None,
                    ),
                )
            )
    iterate.assert_not_called()


@pytest.mark.asyncio
async def test_local_registry_invoker_requires_active_parent_authority() -> None:
    from typing import cast

    from fred_runtime.app.agent_app import LocalRegistryAgentInvoker
    from fred_runtime.runtime_support.authority import AuthorityLostError
    from fred_sdk.contracts.context import AgentInvocationRequest

    invoker = LocalRegistryAgentInvoker(registry={}, access_token=None)
    with pytest.raises(AuthorityLostError):
        await invoker.invoke(
            cast(AgentInvocationRequest, SimpleNamespace(agent_id="child"))
        )


def test_bound_context_cannot_supply_inference_permission() -> None:
    from fred_sdk.contracts.context import BoundRuntimeContext

    assert "platform_chat_model_binding" not in BoundRuntimeContext.model_fields
    assert "usable_model_ids" not in BoundRuntimeContext.model_fields


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.asyncio
async def test_build_runtime_services_uses_persisted_document_source_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, enabled: bool
) -> None:
    from uuid import UUID

    from fred_runtime.react.react_prompting import build_attachment_context_suffix
    from fred_sdk.contracts.models import AgentTuning, StoredCapabilityConfig
    from pydantic import BaseModel
    from weaver_fixtures import active_turn, local_binding

    class DocumentConfig(BaseModel):
        attachments: bool = True
        team_documents: bool = True
        bind_libraries: bool = False
        library_tag_ids: list[str] = []
        document_uids: list[str] | None = None

    class Registry:
        def __contains__(self, capability_id: str) -> bool:
            return capability_id == "document_access"

        def capability(self, capability_id: str) -> Any:
            assert capability_id == "document_access"
            return SimpleNamespace(ConfigModel=DocumentConfig)

    definition = _EchoAgent()
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["document_access"],
        capability_config={
            "document_access": StoredCapabilityConfig(
                schema_version="0.2.0",
                config={"attachments": enabled, "team_documents": not enabled},
            )
        },
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=str(UUID(int=301)),
            user_id="alice",
            team_id="fredlab",
            selected_document_uids=[],
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="alice",
            tenant="fredlab",
            environment=PortableEnvironment.DEV,
            session_id=str(UUID(int=301)),
            user_id="alice",
            team_id="fredlab",
        ),
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
    )
    app = create_agent_app(
        registry={definition.agent_id: definition}, config=_build_test_config(tmp_path)
    )
    binding = local_binding(
        definition.agent_id,
        runtime_context=binding.runtime_context,
        portable_context=binding.portable_context,
    )
    with (
        TestClient(app),
        active_turn(
            binding,
            attachments=[
                dict(
                    document_id=str(UUID(int=401)), name="private.csv", mime="text/csv"
                )
            ],
        ) as authority,
    ):
        services = agent_app_module._build_runtime_services(
            definition,
            binding,
            team_id="fredlab",
            tuning=tuning,
            capability_registry=cast(Any, Registry()),
        )

        expected = (UUID(int=401),) if enabled else ()
        assert (
            authority.document_context(binding.runtime_context).attachment_ids
            == expected
        )
        suffix = build_attachment_context_suffix(binding, tabular_tools_available=False)
        assert ("private.csv" in suffix) is enabled
        assert isinstance(services.tool_provider, agent_app_module.FredMcpToolProvider)
        sent = services.tool_provider._agent.document_context()
        from fred_core.documents.transport import DocumentAccessContext

        assert (
            DocumentAccessContext.model_validate_json(sent).attachment_ids == expected
        )

    assert isinstance(services.tool_provider, agent_app_module.FredMcpToolProvider)
    assert services.tool_provider._agent._document_scope.is_empty


@pytest.mark.asyncio
async def test_build_runtime_services_binds_scratchpad_to_trusted_conversation_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MemoryFilesystem:
        def __init__(self) -> None:
            self.files: dict[str, bytes] = {}

        async def read(self, path: str) -> bytes:
            try:
                return self.files[path]
            except KeyError as exc:
                raise FileNotFoundError(path) from exc

        async def write(self, path: str, data: bytes | str) -> None:
            self.files[path] = data.encode() if isinstance(data, str) else data

        async def list(self, prefix: str = "") -> list[Any]:
            return []

        async def mkdir(self, path: str) -> None:
            del path

    storage = _MemoryFilesystem()
    runtime_context = FredRuntimeContext(
        RuntimeConfig(
            knowledge_flow_url="http://knowledge-flow.invalid",
            filesystem=cast(Any, storage),
        )
    )
    monkeypatch.setattr(
        "fred_runtime.runtime_context._RUNTIME_CONTEXT", runtime_context
    )

    def _binding(
        *, trusted_session_id: str | None, request_id: str
    ) -> BoundRuntimeContext:
        return BoundRuntimeContext(
            runtime_context=RuntimeContext(session_id=trusted_session_id),
            portable_context=PortableContext(
                request_id=request_id,
                correlation_id=f"correlation-{request_id}",
                actor="alice",
                tenant="fredlab",
                environment=PortableEnvironment.DEV,
                session_id="portable-shadow",
            ),
        )

    definition = _EchoAgent()
    first = agent_app_module._build_runtime_services(
        definition,
        _binding(trusted_session_id="trusted-session", request_id="request-one"),
    ).conversation_filesystem
    fresh_same_session = agent_app_module._build_runtime_services(
        definition,
        _binding(trusted_session_id="trusted-session", request_id="request-two"),
    ).conversation_filesystem
    other_session = agent_app_module._build_runtime_services(
        definition,
        _binding(trusted_session_id="other-session", request_id="request-three"),
    ).conversation_filesystem
    request_fallback = agent_app_module._build_runtime_services(
        definition,
        _binding(trusted_session_id=None, request_id="fallback-request"),
    ).conversation_filesystem
    assert first is not None
    assert fresh_same_session is not None
    assert other_session is not None
    assert request_fallback is not None

    await first.write_text("/notes.md", "shared", origin="system")

    assert await fresh_same_session.read_text("/notes.md", origin="system") == "shared"
    with pytest.raises(ConversationScratchpadFileNotFoundError):
        await other_session.read_text("/notes.md", origin="system")

    await request_fallback.write_text("/fallback.md", "request scoped", origin="system")
    assert storage.files == {
        "conversations/trusted-session/scratchpad/notes.md": b"shared",
        "conversations/fallback-request/scratchpad/fallback.md": b"request scoped",
    }


@pytest.mark.asyncio
async def test_nested_turn_cannot_run_without_parent_scope() -> None:
    from fred_runtime.model_routing.turn import current_turn
    from fred_runtime.runtime_support.authority import AuthorityLostError

    with pytest.raises(AuthorityLostError):
        current_turn()


def test_local_registry_invoker_child_cannot_replace_binding_via_portable_context() -> (
    None
):
    """
    Isolation (Slice 1 review): `PortableContext` is `extra="forbid"` — there
    is structurally no field on it (or on `AgentInvocationRequest`) a nested
    child, or a compromised parent, could use to carry a DIFFERENT platform
    chat binding into the nested turn. The only channel is the invoker's own
    private `platform_chat_model_binding` attribute, wired exclusively from
    `_build_runtime_services`'s own `BoundRuntimeContext`.

    How to use it:
    - run in the default offline `fred-runtime` test suite
    """
    with pytest.raises(Exception, match="platform_chat_model_binding"):
        PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="fredlab",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="alice",
            team_id="fredlab",
            platform_chat_model_binding={"provider": "attacker", "name": "forged"},  # pyright: ignore[reportCallIssue]
        )


async def _write_react_v2_checkpoint(
    checkpointer,
    *,
    thread_id: str,
    channel_values: dict[str, Any],
):
    """
    Write one ReAct-V2-shaped checkpoint through the real `FredSqlCheckpointer`
    (the same `aput` production code uses) — a native `interrupt()` leaves only
    a pending write on the `__interrupt__` channel (#2179).

    Always UNNAMESPACED, like production: LangGraph resets `checkpoint_ns` to
    `""` on every root-graph run, so a compiled ReAct agent's checkpoints can
    only ever land there (`test_langgraph_resets_root_checkpoint_namespace`).
    """

    assert await checkpointer.abind_conversation(
        thread_id, conversation_provenance(), allow_create=True
    )
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
    occurrence_id: str | None = None,
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
    payload = {"question": "proceed?"}
    if occurrence_id is not None:
        payload["occurrence_id"] = occurrence_id
    await checkpointer.aput_writes(
        stored_config,
        [("__interrupt__", {"value": payload, "id": interrupt_id})],
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
    Regression for #2179: `_validate_session_checkpoint_access` reads the
    thread's latest checkpoint and accepts the resume by finding its pending
    `"__interrupt__"` write whose `Interrupt.id` matches the client-supplied
    `interrupt_id` (#2216 tightened this from "any pending interrupt" to an
    exact id match).

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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

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
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": "session-react-v2",
                    # LangGraph's Interrupt.id — never a real stored checkpoint
                    # id (#2179's root cause) — but exactly the id the pending
                    # write above carries (#2216's exact-match requirement).
                    "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("request_occurrence_id", "expected_detail"),
    [
        (None, "occurrence_id does not match"),
        ("call-stale", "occurrence_id does not match"),
    ],
)
def test_resume_rejects_missing_or_stale_occurrence_id(
    monkeypatch,
    request_occurrence_id,
    expected_detail,
) -> None:
    async def _fake_load_checkpoint(checkpointer, *, thread_id, checkpoint_ns=""):
        _ = (checkpointer, thread_id, checkpoint_ns)
        return {"id": "cp-1", "channel_values": {"messages": []}}, [
            (
                "task-1",
                "__interrupt__",
                {
                    "id": "interrupt-shared",
                    "value": {"occurrence_id": "call-current"},
                },
            )
        ]

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="rags.sample.echo",
        input="",
        session_id="session-occurrence",
        interrupt_id="interrupt-shared",
        occurrence_id=request_occurrence_id,
        resume_payload={"choice_id": "proceed"},
    )

    with pytest.raises(agent_app_module.HTTPException) as exc:
        asyncio.run(agent_app_module._validate_session_checkpoint_access(request))

    assert exc.value.status_code == 409
    assert expected_detail in exc.value.detail


def test_resume_accepts_matching_occurrence_id(monkeypatch) -> None:
    async def _fake_load_checkpoint(checkpointer, *, thread_id, checkpoint_ns=""):
        _ = (checkpointer, thread_id, checkpoint_ns)
        return {"id": "cp-1", "channel_values": {"messages": []}}, [
            (
                "task-1",
                "__interrupt__",
                {
                    "id": "interrupt-shared",
                    "value": {"occurrence_id": "call-current"},
                },
            )
        ]

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="rags.sample.echo",
        input="",
        session_id="session-occurrence",
        interrupt_id="interrupt-shared",
        occurrence_id="call-current",
        resume_payload={"choice_id": "proceed"},
    )

    asyncio.run(agent_app_module._validate_session_checkpoint_access(request))


def test_legacy_sibling_does_not_accept_an_unknown_occurrence(monkeypatch) -> None:
    async def _fake_load_checkpoint(checkpointer, *, thread_id, checkpoint_ns=""):
        _ = (checkpointer, thread_id, checkpoint_ns)
        return {"id": "cp-1", "channel_values": {"messages": []}}, [
            (
                "task-legacy",
                "__interrupt__",
                {"id": "interrupt-shared", "value": {}},
            ),
            (
                "task-current",
                "__interrupt__",
                {
                    "id": "interrupt-shared",
                    "value": {"occurrence_id": "call-current"},
                },
            ),
        ]

    monkeypatch.setattr(agent_app_module, "load_checkpoint", _fake_load_checkpoint)
    monkeypatch.setattr(
        agent_app_module,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="rags.sample.echo",
        input="",
        session_id="session-occurrence",
        interrupt_id="interrupt-shared",
        occurrence_id="call-unknown",
        resume_payload={"choice_id": "proceed"},
    )

    with pytest.raises(agent_app_module.HTTPException) as exc:
        asyncio.run(agent_app_module._validate_session_checkpoint_access(request))

    assert exc.value.status_code == 409
    assert "occurrence_id does not match" in exc.value.detail


def test_resume_rejects_react_v2_checkpoint_without_pending_interrupt(
    monkeypatch, tmp_path
) -> None:
    """
    The mirror-negative of the acceptance test above: a ReAct V2 checkpoint
    with no pending `"__interrupt__"` write (turn simply finished, nothing
    waiting for approval) must still 409 — a checkpoint that exists is not
    a checkpoint that is waiting.
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

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
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": "session-react-v2-done",
                    "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

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
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": "session-react-input-resume",
                    "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        first = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-exchange-continuity",
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": "session-exchange-continuity",
                    "interrupt_id": "xxh3-routing-hash-not-a-real-checkpoint-id",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-stale-attack"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None

        # 1. interrupt A is pending; resume it with its own id.
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-a",
            )
        )
        resume_a = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": session_id,
                    "interrupt_id": "interrupt-a",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )
        assert resume_a.status_code == 200
        assert calls == ["interrupt-a"]

        # 2. the thread later reaches interrupt B — a different id.
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-b",
            )
        )
        assert "interrupt-a" != "interrupt-b"

        # 3. a stale/duplicated response for A must be rejected — and must
        # never reach the runtime (B's tool has not executed).
        stale_resume = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": session_id,
                    "interrupt_id": "interrupt-a",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )
        assert stale_resume.status_code == 409
        assert stale_resume.json()["detail"] == (
            "interrupt_id does not match the pending HITL request for this session."
        )
        assert calls == ["interrupt-a"]  # unchanged — B never executed

        # 4. resuming with B's own id succeeds, exactly once.
        resume_b = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": session_id,
                    "interrupt_id": "interrupt-b",
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )
        assert resume_b.status_code == 200
        assert calls == ["interrupt-a", "interrupt-b"]


def _assert_hitl_already_resumed(message: str | None) -> None:
    """The rejected duplicate reads as itself, and stays traceable to a log line.

    Both halves matter: the sentence tells the user to stop retrying rather
    than to open a ticket, and the reference is what support correlates — a
    specific sentence does not exempt the turn from being traceable.
    """

    assert message is not None
    sentence, _, reference = message.partition("Contact support with reference ")
    assert sentence == "This HITL request is already being resumed. "
    assert len(reference.rstrip(".")) == 32


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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-replay"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-a",
            )
        )
        payload = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )

        first = client.post("/pod/v1/agents/execute", json=payload)
        assert first.status_code == 200
        assert first.json().get("kind") == "final"
        assert calls == [1]

        replay = client.post("/pod/v1/agents/execute", json=payload)

    assert replay.status_code == 200
    assert replay.json().get("kind") == "execution_error"
    _assert_hitl_already_resumed(replay.json().get("message"))
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-invalid-input"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-real",
            )
        )

        body: dict[str, Any] = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id="session-thread-a",
                interrupt_id="interrupt-a",
            )
        )
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id="session-thread-b",
                interrupt_id="interrupt-b",
            )
        )

        response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "",
                    "session_id": "session-thread-a",
                    "interrupt_id": "interrupt-b",  # belongs to thread B, not A
                    "resume_payload": {"choice_id": "proceed"},
                    "runtime_context": {"user_id": "alice"},
                }
            ),
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
            checkpointer,
            thread_id="session-concurrent",
            interrupt_id="interrupt-a",
        )

        async def _attempt():
            try:
                claim = await agent_app_module._claim_hitl_resume_before_invocation(
                    session_id="session-concurrent",
                    checkpoint_ns="",
                    interrupt_id="interrupt-a",
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-dup-http-concurrent"

    with TestClient(app):
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        await _write_react_v2_interrupt(
            checkpointer,
            thread_id=session_id,
            interrupt_id="interrupt-a",
        )

        payload = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )

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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-setup-failure"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-a",
            )
        )
        payload = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )

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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-start-failure"

    with TestClient(app) as client:
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        asyncio.run(
            _write_react_v2_interrupt(
                checkpointer,
                thread_id=session_id,
                interrupt_id="interrupt-a",
            )
        )
        payload = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )

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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )
    session_id = "session-cancel-mid-invocation"

    with TestClient(app):
        checkpointer = get_runtime_context().config.checkpointer
        assert checkpointer is not None
        await _write_react_v2_interrupt(
            checkpointer,
            thread_id=session_id,
            interrupt_id="interrupt-a",
        )
        payload = managed_payload(
            {
                "agent_id": "rags.sample.echo",
                "input": "",
                "session_id": session_id,
                "interrupt_id": "interrupt-a",
                "resume_payload": {"choice_id": "proceed"},
                "runtime_context": {"user_id": "alice"},
            }
        )

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
    _assert_hitl_already_resumed(duplicate.json().get("message"))
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
    app = create_managed_app(
        monkeypatch, registry=registry, config=_build_test_config(tmp_path)
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json=managed_payload(
                {
                    "agent_id": "rags.sample.echo",
                    "input": "hello",
                    "session_id": "session-normal-turn",
                    "runtime_context": {"user_id": "alice"},
                }
            ),
        )

    assert response.status_code == 200
    assert calls == [None]


@pytest.mark.asyncio
async def test_normal_turn_does_not_query_the_checkpointer(monkeypatch) -> None:
    """#2216 non-regression: `_validate_session_checkpoint_access` must
    return immediately (no checkpointer lookup at all) for a turn that sets
    no `resume_payload` — matching the existing
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


def test_execute_rejects_managed_request_without_team_before_resolution(
    monkeypatch, tmp_path
) -> None:
    async def _unexpected_resolution(**kwargs):
        raise AssertionError("invalid managed request reached instance resolution")

    monkeypatch.setattr(
        agent_app_module, "_resolve_agent_instance", _unexpected_resolution
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
                "agent_instance_id": "instance-without-team",
                "input": "hello",
                "runtime_context": {"user_id": "alice"},
            },
        )

    assert response.status_code == 422


@pytest.mark.parametrize("route", ["execute", "execute/stream", "evaluate"])
def test_security_disabled_does_not_admit_an_anonymous_turn(
    monkeypatch, tmp_path, route
):
    model = ToolFriendlyFakeChatModel(responses=[])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    iterate = AsyncMock(side_effect=AssertionError("Anonymous turn reached execution"))
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", iterate)
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(tmp_path),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/pod/v1/agents/{route}", json=managed_payload({"input": "hi"})
        )
    assert response.status_code == 403
    assert "authenticated person" in response.json()["detail"]
    iterate.assert_not_called()


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


@pytest.mark.usefixtures("empty_runtime_context")
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


@pytest.mark.usefixtures("empty_runtime_context")
def test_capability_block_delivers_mcp_agent_instructions_for_active_server() -> None:
    """
    Ensure `_build_capability_block` delivers an active MCP server's catalog
    `agent_instructions` as an `McpPromptGroup`.

    Why this exists:
    - #1978 moved `agent_instructions` delivery off `_apply_runtime_tuning`
      (which no longer touches the system prompt for MCP at all) and onto
      each MCP server's own capability, assembled by `_build_capability_block`
      from the agent's selected capabilities. #1988 dropped the `mcp:` id
      prefix: the capability id IS the catalog server id (`server.id`). #2455
      moved delivery again, off a per-model-call middleware fragment and onto
      `block.mcp_prompt_groups`, inlined into the static ReAct tool-prompt
      suffix — the instructions must stay enforced even when an operator
      overrides `prompts.system`, since they are never folded into
      `system_prompt_template` itself.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_delivers_mcp_agent_instructions_for_active_server -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
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
    fragments = [group.agent_instructions for group in block.mcp_prompt_groups]
    assert fragments == ["Always cite retrieved claims."]


@pytest.mark.usefixtures("empty_runtime_context")
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

    server_ids = [
        group.server_id
        for group in (block.mcp_prompt_groups if block is not None else ())
    ]
    assert server_ids == ["mcp-storage"]


@pytest.mark.usefixtures("empty_runtime_context")
def test_build_capability_block_for_graph_agent_returns_tools() -> None:
    """
    Ensure `_build_capability_block` builds a non-empty block for a Graph agent.

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
        # This test specifically exercises the Graph capability-block build
        # path — opt back in from GraphAgentDefinition's False default (see
        # AgentDefinition.supports_capabilities).
        supports_capabilities: bool = True

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


@pytest.mark.usefixtures("empty_runtime_context")
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
        # This test specifically exercises the Graph capability-block build
        # path — opt back in from GraphAgentDefinition's False default (see
        # AgentDefinition.supports_capabilities).
        supports_capabilities: bool = True

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


@pytest.mark.usefixtures("empty_runtime_context")
def test_build_capability_block_accepts_hitl_gated_capability_for_graph_agent() -> None:
    """Graph now consumes the same capability HITL declarations as ReAct/Deep."""
    from collections.abc import Mapping as _Mapping

    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityContext,
        CapabilityManifest,
        EmptyModel,
        HitlSpec,
    )
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
        # This test specifically exercises the Graph capability-block build
        # path — opt back in from GraphAgentDefinition's False default (see
        # AgentDefinition.supports_capabilities).
        supports_capabilities: bool = True

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
    assert block.hitl["gated_probe"].spec.require


@pytest.mark.usefixtures("empty_runtime_context")
def test_build_capability_block_ignores_stale_selection_for_capability_unsupported_graph_agent() -> (
    None
):
    """
    A `GraphAgentDefinition` that leaves `supports_capabilities` at its False
    default (the honest "this agent doesn't support capabilities" signal, see
    `AgentDefinition.supports_capabilities`) must never build a block or raise
    — not even when the managed instance's saved tuning still names a
    HITL-gated, otherwise Graph-incompatible capability. This is exactly the
    live-broken-instance case the field was introduced to fix: an agent
    instance whose capability selection was saved back when the picker (still
    driven by pod-wide registration, not the definition's own declaration)
    wrongly offered it. `_effective_capability_ids` and `_build_capability_block`
    both discard the stale selection instead of erroring on it.

    Example:
    - `pytest tests/test_agent_app.py::test_build_capability_block_ignores_stale_selection_for_capability_unsupported_graph_agent -q`
    """
    from collections.abc import Mapping as _Mapping

    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_sdk.contracts.capability import (
        AgentCapability,
        CapabilityContext,
        CapabilityManifest,
        EmptyModel,
        HitlSpec,
    )
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
            id="document_extract",
            version="1.0.0",
            name="cap.document_extract.name",
            description="cap.document_extract.description",
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
        agent_id: str = "test.graph_capability_unsupported_stale_selection"
        role: str = "test"
        description: str = "test"
        # Deliberately NOT overriding `supports_capabilities` — this mirrors
        # a real GraphAgentDefinition subclass like Eva, which relies on the
        # False default rather than declaring it.

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
    assert definition.supports_capabilities is False
    registry = CapabilityRegistry()
    registry.register(_HitlGatedCapability())
    # Mirrors the actual saved tuning on the live-broken Eva instance this bug
    # was reported against: a HITL-gated, non-MCP capability selected while
    # the picker was still (wrongly) offering it.
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=["document_extract"],
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

    assert block is None


@pytest.mark.usefixtures("empty_runtime_context")
def test_capability_block_orders_mcp_prompt_groups_by_server_id() -> None:
    """
    Ensure `block.mcp_prompt_groups` comes back id-sorted, not in selection
    order.

    Why this exists:
    - `build_runtime_tool_prompt_suffix` (#2455) renders each group's `Tools
      for {title}:` header in `mcp_prompt_groups` iteration order, with no
      sort of its own — it trusts the caller. `_build_capability_block`
      inherits `build_capability_agent_block`'s `sorted(capability id)` rule
      (RFC §5.3: "a UI reorder must not change behavior"), and since an MCP
      server's capability id IS its catalog server id (#1988), that's the
      same guarantee this test pins.
    - superseded assertion: before #2455 moved `agent_instructions` delivery
      off a per-model-call middleware fragment, this test guarded
      `_McpInstructionsMiddleware` instances against `create_agent`'s
      duplicate-`.name` rejection — a hazard specific to that mechanism and
      structurally impossible now that it no longer exists.

    How to use it:
    - run in the default offline fred-runtime test suite

    Example:
    - `pytest tests/test_agent_app.py::test_capability_block_orders_mcp_prompt_groups_by_server_id -q`
    """
    from fred_runtime.app.agent_app import _build_capability_block
    from fred_runtime.capabilities import CapabilityRegistry, register_mcp_capabilities
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
        # Reverse-alphabetical selection order, on purpose: the assertion
        # below only holds if the block sorts by id rather than preserving
        # this order.
        selected_capability_ids=["mcp-storage", "mcp-search"],
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
    server_ids = [group.server_id for group in block.mcp_prompt_groups]
    assert server_ids == ["mcp-search", "mcp-storage"]


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
@pytest.mark.parametrize("engine_enabled", [True, False])
async def test_admission_defers_permissions_to_weaver_resolution(
    monkeypatch, minimal_config, engine_enabled
):
    engine = SimpleNamespace(
        enabled=engine_enabled,
        check_user_team_permission_or_raise=AsyncMock(side_effect=AssertionError),
    )
    _wire_engine(monkeypatch, engine)
    request = RuntimeExecuteRequest.model_validate(managed_payload({"input": "hello"}))
    await agent_app_module._authorize_execution_or_raise(
        request, _ALICE, PodApplicationContext(minimal_config)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caller",
    [
        None,
        KeycloakUser(uid="worker", username="worker", roles=["service_agent"]),
        KeycloakUser(
            uid="worker",
            username="worker",
            roles=["service_agent"],
            client_id="agents",
            caller_roles=frozenset({"delegation_caller"}),
        ),
    ],
)
async def test_admission_requires_an_authenticated_person(minimal_config, caller):
    request = RuntimeExecuteRequest.model_validate(managed_payload({"input": "hello"}))
    with pytest.raises(agent_app_module.HTTPException) as error:
        await agent_app_module._authorize_execution_or_raise(
            request, caller, PodApplicationContext(minimal_config)
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [None, "c3"])
async def test_direct_template_execution_has_no_weaver_authority(
    monkeypatch, minimal_config, profile
):
    _wire_engine(monkeypatch, None, security_profile=profile)
    request = RuntimeExecuteRequest(agent_id="demo.agent", input="hi")
    with pytest.raises(agent_app_module.HTTPException) as error:
        await agent_app_module._authorize_execution_or_raise(
            request, _ALICE, PodApplicationContext(minimal_config)
        )
    assert error.value.status_code == 403
    assert "Direct template" in error.value.detail


@pytest.mark.parametrize(
    "team", ["fredlab", "personal", "personal:alice", "personal:bob"]
)
def test_a_team_or_personal_alias_cannot_replace_a_canonical_space(team):
    with pytest.raises(ValidationError, match="runtime_context.space_id is required"):
        RuntimeExecuteRequest(
            agent_instance_id=INSTANCE_ID,
            input="hi",
            runtime_context=RuntimeContext(team_id=team),
        )


class _FakeHistoryStore:
    """session_exists / session_belongs_to_user oracle for F-C tests."""

    def __init__(self, *, exists: bool, owner: str | None) -> None:
        self._exists = exists
        self._owner = owner

    async def session_exists(self, session_id: str) -> bool:
        return self._exists

    async def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        return self._owner is not None and user_id == self._owner


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
            "s-1", _ALICE, container, agent_instance_id="inst-1"
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_session_ownership_allows_owner(monkeypatch, minimal_config) -> None:
    """The session owner may continue/resume their own session."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=True, owner="alice"))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        "s-1", _ALICE, container, agent_instance_id="inst-1"
    )


@pytest.mark.asyncio
async def test_session_ownership_allows_new_session(
    monkeypatch, minimal_config
) -> None:
    """A brand-new session (no rows yet) → allowed; the caller becomes owner."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=False, owner=None))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        "s-1", _ALICE, container, agent_instance_id="inst-1"
    )


@pytest.mark.asyncio
async def test_session_ownership_skipped_when_security_disabled(
    monkeypatch, minimal_config
) -> None:
    """No authenticated user (dev) → ownership not enforced."""
    _wire_history(monkeypatch, _FakeHistoryStore(exists=True, owner="bob"))
    container = PodApplicationContext(minimal_config)

    await agent_app_module._enforce_session_ownership(
        "s-1", None, container, agent_instance_id="inst-1"
    )


# --- CTRLP-12 C1: can_manage_platform admin branch on the delete endpoints -----


def _get_kpi_turns_endpoint():
    """Grab the `/kpi-turns` route's raw endpoint function, bypassing FastAPI's
    dependency-injection layer so it can be called directly with explicit args."""
    router = agent_app_module._build_agent_router(
        registry={}, security_enabled=True, max_chat_input_chars=5_000
    )
    return next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.endpoint.__name__ == "get_kpi_turns"
    )


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
                "space_id": SPACE_ID,
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
            "runtime_context": {
                "user_id": "alice",
                "team_id": "fredlab",
                "space_id": SPACE_ID,
            },
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


@pytest.mark.usefixtures("empty_runtime_context")
@pytest.mark.parametrize(
    "turn_documents", [None, [], ["00000000-0000-0000-0000-000000000101"]]
)
def test_document_ceiling_is_shared_by_all_services_and_child_invoker(
    turn_documents,
) -> None:
    from fred_core.documents.selection import DocumentScope
    from fred_sdk.contracts.models import AgentTuning, StoredCapabilityConfig
    from pydantic import BaseModel
    from weaver_fixtures import INSTANCE_ID, SPACE_ID

    folder = "00000000-0000-0000-0000-000000000201"
    explicit = "00000000-0000-0000-0000-000000000102"

    class DocumentConfig(BaseModel):
        attachments: bool = False
        team_documents: bool = True
        bind_libraries: bool = False
        library_tag_ids: list[str] = []
        document_uids: list[str] | None = None

    class Registry:
        def __contains__(self, capability_id: str) -> bool:
            return capability_id == "document_access"

        def capability(self, capability_id: str) -> Any:
            assert capability_id == "document_access"
            return SimpleNamespace(ConfigModel=DocumentConfig)

    registry = cast(Any, Registry())
    definition = _EchoAgent()
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        capability_config={
            "document_access": StoredCapabilityConfig(
                schema_version="0.3.0",
                config={
                    "bind_libraries": True,
                    "library_tag_ids": [folder],
                    "document_uids": [explicit],
                },
            )
        },
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            user_id="alice",
            session_id="s",
            space_id=SPACE_ID,
            agent_instance_id=INSTANCE_ID,
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="alice",
            tenant=SPACE_ID,
            environment=PortableEnvironment.DEV,
        ),
    )
    services = agent_app_module._build_runtime_services(
        definition,
        binding,
        tuning=tuning,
        registry={definition.agent_id: definition},
        capability_registry=registry,
        turn_options={"document_access": {"document_uids": turn_documents}},
        bound_library_ids=[folder],
    )
    expected = DocumentScope.from_ids([folder], [explicit]).intersect(
        DocumentScope.from_ids(document_ids=turn_documents)
    )
    for port in (
        services.document_search,
        services.document_markdown,
        services.document_extraction,
        services.document_summarize,
        services.agent_invoker,
    ):
        assert getattr(port, "_document_scope") == expected
    assert isinstance(services.tool_provider, agent_app_module.FredMcpToolProvider)
    assert services.tool_provider._agent._document_scope == expected
    # The builtin must not add a folder-only ceiling excluding explicit documents.
    invoker = services.tool_invoker
    builtin = getattr(invoker, "_fallback", invoker)
    assert isinstance(builtin, agent_app_module.FredKnowledgeSearchToolInvoker)
    assert builtin._document_scope == expected
    assert builtin._bound_library_ids is None
