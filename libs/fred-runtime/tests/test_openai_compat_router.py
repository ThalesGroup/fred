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
Offline unit tests for the OpenAI-compat /v1 router.

Tests cover:
- GET /v1/models returns registered agents in OpenAI model-list format
- POST /v1/chat/completions streams SSE chunks in OpenAI format with `fred` metadata
- Unknown model returns 404
- Missing user message returns 422

All tests run without any external services.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import fred_runtime.app.openai_compat_router as openai_compat_router_module
import httpx
import pytest
from conftest import (
    StaticChatModelFactory,
    StaticWorkloadTokens,
    ToolFriendlyFakeChatModel,
    install_delegation_runtime,
    migrate_test_config,
)
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    DelegationConfig,
    initialize_delegation,
    preserved_delegation,
)
from fred_core.security.models import StandingAuthorizationError
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    set_delegation_runtime,
)
from fred_runtime.runtime_context import (
    RuntimeConfig,
    get_runtime_context,
    set_runtime_context,
)
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.openai_compat import OpenAIChatRequest
from langchain_core.messages import AIMessage
from starlette.requests import ClientDisconnect


@tool("demo.hello", description="Return a greeting.")
async def _demo_hello(ctx: ToolContext) -> str:
    """Return a static greeting for offline tests."""
    return "hello from tool"


class _HelloAgent(ReActAgent):
    """
    Minimal authored agent for OpenAI-compat router tests.

    Why this exists:
    - the router test needs a real ReActAgent definition so the pod app factory
      wires it correctly; a plain dict would not pass registry validation

    How to use it:
    - register it in the test app registry
    """

    agent_id: str = "test.hello.v1"
    role: str = "Hello Agent"
    description: str = "Greets the user."
    system_prompt_template: str = "Greet the user briefly."
    tools = (_demo_hello,)


def _build_test_config(
    tmp_path,
    *,
    openai_compat: bool = True,
    max_chat_input_chars: int = 5_000,
) -> AgentPodConfig:
    """
    Build an offline pod config with openai_compat enabled.

    Why this exists:
    - mirrors `_build_test_config` in test_agent_app.py; kept local to this
      module so the two test files remain independent

    How to use it:
    - call once per test with pytest's `tmp_path`
    """
    config = AgentPodConfig.model_validate(
        {
            "app": {
                "runtime_id": "test-pod",
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                "openai_compat": openai_compat,
                "max_chat_input_chars": max_chat_input_chars,
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
            "observability": {
                "kpi": {
                    "log": {"enabled": True},
                    "prometheus": {"enabled": False},
                    "opensearch": {"enabled": False},
                }
            },
            "storage": {"postgres": {"sqlite_path": str(tmp_path / "runtime.sqlite3")}},
        }
    )
    # The pod refuses to start against an unmigrated database (#2290) —
    # create the Alembic-owned schema first, as the deploy migration job does.
    return migrate_test_config(config)


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


def test_list_models_returns_registered_agents(monkeypatch, tmp_path) -> None:
    """
    GET /v1/models must return registered agents in OpenAI model-list format.

    Why this test exists:
    - Open WebUI calls /v1/models to populate the model selector; if this
      endpoint is absent or malformed the frontend cannot discover any agent
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "test.hello.v1"
    assert data["data"][0]["object"] == "model"
    assert data["data"][0]["owned_by"] == "fred"


def test_openai_compat_disabled_hides_v1_routes(monkeypatch, tmp_path) -> None:
    """
    When openai_compat is False, /v1/* must not exist.

    Why this test exists:
    - pods that explicitly opt out (e.g. internal workers) must not expose /v1
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    config = _build_test_config(tmp_path, openai_compat=False)
    app = create_agent_app(registry=registry, config=config)

    with TestClient(app) as client:
        assert client.get("/v1/models").status_code == 404


# ---------------------------------------------------------------------------
# /v1/chat/completions — validation errors
# ---------------------------------------------------------------------------


def test_chat_completions_unknown_model_returns_404(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions with an unknown model must return 404.

    Why this test exists:
    - Open WebUI may send a stale model name; a clear 404 is better than a
      500 or hanging stream
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "does-not-exist",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert response.status_code == 404


def test_chat_completions_no_user_message_returns_422(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions with only system messages must return 422.

    Why this test exists:
    - Fred requires a user message to forward to the agent; a system-only
      request cannot be executed and should be rejected before streaming starts
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test.hello.v1",
                "messages": [{"role": "system", "content": "You are helpful."}],
            },
        )
    assert response.status_code == 422


def test_chat_completions_enforces_only_last_user_message(
    monkeypatch, tmp_path
) -> None:
    """The forwarded user message uses code-point counting and a safe error body."""

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="accepted")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(
        registry=registry,
        config=_build_test_config(tmp_path, max_chat_input_chars=5),
    )

    with TestClient(app) as client:
        accepted = client.post(
            "/v1/chat/completions",
            json={
                "model": definition.agent_id,
                "messages": [
                    {"role": "user", "content": "historical message is much longer"},
                    {"role": "assistant", "content": "history"},
                    {"role": "user", "content": "🙂" * 5},
                ],
            },
            headers={"X-Fred-Session-Id": "openai-limit-exact"},
        )
        target_resolution = AsyncMock()
        monkeypatch.setattr(
            openai_compat_router_module,
            "_resolve_agent_instance",
            target_resolution,
        )
        rejected_text = "界" * 6
        rejected = client.post(
            "/v1/chat/completions",
            json={
                "model": definition.agent_id,
                "messages": [{"role": "user", "content": rejected_text}],
            },
        )

    assert accepted.status_code == 200
    assert rejected.status_code == 400
    assert rejected.json() == {
        "error": {
            "message": "Your message exceeds the 5-character limit.",
            "type": "invalid_request_error",
            "param": "messages",
            "code": "chat_input_too_long",
            "limit_chars": 5,
            "actual_chars": 6,
        }
    }
    assert rejected_text not in rejected.text
    target_resolution.assert_not_awaited()


# ---------------------------------------------------------------------------
# /v1/chat/completions — streaming
# ---------------------------------------------------------------------------


def test_chat_completions_streams_openai_chunks_and_done(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions must stream OpenAI-shaped SSE chunks ending with [DONE].

    Why this test exists:
    - verifies the full SSE pipeline: request → Fred stream → OpenAI chunk
      transformation → [DONE] sentinel
    - asserts that at least one chunk carries delta content and that the final
      chunk has finish_reason="stop"
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="Hello there.")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test.hello.v1",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
            # session_id is required when a SQL checkpointer is active:
            # LangGraph needs a non-None thread_id when a checkpointer is configured.
            headers={"X-Fred-Session-Id": "test-session-openai-compat"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    lines = response.text.splitlines()
    assert "data: [DONE]" in lines

    # Parse all data lines (excluding [DONE])
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks, "Expected at least one SSE chunk before [DONE]"

    # Every chunk must have the required OpenAI fields
    for chunk in chunks:
        assert chunk["object"] == "chat.completion.chunk"
        assert chunk["model"] == "test.hello.v1"
        assert "choices" in chunk
        assert chunk["id"].startswith("chatcmpl-")

    # The final chunk must have finish_reason="stop"
    final_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert final_chunks, "Expected a chunk with finish_reason=stop"


# ---------------------------------------------------------------------------
# /v1/chat/completions — admission
# ---------------------------------------------------------------------------

PERSON_TOKEN = "person-bearer-token"


class _AuditingContainer:
    """What the route asks of the pod container: the two attributes the audit
    helper writes to, and the control-plane client the resolution stub ignores."""

    def __init__(self) -> None:
        self._audit_events_lock = threading.Lock()
        self.audit_events_buffer: list[dict[str, Any]] = []

    def get_control_plane_http_client(self) -> httpx.AsyncClient | None:
        return None


class _ControlPlaneContainer(_AuditingContainer):
    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__()
        self._client = client

    def get_control_plane_http_client(self) -> httpx.AsyncClient:
        return self._client


@pytest.fixture
def compat_pod() -> Iterator[_AuditingContainer]:
    """An offline pod for the /v1 surface: a runtime context with no engine and
    no delegation left installed for whatever test runs next."""
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    yield _AuditingContainer()
    set_delegation_runtime(None)
    set_runtime_context(None)


def install_delegation(*, workload_client: bool = True) -> DelegationRuntime:
    return install_delegation_runtime(
        StaticWorkloadTokens() if workload_client else None
    )


def compat_client(
    monkeypatch,
    captured: dict[str, Any],
    container: _AuditingContainer,
    user: KeycloakUser | None = None,
) -> TestClient:
    """A client over the /v1 router alone: the turn and the instance resolution
    are stubbed so the test reads what admission handed them."""

    definition = _HelloAgent()

    async def _fake_resolve(**kwargs: Any):
        captured["resolved_with"] = kwargs.get("access_token")
        return agent_app_module._ResolvedExecutionTarget(
            definition=definition,
            effective_agent_id=definition.agent_id,
            team_id=kwargs.get("team_id"),
        )

    async def _fake_iterate(_definition, _request, **kwargs: Any):
        captured["kwargs"] = kwargs
        provider = kwargs.get("credential_provider")
        if provider is not None:
            captured["credentials"] = await provider.credentials()
            captured["record"] = getattr(provider, "record", None)
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        openai_compat_router_module, "_resolve_agent_instance", _fake_resolve
    )
    monkeypatch.setattr(
        openai_compat_router_module, "_iterate_runtime_event_payloads", _fake_iterate
    )
    monkeypatch.setattr(
        openai_compat_router_module,
        "get_pod_container_from_app",
        lambda _app: container,
    )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        openai_compat_router_module.create_openai_compat_router(
            {definition.agent_id: definition},
            security_enabled=True,
            max_chat_input_chars=5_000,
            authenticated_user_dep=lambda: (
                user or KeycloakUser(uid="alice", username="alice", roles=["reader"])
            ),
        ),
        prefix="/v1",
    )
    return TestClient(app)


def chat_completion(client: TestClient):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": "test.hello.v1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
        headers={
            "Authorization": f"Bearer {PERSON_TOKEN}",
            "X-Fred-Session-Id": "session-compat",
            "X-Fred-Team-Id": "team-1",
        },
    )


@pytest.mark.parametrize(
    ("unavailable", "expected_status", "cause"),
    [(True, 503, "standing_unavailable"), (False, 403, "standing_refused")],
)
def test_chat_completion_preserves_standing_decision_at_http_boundary(
    monkeypatch, compat_pod, unavailable, expected_status, cause
) -> None:
    install_delegation()
    rebac = SimpleNamespace(
        enabled=True,
        check_user_team_permission_or_raise=AsyncMock(
            side_effect=StandingAuthorizationError(unavailable=unavailable)
        ),
    )
    context = get_runtime_context()
    context._config = replace(context.config, rebac_engine=rebac)
    captured: dict[str, Any] = {}

    with compat_client(monkeypatch, captured, compat_pod) as client:
        response = chat_completion(client)

    assert response.status_code == expected_status
    assert response.headers["X-Fred-Denial-Cause"] == cause
    assert "kwargs" not in captured
    assert PERSON_TOKEN not in response.text


def test_a_chat_completion_under_delegation_carries_no_persons_bearer(
    monkeypatch, compat_pod
) -> None:
    """This surface admits a run like every other one: the turn calls out with
    the workload bearer and the grant, never with the person's token."""
    runtime = install_delegation()
    captured: dict[str, Any] = {}

    with compat_client(monkeypatch, captured, compat_pod) as client:
        response = chat_completion(client)

    assert response.status_code == 200
    credentials = captured["credentials"]
    assert credentials.delegated is True
    assert credentials.authorization == "Bearer workload-token"
    assert credentials.parameters[GRANT_PARAM_PERSON] == "alice"
    assert credentials.parameters[GRANT_PARAM_AGENT] == "test.hello.v1"
    assert PERSON_TOKEN not in str(credentials)
    record = captured["record"]
    assert record.run_id == credentials.parameters[GRANT_PARAM_RUN]
    assert record.person_id == "alice"
    # The response's end releases the record, although this turn never did.
    assert len(runtime.records) == 0
    # The person's credential is spent on the one call that verifies them.
    assert captured["resolved_with"] == PERSON_TOKEN


@pytest.mark.parametrize(
    "roles", [[], ["service_agent"]], ids=["caller-role", "also-service-role"]
)
@pytest.mark.parametrize(
    "accept_delegated_calls", [False, True], ids=["acting-only", "also-accepting"]
)
def test_a_workload_naming_no_person_cannot_run_a_chat_completion(
    monkeypatch, compat_pod, roles: list[str], accept_delegated_calls: bool
) -> None:
    """The /v1 surface admits runs too, so it refuses a workload acting as itself."""
    caller = KeycloakUser(
        uid="svc",
        username="svc",
        roles=roles,
        client_id="a-workload",
        caller_roles=frozenset({"delegation_caller"}),
    )
    install_delegation()
    captured: dict[str, Any] = {}

    with preserved_delegation():
        # The caller role is recognised in either direction, not only where
        # grants are believed.
        initialize_delegation(
            DelegationConfig(
                act_for_people=True, accept_delegated_calls=accept_delegated_calls
            )
        )
        with compat_client(monkeypatch, captured, compat_pod, user=caller) as client:
            response = chat_completion(client)

    assert response.status_code == 403
    assert response.json()["detail"] == "delegated_person_required"
    assert "kwargs" not in captured
    assert "resolved_with" not in captured


def test_a_service_identity_runs_a_chat_completion_on_its_own_bearer(
    monkeypatch, compat_pod
) -> None:
    """A service identity without the caller role names no person: the turn gets
    no provider and reads the caller's own bearer, as with delegation off."""
    runtime = install_delegation()
    captured: dict[str, Any] = {}
    caller = KeycloakUser(
        uid="svc", username="svc", roles=["service_agent"], client_id="evaluation"
    )

    with preserved_delegation():
        initialize_delegation(
            DelegationConfig(act_for_people=True, accept_delegated_calls=True)
        )
        with compat_client(monkeypatch, captured, compat_pod, user=caller) as client:
            response = chat_completion(client)

    assert response.status_code == 200
    assert captured["kwargs"]["credential_provider"] is None
    assert captured["kwargs"]["access_token"] == PERSON_TOKEN
    assert len(runtime.records) == 0


def test_a_chat_completion_fails_closed_when_delegation_is_unusable(
    monkeypatch, compat_pod
) -> None:
    """No workload client means no delegated call can be made; the request is
    refused rather than falling back to the person's bearer."""
    install_delegation(workload_client=False)
    captured: dict[str, Any] = {}

    with compat_client(monkeypatch, captured, compat_pod) as client:
        response = chat_completion(client)

    assert response.status_code == 503
    assert "kwargs" not in captured
    assert "resolved_with" not in captured


def test_with_the_flag_off_a_chat_completion_gets_no_provider_at_all(
    monkeypatch, compat_pod
) -> None:
    """Nothing stands between this surface's turn and the person's token: its
    clients read it off the context exactly as they did before delegation."""
    set_delegation_runtime(None)
    captured: dict[str, Any] = {}

    with compat_client(monkeypatch, captured, compat_pod) as client:
        response = chat_completion(client)

    assert response.status_code == 200
    assert "data: [DONE]" in response.text
    assert captured["kwargs"]["credential_provider"] is None
    assert captured["kwargs"]["access_token"] == PERSON_TOKEN
    assert "credentials" not in captured


@pytest.mark.asyncio
async def test_delegated_chat_completion_makes_no_control_plane_call(
    monkeypatch, compat_pod
) -> None:
    install_delegation()
    definition = _HelloAgent()
    control_plane_requests: list[httpx.Request] = []
    captured: dict[str, Any] = {}

    def control_plane_handler(request: httpx.Request) -> httpx.Response:
        control_plane_requests.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(control_plane_handler)
    ) as control_plane_client:
        container = _ControlPlaneContainer(control_plane_client)
        set_runtime_context(
            FredRuntimeContext(
                RuntimeConfig(
                    knowledge_flow_url="http://kf.invalid/kf/v1",
                    control_plane_url="http://control-plane.invalid",
                    control_plane_http_client=control_plane_client,
                )
            )
        )
        monkeypatch.setattr(
            openai_compat_router_module,
            "get_pod_container_from_app",
            lambda _app: container,
        )

        async def iterate(_definition, _request, **kwargs: Any):
            provider = kwargs["credential_provider"]
            captured.update(kwargs)
            try:
                yield {"kind": "final", "content": "done"}
            finally:
                agent_app_module._discard_run_record(provider)

        monkeypatch.setattr(
            openai_compat_router_module,
            "_iterate_runtime_event_payloads",
            iterate,
        )
        app = FastAPI()
        app.include_router(
            openai_compat_router_module.create_openai_compat_router(
                {definition.agent_id: definition},
                security_enabled=True,
                max_chat_input_chars=5_000,
                authenticated_user_dep=lambda: KeycloakUser(
                    uid="alice", username="alice", roles=["reader"]
                ),
            ),
            prefix="/v1",
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://runtime.invalid"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": definition.agent_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
                headers={
                    "Authorization": f"Bearer {PERSON_TOKEN}",
                    "X-Fred-Session-Id": "session-compat",
                    "X-Fred-Team-Id": "team-1",
                },
            )

    assert response.status_code == 200
    assert control_plane_requests == []
    assert captured["team_id"] == "team-1"
    assert captured["access_token"] is None
    # The iterator, not the route, releases the record once the run is over.
    assert captured["owns_run_record"] is True


@pytest.mark.asyncio
async def test_delegated_stream_failure_logs_only_bounded_fields(
    monkeypatch, compat_pod, caplog
) -> None:
    runtime = install_delegation()
    definition = _HelloAgent()
    container = _AuditingContainer()

    async def resolve(**kwargs: Any):
        return agent_app_module._ResolvedExecutionTarget(
            definition=definition,
            effective_agent_id=definition.agent_id,
            team_id=kwargs["team_id"],
        )

    async def iterate(*args: Any, **kwargs: Any):
        try:
            if kwargs.get("yield_unexpected"):
                yield {}
            raise RuntimeError("upstream-stream-canary")
        finally:
            agent_app_module._discard_run_record(kwargs["credential_provider"])

    monkeypatch.setattr(openai_compat_router_module, "_resolve_agent_instance", resolve)
    monkeypatch.setattr(
        openai_compat_router_module, "_iterate_runtime_event_payloads", iterate
    )
    monkeypatch.setattr(
        openai_compat_router_module,
        "get_pod_container_from_app",
        lambda _app: container,
    )
    app = FastAPI()
    app.include_router(
        openai_compat_router_module.create_openai_compat_router(
            {definition.agent_id: definition},
            security_enabled=True,
            max_chat_input_chars=5_000,
            authenticated_user_dep=lambda: KeycloakUser(
                uid="person-canary", username="person-canary", roles=[]
            ),
        ),
        prefix="/v1",
    )
    caplog.set_level(logging.DEBUG, logger=openai_compat_router_module.__name__)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://runtime.invalid"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": definition.agent_id,
                "messages": [{"role": "user", "content": "content-canary"}],
            },
            headers={"X-Fred-Team-Id": "team-canary"},
        )

    assert response.status_code == 200
    assert "data: [DONE]" in response.text
    payload = " ".join(
        record.getMessage()
        for record in caplog.records
        if record.name == openai_compat_router_module.__name__
    )
    assert "event=delegated_stream outcome=failed reason=execution_failed" in payload
    for canary in (
        "upstream-stream-canary",
        "person-canary",
        "content-canary",
        "team-canary",
        definition.agent_id,
    ):
        assert canary not in payload
    assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_closing_compatibility_stream_waits_for_runtime_cleanup(
    monkeypatch, compat_pod
) -> None:
    runtime = install_delegation()
    definition = _HelloAgent()
    container = _AuditingContainer()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def resolve(**kwargs: Any):
        return agent_app_module._ResolvedExecutionTarget(
            definition=definition,
            effective_agent_id=definition.agent_id,
            team_id=kwargs["team_id"],
        )

    async def iterate(*args: Any, **kwargs: Any):
        try:
            yield {"kind": "final", "content": "done"}
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()
            agent_app_module._discard_run_record(kwargs["credential_provider"])

    monkeypatch.setattr(openai_compat_router_module, "_resolve_agent_instance", resolve)
    monkeypatch.setattr(
        openai_compat_router_module, "_iterate_runtime_event_payloads", iterate
    )
    monkeypatch.setattr(
        openai_compat_router_module,
        "get_pod_container_from_app",
        lambda _app: container,
    )
    app = FastAPI()
    router = openai_compat_router_module.create_openai_compat_router(
        {definition.agent_id: definition},
        security_enabled=True,
        max_chat_input_chars=5_000,
        authenticated_user_dep=lambda: None,
    )
    app.include_router(router, prefix="/v1")
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/chat/completions"
    )
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "POST",
            "path": "/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"x-fred-team-id", b"team")],
            "scheme": "http",
            "server": ("runtime.invalid", 80),
            "client": ("synthetic", 1),
        }
    )
    response = await cast(Any, route).endpoint(
        OpenAIChatRequest.model_validate(
            {
                "model": definition.agent_id,
                "messages": [{"role": "user", "content": "hi"}],
            }
        ),
        request,
        KeycloakUser(uid="person", username="person", roles=[]),
    )
    iterator = cast(Any, response.body_iterator)

    await anext(iterator)
    close_task = asyncio.create_task(iterator.aclose())
    await asyncio.wait_for(cleanup_started.wait(), 1)
    assert close_task.done() is False
    assert len(runtime.records) == 1
    release_cleanup.set()
    await asyncio.wait_for(close_task, 1)

    assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_a_compatibility_stream_whose_send_fails_still_ends_its_run(
    monkeypatch, compat_pod
) -> None:
    """Under ASGI 2.4 a disconnect surfaces as a failed `send` and the response
    raises instead of ending: the run behind it is released all the same."""
    runtime = install_delegation()
    definition = _HelloAgent()
    closed: list[bool] = []

    async def resolve(**kwargs: Any):
        return agent_app_module._ResolvedExecutionTarget(
            definition=definition,
            effective_agent_id=definition.agent_id,
            team_id=kwargs["team_id"],
        )

    async def iterate(*args: Any, **kwargs: Any):
        try:
            yield {"kind": "final", "content": "done"}
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    monkeypatch.setattr(openai_compat_router_module, "_resolve_agent_instance", resolve)
    monkeypatch.setattr(
        openai_compat_router_module, "_iterate_runtime_event_payloads", iterate
    )
    monkeypatch.setattr(
        openai_compat_router_module,
        "get_pod_container_from_app",
        lambda _app: _AuditingContainer(),
    )
    app = FastAPI()
    router = openai_compat_router_module.create_openai_compat_router(
        {definition.agent_id: definition},
        security_enabled=True,
        max_chat_input_chars=5_000,
        authenticated_user_dep=lambda: None,
    )
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/chat/completions"
    )
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.4"},
        "app": app,
        "method": "POST",
        "path": "/v1/chat/completions",
        "query_string": b"",
        "headers": [(b"x-fred-team-id", b"team")],
        "scheme": "http",
        "server": ("runtime.invalid", 80),
        "client": ("synthetic", 1),
    }
    response = await cast(Any, route).endpoint(
        OpenAIChatRequest.model_validate(
            {
                "model": definition.agent_id,
                "messages": [{"role": "user", "content": "hi"}],
            }
        ),
        Request(scope),
        KeycloakUser(uid="person", username="person", roles=[]),
    )
    assert len(runtime.records) == 1

    async def receive() -> dict[str, Any]:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}  # pragma: no cover

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            raise OSError("synthetic broken pipe")

    with pytest.raises(ClientDisconnect):
        await asyncio.wait_for(response(scope, receive, send), 1)

    assert closed == [True]
    assert len(runtime.records) == 0
