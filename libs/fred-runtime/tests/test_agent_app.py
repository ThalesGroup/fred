from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.execution import ExecutionGrant, ExecutionGrantAction
from fred_sdk.contracts.models import ReActAgentDefinition
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.runtime_context import get_runtime_context


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    """
    Tiny fake chat model that supports tool binding for offline runtime tests.

    Why this exists:
    - the stock fake model is good for scripted responses but does not expose
      `bind_tools(...)`, which the ReAct runtime expects

    How to use it:
    - script a list of `AIMessage` responses and pass it through
      `StaticChatModelFactory`

    Example:
    - `model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])`
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


class StaticChatModelFactory:
    """
    Minimal chat-model factory that always returns the same fake model.

    Why this exists:
    - the pod app factory expects a `chat_model_factory` runtime service
    - this test only needs one deterministic offline model instance

    How to use it:
    - inject it by monkeypatching `_build_chat_model_factory(...)`

    Example:
    - `factory = StaticChatModelFactory(model)`
    """

    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self._model = model

    def build(self, definition, binding):  # type: ignore[override]
        return self._model

    def build_for_operation(
        self, *, definition, binding, purpose: str, operation: str | None
    ):
        """
        Return the same deterministic fake model for operation-specific routing.

        Why this exists:
        - the ReAct runtime now asks the factory for per-operation models before
          falling back to `build(...)`

        How to use it:
        - the regression test keeps one scripted model for the whole turn, so
          this simply delegates to `build(...)`

        Example:
        - `factory.build_for_operation(definition=definition, binding=binding, purpose="react", operation="reasoner")`
        """

        return self.build(definition, binding)


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

    return AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                "metrics_port": 9900,
                "kpi_process_metrics_interval_sec": kpi_process_metrics_interval_sec,
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
                "metrics": metrics_backend,
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
            "ExecutionGrant",
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
                == "http://control-plane:8222/control-plane/v1/agent-instances/instance-1/runtime"
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
                        "mcp_servers": [],
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

    now = int(time.time())
    grant = ExecutionGrant(
        user_id="alice",
        team_id="fredlab",
        agent_instance_id="instance-1",
        action=ExecutionGrantAction.EXECUTE,
        audience="http://localhost",
        issued_at=now - 10,
        expires_at=now + 3600,
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
                "execution_grant": grant.model_dump(mode="json"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "final"
    assert payload["content"] == "Managed execution complete."


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
    monkeypatch.setattr(agent_app_module, "start_http_server", _fake_start_http_server)
    monkeypatch.setattr(agent_app_module, "emit_process_kpis", _neverending_process)
    monkeypatch.setattr(agent_app_module, "emit_sql_pool_kpis", _neverending_pool)

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
        agent_app_module, "start_http_server", _unexpected_start_http_server
    )

    definition = _EchoAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app):
        runtime_writer = get_runtime_context().config.kpi_writer
        assert isinstance(runtime_writer, KPIWriter)
        assert isinstance(runtime_writer.store, KpiLogStore)

    assert observed["metrics_server"] is False


def test_managed_resume_requires_resume_grant(monkeypatch, tmp_path) -> None:
    """
    Ensure managed HITL resume calls require a `resume` execution grant.

    Why this exists:
    - resume flows must not reuse normal `execute` grants
    - the runtime should reject that mismatch before any downstream resolution

    How to use it:
    - run in the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_agent_app.py -q`
    """

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _TeamScopeAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane:8222/control-plane/v1",
        ),
    )

    now = int(time.time())
    grant = ExecutionGrant(
        user_id="alice",
        team_id="fredlab",
        agent_instance_id="instance-1",
        action=ExecutionGrantAction.EXECUTE,
        audience="http://localhost",
        issued_at=now - 10,
        expires_at=now + 3600,
    )

    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_instance_id": "instance-1",
                "input": "",
                "session_id": "managed-session",
                "resume_payload": {"choice_id": "confirm"},
                "execution_grant": grant.model_dump(mode="json"),
            },
        )

    assert response.status_code == 403
    assert "grant action mismatch" in response.json()["detail"]


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
        definition, request, access_token=None, *, team_id=None, registry=None
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
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
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
