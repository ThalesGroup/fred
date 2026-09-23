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

"""Admission: the one moment the person's credential is used.

What it leaves behind is the run record — the only thing that names the person
for the rest of the run — and a context with no credential in it at all. What it
refuses is a run it could not make a delegated call for.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security import oidc
from fred_core.security.backend_to_backend_auth import M2MTokenProvider
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.security.oidc import get_current_user_without_gcu
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationRuntime,
    OutboundCredentialProvider,
    OutboundCredentials,
    RunRecord,
    set_delegation_runtime,
)
from fred_runtime.common.run_lifecycle import register_run
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
    RunCeilingReachedError,
    RunStopError,
)
from fred_runtime.runtime_support.run_budget import (
    RunScope,
    configure_run_limits,
    terminal_stop_event,
)
from fred_sdk.authoring import ReActAgent
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from test_delegation_receiver_integration import _NOW, _FixedDateTime, _Jwks

PERSON_TOKEN = "person-bearer-token"
WORKLOAD_CLIENT_ID = "agent-backend"
# The workload that asks this pod to run for someone it names, trusted through
# the pod's own `security.delegation.caller_policies` — never the pod's client.
CALLING_WORKLOAD = "campaign-worker"
CALLING_WORKLOAD_SUBJECT = "campaign-worker-service-account"
CAMPAIGN_CREATOR = "creator-1"
GRANT_ISSUER = "https://id.invalid/realms/fred"
GRANT_AUDIENCE = "agent-runtime"
CALLER_POLICY = CallerPolicy(
    client_id=CALLING_WORKLOAD, subject=CALLING_WORKLOAD_SUBJECT
)


class FakeWorkloadTokens(M2MTokenProvider):
    """The pod's own bearer, already in hand: the real provider serves a cached
    token and only talks to the realm when it has none, which offline it never
    would."""

    def __init__(self, token: str = "workload-token") -> None:
        self.token = token

    async def get_token(self) -> str:
        return self.token


class Container(PodApplicationContext):
    """The pod container as admission and the gate use it: the audit buffer they
    write to, the KPI writer their stage timers take, and a control-plane client
    the stubbed binding call never sends anything through. Built without the pod
    configuration, which none of that path reads."""

    def __init__(self) -> None:
        self._audit_events_lock = threading.Lock()
        self.audit_events_buffer = deque(maxlen=200)
        self._kpi_writer = NoOpKPIWriter()
        self._control_plane_http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(503))
        )


def audited(container: Container, name: str) -> list[dict[str, object]]:
    """The audit events of one kind, read as the records they are written as."""
    return [
        dict(event)
        for event in container.audit_events_buffer
        if event["audit_event"] == name
    ]


@pytest.fixture(autouse=True)
def _no_delegation_between_tests():
    yield
    set_delegation_runtime(None)


def install_delegation(
    *,
    allowed_callers: list[str] | None = None,
    caller_policies: list[CallerPolicy] | None = None,
    token_provider: Any = "default",
) -> DelegationRuntime:
    config = (
        DelegationConfig(
            enabled=True,
            allowed_callers=allowed_callers or [],
            caller_policies=caller_policies or [],
        )
        if allowed_callers or caller_policies
        else DelegationConfig.model_construct(enabled=True, allowed_callers=[])
    )
    runtime = DelegationRuntime(
        config=config,
        token_provider=(
            FakeWorkloadTokens() if token_provider == "default" else token_provider
        ),
        workload_client_id=WORKLOAD_CLIENT_ID,
    )
    set_delegation_runtime(runtime)
    return runtime


def execute_request(**overrides) -> RuntimeExecuteRequest:
    return RuntimeExecuteRequest(
        agent_instance_id=overrides.pop("agent_instance_id", "instance-1"),
        input="hello",
        session_id=overrides.pop("session_id", "session-1"),
        runtime_context=overrides.pop(
            "runtime_context",
            RuntimeContext(
                user_id="alice",
                team_id="team-1",
                access_token=PERSON_TOKEN,
                refresh_token="person-refresh-token",
            ),
        ),
        **overrides,
    )


def person(uid: str = "alice", roles: list[str] | None = None) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=roles or ["reader"])


# ---------------------------------------------------------------------------
# The record admission writes
# ---------------------------------------------------------------------------


def test_admission_records_the_run_from_the_verified_token():
    runtime = install_delegation(allowed_callers=["agent-backend"])
    request = execute_request()

    provider = agent_app_module._admission_credentials(
        request,
        person(roles=["reader", "writer"]),
        Container(),
    )

    assert isinstance(provider, DelegatedCredentialProvider)
    record = runtime.records.get(provider.run_id)
    assert record is not None
    assert record.person_id == "alice"
    assert record.roles == ("reader", "writer")
    assert record.team_id == "team-1"
    assert record.agent_id == "instance-1"
    assert record.parent_run_id is None
    assert record.mode == "attended"
    assert record.started_at > 0


def test_admission_drops_the_persons_credential_once_the_record_exists():
    install_delegation(allowed_callers=["agent-backend"])
    request = execute_request()

    agent_app_module._admission_credentials(request, person(), Container())

    assert request.runtime_context is not None
    assert request.runtime_context.access_token is None
    assert request.runtime_context.refresh_token is None
    assert request.runtime_context.access_token_expires_at is None


@pytest.mark.asyncio
async def test_the_grant_that_follows_admission_names_the_admitted_person():
    install_delegation(allowed_callers=["agent-backend"])
    request = execute_request()

    provider = agent_app_module._admission_credentials(request, person(), Container())

    assert provider is not None
    credentials = await provider.credentials()
    assert credentials.parameters[GRANT_PARAM_PERSON] == "alice"
    assert credentials.parameters[GRANT_PARAM_AGENT] == "instance-1"
    assert credentials.authorization == "Bearer workload-token"


def test_admission_audit_keeps_identifiers_only_in_the_run_record():
    install_delegation(allowed_callers=[WORKLOAD_CLIENT_ID])
    container = Container()

    provider = agent_app_module._admission_credentials(
        execute_request(), person(), container
    )

    assert isinstance(provider, DelegatedCredentialProvider)
    events = audited(container, "delegated_run_admitted")
    assert len(events) == 1
    assert events[0]["outcome"] == "accepted"
    assert events[0]["reason"] == "delegated_run_admitted"
    for canary in (
        provider.run_id,
        WORKLOAD_CLIENT_ID,
        "alice",
        "team-1",
        "instance-1",
        PERSON_TOKEN,
    ):
        assert canary not in str(events[0])


# ---------------------------------------------------------------------------
# A run that never starts leaves nothing behind
# ---------------------------------------------------------------------------


async def authorize_and_resolve(monkeypatch, *, resolve) -> Any:
    """Drive the pre-execution gate with everything before admission stubbed,
    so what the gate does with the record it wrote is what the test reads."""

    async def _passes(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        agent_app_module, "_validate_session_checkpoint_access", _passes
    )
    monkeypatch.setattr(agent_app_module, "_enforce_session_ownership", _passes)
    monkeypatch.setattr(agent_app_module, "_authorize_execution_or_raise", _passes)
    monkeypatch.setattr(agent_app_module, "_resolve_agent_instance", resolve)
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    try:
        return await agent_app_module._authorize_and_resolve(
            execute_request(),
            authenticated_user=person(),
            container=Container(),
            registry={},
            access_token=PERSON_TOKEN,
        )
    finally:
        set_runtime_context(None)


def resolved_target(team_id: str) -> Any:
    definition = _Definition()
    return agent_app_module._ResolvedExecutionTarget(
        definition=definition,
        effective_agent_id=definition.agent_id,
        team_id=team_id,
    )


@pytest.mark.asyncio
async def test_an_admitted_run_keeps_its_record_for_the_turn_to_use(monkeypatch):
    runtime = install_delegation(allowed_callers=[WORKLOAD_CLIENT_ID])

    async def _resolve(**kwargs: Any) -> Any:
        return resolved_target("team-1")

    _, target = await authorize_and_resolve(monkeypatch, resolve=_resolve)

    assert len(runtime.records) == 1
    assert target.credential_provider is not None


@pytest.mark.asyncio
async def test_binding_and_execution_use_the_same_workload_provider(monkeypatch):
    """The person credential ends at local admission."""
    install_delegation(allowed_callers=[WORKLOAD_CLIENT_ID])
    captured: dict[str, Any] = {}

    async def _resolve(**kwargs: Any) -> Any:
        captured["binding"] = kwargs["credentials"]
        return resolved_target("team-1")

    _, target = await authorize_and_resolve(monkeypatch, resolve=_resolve)

    binding = await captured["binding"].credentials()
    assert binding.authorization == "Bearer workload-token"
    assert binding.parameters[GRANT_PARAM_PERSON] == "alice"

    assert target.credential_provider is not None
    turn = await target.credential_provider.credentials()
    assert turn.authorization == "Bearer workload-token"
    assert turn.parameters[GRANT_PARAM_PERSON] == "alice"


@pytest.mark.asyncio
async def test_a_refused_binding_call_leaves_no_record_behind(monkeypatch):
    runtime = install_delegation(allowed_callers=[WORKLOAD_CLIENT_ID])

    async def _refuse(**kwargs: Any) -> Any:
        raise HTTPException(status_code=404, detail="Unknown agent instance.")

    with pytest.raises(HTTPException) as raised:
        await authorize_and_resolve(monkeypatch, resolve=_refuse)

    assert raised.value.status_code == 404
    assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_a_run_resolved_onto_another_team_leaves_no_record_behind(monkeypatch):
    runtime = install_delegation(allowed_callers=[WORKLOAD_CLIENT_ID])

    async def _other_team(**kwargs: Any) -> Any:
        return resolved_target("team-2")

    with pytest.raises(HTTPException) as raised:
        await authorize_and_resolve(monkeypatch, resolve=_other_team)

    assert raised.value.status_code == 403
    assert len(runtime.records) == 0


# ---------------------------------------------------------------------------
# Flag off — unchanged
# ---------------------------------------------------------------------------


def test_with_the_flag_off_admission_hands_the_turn_no_provider():
    """Nothing is put between a client and the person's token: every outbound
    path keeps reading it live off the context, refresh and retry included."""
    set_delegation_runtime(DelegationRuntime(config=DelegationConfig()))
    request = execute_request()

    provider = agent_app_module._admission_credentials(request, person(), Container())

    assert provider is None
    assert request.runtime_context is not None
    assert request.runtime_context.access_token == PERSON_TOKEN


def test_with_no_delegation_installed_at_all_admission_is_unchanged():
    request = execute_request()

    provider = agent_app_module._admission_credentials(request, person(), Container())

    assert provider is None
    assert request.runtime_context is not None
    assert request.runtime_context.access_token == PERSON_TOKEN


class PersonAgentSettings:
    """The identity fields the shared client reads off an agent."""

    id = "agent-a"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class PersonAgentShim:
    """The agent-like object a flag-off client is bound to.

    Modelled on the runtime's own shims: the refresh hook is async, writes the
    new token onto the live runtime context in place, and returns it.
    """

    def __init__(self, token: str) -> None:
        self.runtime_context = RuntimeContext(
            session_id="session-1", user_id="alice", access_token=token
        )
        self.agent_settings: AgentSettingsLike = PersonAgentSettings()
        self.refreshes = 0

    async def refresh_user_access_token(self) -> str:
        self.refreshes += 1
        self.runtime_context.access_token = "refreshed-person-token"
        return "refreshed-person-token"


@pytest.mark.asyncio
async def test_with_the_flag_off_an_expired_token_is_still_refreshed_and_retried():
    """What handing the turn no provider is for: the client keeps the recovery
    it has always had — refresh in place, then retry with what it wrote."""
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    shim = PersonAgentShim("expired-person-token")
    answers = [httpx.Response(401, text="expired"), httpx.Response(200, json={})]
    seen: list[httpx.Request] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answers[len(seen) - 1]

    try:
        credentials = agent_app_module._admission_credentials(
            execute_request(), person(), Container()
        )
        client = KfBaseClient(frozenset({"GET"}), agent=shim, credentials=credentials)
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))

        response = await client._request_with_token_refresh(
            "GET", "/documents", phase_name="test"
        )
    finally:
        set_runtime_context(None)

    assert response.status_code == 200
    assert shim.refreshes == 1
    assert [request.headers["Authorization"] for request in seen] == [
        "Bearer expired-person-token",
        "Bearer refreshed-person-token",
    ]


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


def test_an_empty_allow_list_fails_admission_and_writes_no_record():
    runtime = install_delegation(allowed_callers=None)
    request = execute_request()

    with pytest.raises(HTTPException) as raised:
        agent_app_module._admission_credentials(request, person(), Container())

    assert raised.value.status_code == 503
    assert "allow-list" in str(raised.value.detail)
    assert len(runtime.records) == 0


def test_a_missing_workload_client_fails_admission_and_writes_no_record():
    runtime = install_delegation(allowed_callers=["agent-backend"], token_provider=None)

    with pytest.raises(HTTPException) as raised:
        agent_app_module._admission_credentials(
            execute_request(), person(), Container()
        )

    assert raised.value.status_code == 503
    assert "workload client" in str(raised.value.detail)
    assert len(runtime.records) == 0


def test_a_failed_admission_forwards_no_bearer():
    """The person's credential stays where it was: unused, and never handed to a
    downstream call as a fallback."""
    install_delegation(allowed_callers=None)
    request = execute_request()

    with pytest.raises(HTTPException):
        agent_app_module._admission_credentials(request, person(), Container())

    assert request.runtime_context is not None
    assert request.runtime_context.access_token == PERSON_TOKEN


def test_an_unauthenticated_caller_cannot_be_admitted_under_delegation():
    install_delegation(allowed_callers=["agent-backend"])

    with pytest.raises(HTTPException) as raised:
        agent_app_module._admission_credentials(execute_request(), None, Container())

    assert raised.value.status_code == 503


def test_the_audit_names_only_the_refusal_outcome_and_reason():
    install_delegation(allowed_callers=None)
    container = Container()

    with pytest.raises(HTTPException):
        agent_app_module._admission_credentials(execute_request(), person(), container)

    events = audited(container, "delegation_unavailable")
    assert len(events) == 1
    assert events[0]["outcome"] == "rejected"
    assert events[0]["reason"] == "delegation_unavailable"
    for canary in ("alice", "instance-1", PERSON_TOKEN):
        assert canary not in str(events[0])


# ---------------------------------------------------------------------------
# A person who presented nothing, named by a workload that did
# ---------------------------------------------------------------------------


@pytest.fixture
def calling_workload_bearer(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The bearer a pod verifies before it believes any grant beside it: signed
    by the realm key, issued to the client and service account the pod's
    `security.delegation.caller_policies` names."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", GRANT_ISSUER)
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", GRANT_AUDIENCE)
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", _Jwks(private_key.public_key()))
    monkeypatch.setattr(jwt.api_jwt, "datetime", _FixedDateTime)
    initialize_delegation(
        DelegationConfig(enabled=True, caller_policies=[CALLER_POLICY]),
        issuer=GRANT_ISSUER,
        audience=GRANT_AUDIENCE,
    )
    try:
        yield jwt.encode(
            {
                "sub": CALLING_WORKLOAD_SUBJECT,
                "azp": CALLING_WORKLOAD,
                "iss": GRANT_ISSUER,
                "aud": GRANT_AUDIENCE,
                "typ": "Bearer",
                "iat": _NOW - 30,
                "exp": _NOW + 300,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "synthetic"},
        )
    finally:
        initialize_delegation(DelegationConfig())


def grant(run_id: str = "run-9") -> dict[str, str]:
    """The three parameters a calling workload puts beside its own bearer."""
    return {
        GRANT_PARAM_PERSON: CAMPAIGN_CREATOR,
        GRANT_PARAM_RUN: run_id,
        GRANT_PARAM_AGENT: "instance-1",
    }


def unattended_request() -> RuntimeExecuteRequest:
    """What a calling workload sends: a target and a team, and nothing of the
    person's — no session to continue and no credential to spend."""
    return execute_request(
        session_id=None, runtime_context=RuntimeContext(team_id="team-1")
    )


def admit_through_a_route(
    bearer: str,
    *,
    request: RuntimeExecuteRequest,
    container: Container,
    parameters: dict[str, str],
) -> DelegatedCredentialProvider:
    """Admit one run the way an endpoint does, so the person admission sees is
    the one the receiver resolved from a verified bearer and nothing else."""
    app = FastAPI()
    admitted: list[Any] = []

    @app.post("/agents/execute")
    async def _execute(user=Depends(get_current_user_without_gcu)) -> dict[str, str]:
        admitted.append(
            agent_app_module._admission_credentials(request, user, container)
        )
        return {"outcome": "admitted"}

    with TestClient(app) as client:
        response = client.post(
            "/agents/execute",
            params=parameters,
            headers={"Authorization": f"Bearer {bearer}"},
        )

    assert response.status_code == 200
    provider = admitted[0]
    assert isinstance(provider, DelegatedCredentialProvider)
    return provider


@pytest.mark.asyncio
async def test_a_grant_from_a_configured_workload_admits_the_person_it_names(
    calling_workload_bearer: str,
) -> None:
    """The request carries no session and no credential of the person's, and the
    run is still admitted: the grant beside the caller's bearer is the whole
    input, and what the run calls out with afterwards is the pod's own bearer."""
    runtime = install_delegation(caller_policies=[CALLER_POLICY])

    provider = admit_through_a_route(
        calling_workload_bearer,
        request=unattended_request(),
        container=Container(),
        parameters=grant(),
    )

    record = runtime.records.get(provider.run_id)
    assert record is not None
    assert record.run_id == "run-9"
    assert record.person_id == CAMPAIGN_CREATOR
    assert record.mode == "background"
    assert record.origin_caller == CALLING_WORKLOAD
    assert record.agent_id == "instance-1"
    assert record.team_id == "team-1"
    # No roles either: a person named by a caller cannot reach a role shortcut.
    assert record.roles == ()
    credentials = await provider.credentials()
    assert credentials.authorization == "Bearer workload-token"
    assert credentials.parameters[GRANT_PARAM_PERSON] == CAMPAIGN_CREATOR


def test_a_grant_admission_audit_names_neither_the_person_nor_the_caller(
    calling_workload_bearer: str,
) -> None:
    install_delegation(caller_policies=[CALLER_POLICY])
    container = Container()

    provider = admit_through_a_route(
        calling_workload_bearer,
        request=unattended_request(),
        container=container,
        parameters=grant(),
    )

    events = audited(container, "delegated_run_admitted")
    assert len(events) == 1
    assert events[0]["outcome"] == "accepted"
    assert events[0]["reason"] == "delegated_run_admitted"
    for canary in (
        provider.run_id,
        CAMPAIGN_CREATOR,
        CALLING_WORKLOAD,
        "instance-1",
        "team-1",
        calling_workload_bearer,
    ):
        assert canary not in str(events[0])


@pytest.mark.asyncio
async def test_registration_names_the_origin_workload_under_the_runtimes_bearer(
    calling_workload_bearer: str,
) -> None:
    """Two programs, kept apart from admission to the registry: the run is
    registered under the runtime's own bearer, and the body still names the
    workload whose grant started it."""
    install_delegation(caller_policies=[CALLER_POLICY])
    provider = admit_through_a_route(
        calling_workload_bearer,
        request=unattended_request(),
        container=Container(),
        parameters=grant(),
    )
    sent: list[httpx.Request] = []

    def _receive(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            201,
            json={"run_id": "run-9", "run_ceiling_seconds": 900.0, "binding": None},
        )

    registration = await register_run(
        provider,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_receive)),
        control_plane_url="http://control-plane.invalid",
        agent_instance_id="instance-1",
        agent_id=None,
        run_ceiling_seconds=900.0,
    )

    assert registration.run_id == "run-9"
    body = json.loads(sent[0].content)
    assert body["origin_caller"] == CALLING_WORKLOAD
    assert body["mode"] == "background"
    assert body["agent_instance_id"] == "instance-1"
    assert body["team_id"] == "team-1"
    assert dict(sent[0].url.params) == grant()
    assert sent[0].headers["Authorization"] == "Bearer workload-token"


# ---------------------------------------------------------------------------
# The turn the record admits
# ---------------------------------------------------------------------------


class _NullExecutor:
    async def stream(self, *args: object, **kwargs: object):
        return
        yield  # pragma: no cover - makes this an async generator


class _RecordingRuntime:
    instances: list["_RecordingRuntime"] = []

    def __init__(self, *, definition, services, capability_block) -> None:
        type(self).instances.append(self)

    def bind(self, binding: object) -> None:
        pass

    async def activate(self) -> None:
        pass

    async def get_executor(self) -> _NullExecutor:
        return _NullExecutor()

    async def dispose(self) -> None:
        pass


class _Definition(ReActAgent):
    """A real authored agent: the execution path declares its definitions, and
    every runtime these tests drive is replaced before one is executed."""

    agent_id: str = "rags.sample.echo"
    role: str = "Echo"
    description: str = "Echoes what it is given."
    system_prompt_template: str = "Echo the user briefly."


def delegated_provider(runtime: DelegationRuntime, record: RunRecord):
    runtime.records.put(record)
    return runtime.provider_for(run_id=record.run_id, agent_id=record.agent_id)


async def run_one_turn(
    monkeypatch, *, credential_provider, context: dict, runtime_cls=None, **kwargs
):
    """Drive the turn generator far enough to capture what it binds."""
    bindings: list[Any] = []
    _RecordingRuntime.instances.clear()
    selected = runtime_cls or _RecordingRuntime
    monkeypatch.setattr(agent_app_module, "ReActRuntime", selected)
    monkeypatch.setattr(agent_app_module, "DeepAgentRuntime", selected)
    monkeypatch.setattr(
        agent_app_module,
        "_build_capability_block",
        lambda *args, **kwargs: None,
    )

    def _capture_services(definition, binding, **service_kwargs):
        bindings.append(binding)
        from fred_sdk.contracts.runtime import RuntimeServices

        return RuntimeServices()

    monkeypatch.setattr(agent_app_module, "_build_runtime_services", _capture_services)

    request = agent_app_module._AgentExecuteRequest.model_construct(
        agent_id="rags.sample.echo",
        agent_instance_id=None,
        message="hello",
        context=context,
        resume_payload=None,
        checkpoint_id=None,
        interrupt_id=None,
        invocation_turns=(),
    )
    payloads = [
        payload
        async for payload in agent_app_module._iterate_runtime_event_payloads(
            _Definition(),
            request,
            credential_provider=credential_provider,
            **kwargs,
        )
    ]
    return bindings[0], payloads


@pytest.mark.asyncio
async def test_a_delegated_turn_carries_no_person_token_anywhere_in_its_context(
    monkeypatch,
):
    runtime = install_delegation(allowed_callers=["agent-backend"])
    provider = delegated_provider(
        runtime, RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )

    binding, _ = await run_one_turn(
        monkeypatch,
        credential_provider=provider,
        context={
            "user_id": "alice",
            "access_token": PERSON_TOKEN,
            "refresh_token": "person-refresh-token",
        },
        access_token=PERSON_TOKEN,
    )

    assert binding.runtime_context.access_token is None
    assert binding.runtime_context.refresh_token is None
    assert PERSON_TOKEN not in str(binding.runtime_context.model_dump())


@pytest.mark.asyncio
async def test_a_turn_with_the_flag_off_still_carries_the_persons_token(monkeypatch):
    binding, _ = await run_one_turn(
        monkeypatch,
        credential_provider=None,
        context={"user_id": "alice", "access_token": PERSON_TOKEN},
        access_token=PERSON_TOKEN,
    )

    assert binding.runtime_context.access_token == PERSON_TOKEN


@pytest.mark.asyncio
async def test_the_owning_turn_releases_its_run_record(monkeypatch):
    runtime = install_delegation(allowed_callers=["agent-backend"])
    provider = delegated_provider(
        runtime, RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )

    await run_one_turn(
        monkeypatch,
        credential_provider=provider,
        context={"user_id": "alice"},
        owns_run_record=True,
    )

    assert runtime.records.get("run-7") is None


@pytest.mark.asyncio
async def test_a_child_turn_never_releases_the_run_it_shares(monkeypatch):
    runtime = install_delegation(allowed_callers=["agent-backend"])
    provider = delegated_provider(
        runtime, RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )

    await run_one_turn(
        monkeypatch,
        credential_provider=provider.for_agent("child"),
        context={"user_id": "alice"},
    )

    assert runtime.records.get("run-7") is not None


@pytest.mark.asyncio
async def test_a_run_stopped_by_the_platform_ends_with_a_machine_readable_reason(
    monkeypatch,
):
    """A tool server that cannot be activated under delegation ends the run with
    a reason a client can act on, and a message with nothing upstream in it."""
    runtime = install_delegation(allowed_callers=["agent-backend"])
    provider = delegated_provider(
        runtime, RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )

    class _RefusingRuntime(_RecordingRuntime):
        async def activate(self) -> None:
            raise DelegationUnavailableError(
                "A tool server this agent uses cannot be activated under delegation."
            )

    _, payloads = await run_one_turn(
        monkeypatch,
        credential_provider=provider,
        context={"user_id": "alice"},
        runtime_cls=_RefusingRuntime,
        owns_run_record=True,
    )

    assert payloads[-1]["kind"] == "execution_error"
    assert payloads[-1]["reason"] == "delegation_unavailable"
    # The sentence is the platform's own, and it is the one the engines emit for
    # this reason: a run stopped at activation reads the same as one stopped
    # mid-turn. The refusal's own detail stays off the event entirely.
    assert payloads[-1]["message"] == (
        "This run was stopped because delegated access is unavailable."
    )
    assert (
        payloads[-1]["message"]
        == terminal_stop_event(DelegationUnavailableError()).message
    )
    assert "tool server" not in payloads[-1]["message"]


@pytest.mark.asyncio
async def test_an_ordinary_crash_still_carries_no_reason(monkeypatch):
    class _CrashingRuntime(_RecordingRuntime):
        async def activate(self) -> None:
            raise RuntimeError("something else broke")

    _, payloads = await run_one_turn(
        monkeypatch,
        credential_provider=None,
        context={"user_id": "alice"},
        runtime_cls=_CrashingRuntime,
    )

    assert payloads[-1]["kind"] == "execution_error"
    assert payloads[-1]["reason"] is None


# ---------------------------------------------------------------------------
# Children and team members
# ---------------------------------------------------------------------------


class SpyProvider(OutboundCredentialProvider):
    """A provider whose derived children are recorded, so a fan-out can be read
    back agent by agent."""

    delegated = True

    def __init__(self, run_id: str = "run-7", agent_id: str = "parent") -> None:
        self.run_id = run_id
        self._agent_id = agent_id
        self.children: list["SpyProvider"] = []
        self.bearer = "Bearer workload-token"

    @property
    def agent_id(self) -> str:
        return self._agent_id

    async def credentials(self, *, override_token: str | None = None):
        return OutboundCredentials(
            authorization=self.bearer,
            parameters={
                GRANT_PARAM_PERSON: "alice",
                GRANT_PARAM_RUN: self.run_id,
                GRANT_PARAM_AGENT: self._agent_id,
            },
            delegated=True,
        )

    def for_agent(self, agent_id: str) -> "SpyProvider":
        child = SpyProvider(run_id=self.run_id, agent_id=agent_id)
        child.bearer = self.bearer
        self.children.append(child)
        return child


def invoker(registry: dict[str, Any], provider: OutboundCredentialProvider):
    return agent_app_module.LocalRegistryAgentInvoker(
        registry=registry, access_token=None, credentials=provider
    )


def invocation(agent_id: str) -> AgentInvocationRequest:
    return AgentInvocationRequest(
        agent_id=agent_id,
        message="do your part",
        context=PortableContext(
            request_id="r-1",
            correlation_id="c-1",
            actor="alice",
            tenant="default",
            environment=PortableEnvironment.DEV,
            user_id="alice",
            team_id="team-1",
        ),
    )


@pytest.mark.asyncio
async def test_each_team_member_names_itself_on_the_shared_run(monkeypatch):
    registry = {f"member-{index}": _Definition() for index in range(1, 4)}
    provider = SpyProvider()
    captured: list[Any] = []

    async def _fake_iterate(definition, request, **kwargs):
        captured.append(kwargs["credential_provider"])
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    await asyncio.gather(
        *(
            invoker(registry, provider).invoke(invocation(f"member-{index}"))
            for index in range(1, 4)
        )
    )

    grants = [await child.credentials() for child in captured]
    assert sorted(grant.parameters[GRANT_PARAM_AGENT] for grant in grants) == [
        "member-1",
        "member-2",
        "member-3",
    ]
    assert {grant.parameters[GRANT_PARAM_RUN] for grant in grants} == {"run-7"}
    assert {grant.parameters[GRANT_PARAM_PERSON] for grant in grants} == {"alice"}


@pytest.mark.asyncio
async def test_a_child_is_handed_the_provider_and_not_a_credential(monkeypatch):
    """The parent's provider changes after the child has started; the child's
    next call must carry the change, which a copied string could not."""
    provider = SpyProvider()
    captured: list[Any] = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def _fake_iterate(definition, request, **kwargs):
        child = kwargs["credential_provider"]
        captured.append(child)
        before = await child.credentials()
        started.set()
        await release.wait()
        after = await child.credentials()
        captured.append((before.authorization, after.authorization))
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    running = asyncio.create_task(
        invoker({"member-1": _Definition()}, provider).invoke(invocation("member-1"))
    )
    await started.wait()
    for child in provider.children:
        child.bearer = "Bearer workload-token-2"
    release.set()
    await running

    assert captured[1] == ("Bearer workload-token", "Bearer workload-token-2")


@pytest.mark.asyncio
async def test_cancelling_the_run_cancels_every_member(monkeypatch):
    registry = {f"member-{index}": _Definition() for index in range(1, 4)}
    provider = SpyProvider()
    running = asyncio.Event()
    cancelled: list[str] = []

    async def _fake_iterate(definition, request, **kwargs):
        agent_id = kwargs["credential_provider"].agent_id
        try:
            running.set()
            await asyncio.Event().wait()
            yield {"kind": "final", "content": "unreachable"}
        except asyncio.CancelledError:
            cancelled.append(agent_id)
            raise

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    fan_out = asyncio.gather(
        *(
            invoker(registry, provider).invoke(invocation(f"member-{index}"))
            for index in range(1, 4)
        )
    )
    await running.wait()
    await asyncio.sleep(0)
    fan_out.cancel()
    with pytest.raises(asyncio.CancelledError):
        await fan_out

    assert sorted(cancelled) == ["member-1", "member-2", "member-3"]


@pytest.mark.asyncio
async def test_with_the_flag_off_a_child_gets_no_provider_at_all(monkeypatch):
    captured: list[Any] = []

    async def _fake_iterate(definition, request, **kwargs):
        captured.append(kwargs["credential_provider"])
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    await agent_app_module.LocalRegistryAgentInvoker(
        registry={"member-1": _Definition()}, access_token="person-token"
    ).invoke(invocation("member-1"))

    assert captured == [None]


@pytest.mark.asyncio
async def test_the_run_cancels_an_in_process_child_still_working(monkeypatch):
    """A child that runs inline cannot be cancelled: the run ends while the
    child keeps calling out under an authority the platform has given up."""
    started = asyncio.Event()
    cancelled: list[str] = []

    async def _fake_iterate(definition, request, **kwargs):
        try:
            started.set()
            await asyncio.Event().wait()
            yield {"kind": "final", "content": "unreachable"}
        except asyncio.CancelledError:
            cancelled.append(kwargs["credential_provider"].agent_id)
            raise

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    with RunScope.open(agent_id="parent") as scope:
        running = asyncio.create_task(
            invoker({"member-1": _Definition()}, SpyProvider()).invoke(
                invocation("member-1")
            )
        )
        await started.wait()
        scope.cancel_children()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, timeout=3)

    assert cancelled == ["member-1"]


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("authority_lost", AuthorityLostError),
        ("run_ceiling_reached", RunCeilingReachedError),
        ("cancelled", RunStopError),
        ("delegation_unavailable", DelegationUnavailableError),
    ],
)
@pytest.mark.asyncio
async def test_a_stopped_child_ends_the_parent_on_the_same_reason(
    monkeypatch, reason, expected
):
    """The parent ends typed, on the child's reason — the child's own sentence
    is never handed back as though it were an answer."""

    async def _fake_iterate(definition, request, **kwargs):
        yield {
            "kind": "execution_error",
            "message": "the child's own sentence",
            "reason": reason,
        }

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    with pytest.raises(RunStopError) as raised:
        await invoker({"member-1": _Definition()}, SpyProvider()).invoke(
            invocation("member-1")
        )

    assert type(raised.value) is expected
    assert raised.value.reason == reason
    assert "the child's own sentence" not in str(raised.value)


@pytest.mark.asyncio
async def test_a_child_failing_on_its_own_is_still_an_error_result(monkeypatch):
    """Only a platform stop ends the parent; an ordinary child failure is still
    something the caller reports back to its model."""

    async def _fake_iterate(definition, request, **kwargs):
        yield {"kind": "execution_error", "message": "the child could not answer"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    result = await invoker({"member-1": _Definition()}, SpyProvider()).invoke(
        invocation("member-1")
    )

    assert result.is_error is True
    assert result.content == "the child could not answer"


@pytest.mark.asyncio
async def test_the_run_bounds_how_many_children_run_at_once(monkeypatch):
    """The bound is the deployment's, not the model's: a turn that asks for
    three children at once still runs no more than the configured two."""
    registry = {f"member-{index}": _Definition() for index in range(1, 4)}
    provider = SpyProvider()
    running: list[str] = []
    release = asyncio.Event()

    async def _fake_iterate(definition, request, **kwargs):
        running.append(kwargs["credential_provider"].agent_id)
        await release.wait()
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    async def _wait_for(count: int) -> None:
        for _ in range(200):
            if len(running) >= count:
                return
            await asyncio.sleep(0)
        raise AssertionError(f"only {len(running)} children ever started")

    configure_run_limits(wall_clock_seconds=60.0, max_concurrent_children=2)
    try:
        with RunScope.open(agent_id="parent"):
            fan_out = asyncio.gather(
                *(
                    invoker(registry, provider).invoke(invocation(f"member-{index}"))
                    for index in range(1, 4)
                )
            )
            await _wait_for(2)
            for _ in range(20):
                await asyncio.sleep(0)

            assert len(running) == 2

            release.set()
            await fan_out
    finally:
        configure_run_limits()

    assert sorted(running) == ["member-1", "member-2", "member-3"]


@pytest.mark.asyncio
async def test_a_failure_of_its_own_never_repeats_the_grant(monkeypatch, caplog):
    """An ordinary crash reaches the client as an event: whatever it says about
    the request it failed on, the person it named is not part of it."""

    class _CrashingRuntime(_RecordingRuntime):
        async def activate(self) -> None:
            raise RuntimeError(
                "Server error '500' for url "
                "'http://kf.invalid/documents?person=alice&run=run-7&agent=agent-a'"
            )

    runtime = install_delegation(allowed_callers=["agent-backend"])
    provider = delegated_provider(
        runtime, RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )
    with caplog.at_level(logging.DEBUG, logger=agent_app_module.__name__):
        _, payloads = await run_one_turn(
            monkeypatch,
            credential_provider=provider,
            context={"user_id": "alice"},
            runtime_cls=_CrashingRuntime,
        )

    assert payloads[-1]["kind"] == "execution_error"
    assert payloads[-1]["message"] == "Execution failed."
    assert "person=alice" not in payloads[-1]["message"]
    assert "run-7" not in payloads[-1]["message"]
    emitted = repr([record.__dict__ for record in caplog.records])
    for canary in ("alice", "run-7", "agent-a", "kf.invalid/documents"):
        assert canary not in emitted
