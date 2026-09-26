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
import logging
import threading
import time
from collections import deque
from collections.abc import Iterator, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from conftest import StaticWorkloadTokens, install_delegation_runtime
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security import oidc
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    DelegationConfig,
    initialize_delegation,
    preserved_delegation,
)
from fred_core.security.oidc import get_current_user_without_gcu
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.common import mcp_utils
from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationRuntime,
    OutboundCredentialProvider,
    OutboundCredentials,
    RunRecord,
    set_delegation_runtime,
)
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
    RunStopError,
)
from fred_runtime.runtime_support.run_scope import RunScope, terminal_stop_event
from fred_sdk.authoring import ReActAgent
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import AgentTuning, MCPServerConfiguration, MCPServerRef
from test_agent_app import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    _build_test_config,
    _EchoAgent,
)
from test_delegation_receiver_integration import _NOW, _FixedDateTime, _Jwks

PERSON_TOKEN = "person-bearer-token"
# The workload that asks this pod to run for someone it names, trusted through
# the delegation caller role on its token — never the pod's client.
CALLING_WORKLOAD = "campaign-worker"
CALLING_WORKLOAD_SUBJECT = "campaign-worker-service-account"
CAMPAIGN_CREATOR = "creator-1"
GRANT_ISSUER = "https://id.invalid/realms/fred"
GRANT_AUDIENCE = "fred-delegation"
# The pod's own login client: deliberately not the delegation audience.
LOGIN_CLIENT = "app"


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
    # Pods built here install a process-wide runtime context; later modules must not see it.
    set_runtime_context(None)


def install_delegation(*, token_provider: Any = "default") -> DelegationRuntime:
    return install_delegation_runtime(
        StaticWorkloadTokens() if token_provider == "default" else token_provider
    )


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


def test_admission_drops_the_persons_credential_once_the_record_exists():
    install_delegation()
    request = execute_request()

    agent_app_module._admission_credentials(request, person(), Container())

    assert request.runtime_context is not None
    assert request.runtime_context.access_token is None
    assert request.runtime_context.refresh_token is None
    assert request.runtime_context.access_token_expires_at is None


@pytest.mark.asyncio
async def test_the_grant_that_follows_admission_names_the_admitted_person():
    runtime = install_delegation()
    request = execute_request()

    provider = agent_app_module._admission_credentials(request, person(), Container())

    assert isinstance(provider, DelegatedCredentialProvider)
    record = runtime.records.get(provider.run_id)
    assert record is not None
    credentials = await provider.credentials()
    assert credentials.parameters[GRANT_PARAM_RUN] == record.run_id
    assert credentials.parameters[GRANT_PARAM_PERSON] == record.person_id == "alice"
    assert credentials.parameters[GRANT_PARAM_AGENT] == "instance-1"
    assert credentials.authorization == "Bearer workload-token"


@pytest.mark.asyncio
async def test_a_long_run_keeps_its_grant_after_the_pod_admits_another(monkeypatch):
    """A run has no time limit: an hour on, and after the same pod has admitted
    another run, its outbound calls still carry its grant."""
    install_delegation()
    clock = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    long_run = agent_app_module._admission_credentials(
        execute_request(), person(), Container()
    )
    assert isinstance(long_run, DelegatedCredentialProvider)

    clock[0] += 3600.0
    agent_app_module._admission_credentials(
        execute_request(session_id="session-2"), person("bob"), Container()
    )
    credentials = await long_run.credentials()

    assert credentials.authorization == "Bearer workload-token"
    assert credentials.parameters[GRANT_PARAM_PERSON] == "alice"
    assert credentials.parameters[GRANT_PARAM_RUN] == long_run.run_id


def test_admission_audit_keeps_identifiers_only_in_the_run_record():
    install_delegation()
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
        "alice",
        "team-1",
        "instance-1",
        PERSON_TOKEN,
    ):
        assert canary not in str(events[0])


# ---------------------------------------------------------------------------
# A run that never starts leaves nothing behind
# ---------------------------------------------------------------------------


async def authorize_and_resolve(
    monkeypatch,
    *,
    resolve,
    user: KeycloakUser | None = None,
    access_token: str = PERSON_TOKEN,
) -> Any:
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
            authenticated_user=user or person(),
            container=Container(),
            registry={},
            access_token=access_token,
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
    runtime = install_delegation()

    async def _resolve(**kwargs: Any) -> Any:
        return resolved_target("team-1")

    _, target = await authorize_and_resolve(monkeypatch, resolve=_resolve)

    assert len(runtime.records) == 1
    assert target.credential_provider is not None


@pytest.mark.asyncio
async def test_binding_and_execution_use_the_same_workload_provider(monkeypatch):
    """The person credential ends at local admission."""
    install_delegation()
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
    runtime = install_delegation()

    async def _refuse(**kwargs: Any) -> Any:
        raise HTTPException(status_code=404, detail="Unknown agent instance.")

    with pytest.raises(HTTPException) as raised:
        await authorize_and_resolve(monkeypatch, resolve=_refuse)

    assert raised.value.status_code == 404
    assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_a_run_resolved_onto_another_team_leaves_no_record_behind(monkeypatch):
    runtime = install_delegation()

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
    shim.runtime_context.access_token_expires_at = 0
    answers = [httpx.Response(401, text="expired"), httpx.Response(200, json={})]
    seen: list[str] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
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
    assert seen == [
        "Bearer expired-person-token",
        "Bearer refreshed-person-token",
    ]


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


def test_a_missing_workload_client_fails_admission_and_writes_no_record():
    runtime = install_delegation(token_provider=None)

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
    install_delegation(token_provider=None)
    request = execute_request()

    with pytest.raises(HTTPException):
        agent_app_module._admission_credentials(request, person(), Container())

    assert request.runtime_context is not None
    assert request.runtime_context.access_token == PERSON_TOKEN


def test_an_unauthenticated_caller_cannot_be_admitted_under_delegation():
    install_delegation()

    with pytest.raises(HTTPException) as raised:
        agent_app_module._admission_credentials(execute_request(), None, Container())

    assert raised.value.status_code == 503


def test_the_audit_names_only_the_refusal_outcome_and_reason():
    install_delegation(token_provider=None)
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
# A service identity names no person
# ---------------------------------------------------------------------------

EVALUATOR_TOKEN = "evaluator-bearer-token"


def evaluator() -> KeycloakUser:
    return KeycloakUser(
        uid="evaluator-account",
        username="evaluator-account",
        roles=["service_agent"],
        client_id="evaluation",
    )


@pytest.mark.asyncio
async def test_a_service_identity_runs_on_its_own_bearer_under_delegation(
    monkeypatch,
):
    """Admission hands it no provider, so every outbound call, a tool server
    declared `delegated` included, carries its own bearer and no grant."""
    runtime = install_delegation()
    container = Container()
    request = execute_request(
        runtime_context=RuntimeContext(team_id="team-1", access_token=EVALUATOR_TOKEN)
    )
    captured: dict[str, Any] = {}

    class _FakeMultiServerClient:
        def __init__(self, conns, tool_interceptors=None) -> None:
            captured.update(conns)

        async def get_tools(self, server_name: str):
            return []

    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", _FakeMultiServerClient)

    provider = agent_app_module._admission_credentials(request, evaluator(), container)
    assert request.runtime_context is not None
    await mcp_utils.get_connected_mcp_client_for_agent(
        agent_id="agent-a",
        mcp_servers=[
            MCPServerConfiguration.model_validate(
                {
                    "id": "kf-mcp",
                    "name": "kf",
                    "transport": "streamable_http",
                    "url": "http://kf.invalid/mcp",
                    "enabled": True,
                    "auth_mode": "delegated",
                }
            )
        ],
        runtime_context=request.runtime_context,
        credentials=provider,
    )

    assert provider is None
    assert request.runtime_context.access_token == EVALUATOR_TOKEN
    assert len(runtime.records) == 0
    assert audited(container, "delegated_run_admitted") == []
    assert captured["kf-mcp"]["headers"]["Authorization"] == f"Bearer {EVALUATOR_TOKEN}"
    assert captured["kf-mcp"]["url"] == "http://kf.invalid/mcp"


@pytest.mark.asyncio
async def test_a_service_identitys_binding_call_carries_its_own_bearer(monkeypatch):
    runtime = install_delegation()
    captured: dict[str, Any] = {}

    async def _resolve(**kwargs: Any) -> Any:
        captured["binding"] = kwargs["credentials"]
        return resolved_target("team-1")

    _, target = await authorize_and_resolve(
        monkeypatch, resolve=_resolve, user=evaluator(), access_token=EVALUATOR_TOKEN
    )

    binding = await captured["binding"].credentials()
    assert binding.authorization == f"Bearer {EVALUATOR_TOKEN}"
    assert binding.parameters == {}
    assert target.credential_provider is None
    assert len(runtime.records) == 0


def test_a_service_identity_holding_the_caller_role_is_refused():
    """The delegation client holds the service role too: without a person it
    is refused, never run as the service identity it also is."""
    runtime = install_delegation()
    workload = evaluator().model_copy(
        update={"caller_roles": frozenset({"delegation_caller"})}
    )

    with preserved_delegation():
        initialize_delegation(DelegationConfig(act_for_people=True))
        with pytest.raises(HTTPException) as raised:
            agent_app_module._admission_credentials(
                execute_request(), workload, Container()
            )

    assert raised.value.status_code == 403
    assert raised.value.detail == "delegated_person_required"
    assert len(runtime.records) == 0


# ---------------------------------------------------------------------------
# A person who presented nothing, named by a workload that did
# ---------------------------------------------------------------------------


@pytest.fixture
def realm_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    """The realm key a pod verifies every bearer against, strict on issuer and
    audience."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", GRANT_ISSUER)
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({GRANT_ISSUER}))
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", LOGIN_CLIENT)
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", _Jwks(private_key.public_key()))
    monkeypatch.setattr(jwt.api_jwt, "datetime", _FixedDateTime)
    return private_key


def workload_bearer(
    private_key: rsa.RSAPrivateKey, *, audience: str | list[str] = GRANT_AUDIENCE
) -> str:
    """A calling workload's bearer, signed by the realm key and carrying the
    delegation caller role."""
    return jwt.encode(
        {
            "sub": CALLING_WORKLOAD_SUBJECT,
            "azp": CALLING_WORKLOAD,
            "iss": GRANT_ISSUER,
            "aud": audience,
            "typ": "Bearer",
            "resource_access": {GRANT_AUDIENCE: {"roles": ["delegation_caller"]}},
            "iat": _NOW - 30,
            "exp": _NOW + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "synthetic"},
    )


@pytest.fixture
def calling_workload_bearer(realm_key: rsa.RSAPrivateKey) -> Iterator[str]:
    """The bearer a pod verifies before it believes any grant beside it: signed
    by the realm key, addressed to the delegation audience and carrying the
    delegation caller role."""
    initialize_delegation(
        DelegationConfig(act_for_people=True, accept_delegated_calls=True),
        issuers=[GRANT_ISSUER],
        user_clients=[LOGIN_CLIENT],
    )
    try:
        yield workload_bearer(realm_key)
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
    runtime = install_delegation()

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
    assert record.agent_id == "instance-1"
    credentials = await provider.credentials()
    assert credentials.authorization == "Bearer workload-token"
    assert credentials.parameters[GRANT_PARAM_PERSON] == CAMPAIGN_CREATOR


def test_a_grant_admission_audit_names_neither_the_person_nor_the_caller(
    calling_workload_bearer: str,
) -> None:
    install_delegation()
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


# ---------------------------------------------------------------------------
# Resolving the target: the binding lookup is the only control-plane call
# ---------------------------------------------------------------------------


def managed_binding(definition: ReActAgent) -> dict:
    return {
        "agent_instance_id": "instance-1",
        "template_agent_id": definition.agent_id,
        "owner_scope": "team",
        "owner_team_id": "team-1",
        "tuning": {
            "role": definition.role,
            "description": definition.description,
        },
    }


@pytest.mark.asyncio
async def test_a_delegated_managed_run_resolves_its_binding_with_one_grant_get():
    """The read-only lookup carries the workload bearer and the grant."""
    runtime = install_delegation()
    definition = _Definition()
    provider = delegated_provider(
        runtime,
        RunRecord(run_id="run-9", person_id="alice", agent_id="instance-1"),
    )
    sent: list[httpx.Request] = []

    def _control_plane(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=managed_binding(definition))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_control_plane)
    ) as client:
        target = await agent_app_module._resolve_agent_instance(
            request=agent_app_module._AgentExecuteRequest(
                agent_instance_id="instance-1", message="hello"
            ),
            registry={definition.agent_id: definition},
            access_token=None,
            control_plane_url="http://control-plane.invalid/control-plane/v1",
            http_client=client,
            team_id="team-1",
            credentials=provider,
        )

    assert [(request.method, request.url.path) for request in sent] == [
        ("GET", "/control-plane/v1/teams/team-1/agent-instances/instance-1/runtime")
    ]
    assert dict(sent[0].url.params) == {
        GRANT_PARAM_PERSON: "alice",
        GRANT_PARAM_RUN: "run-9",
        GRANT_PARAM_AGENT: "instance-1",
    }
    assert sent[0].headers["Authorization"] == "Bearer workload-token"
    assert target.effective_agent_id == "instance-1"


@pytest.mark.asyncio
async def test_a_delegated_direct_run_makes_no_control_plane_call():
    runtime = install_delegation()
    definition = _Definition()
    provider = delegated_provider(
        runtime,
        RunRecord(run_id="run-9", person_id="alice", agent_id=definition.agent_id),
    )
    sent: list[httpx.Request] = []

    def _control_plane(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_control_plane)
    ) as client:
        target = await agent_app_module._resolve_agent_instance(
            request=agent_app_module._AgentExecuteRequest(
                agent_id=definition.agent_id, message="hello"
            ),
            registry={definition.agent_id: definition},
            access_token=None,
            control_plane_url="http://control-plane.invalid/control-plane/v1",
            http_client=client,
            credentials=provider,
        )

    assert sent == []
    assert target.effective_agent_id == definition.agent_id


def test_a_role_holder_naming_nobody_is_refused_where_grants_are_not_believed(
    realm_key: rsa.RSAPrivateKey,
) -> None:
    """A pod that acts for people but believes no grant still reads the caller
    role off a verified bearer, so a workload naming nobody cannot run as itself."""
    runtime = install_delegation()
    container = Container()
    app = FastAPI()

    @app.post("/agents/execute")
    async def _execute(user=Depends(get_current_user_without_gcu)) -> dict[str, str]:
        agent_app_module._admission_credentials(unattended_request(), user, container)
        return {"outcome": "admitted"}

    # Also addressed to the pod's own client: the delegation audience alone is
    # accepted only where grants are believed.
    bearer = workload_bearer(realm_key, audience=[LOGIN_CLIENT, GRANT_AUDIENCE])
    with preserved_delegation():
        initialize_delegation(
            DelegationConfig(act_for_people=True),
            issuers=[GRANT_ISSUER],
            user_clients=[LOGIN_CLIENT],
        )
        with TestClient(app) as client:
            response = client.post(
                "/agents/execute", headers={"Authorization": f"Bearer {bearer}"}
            )

    assert response.status_code == 403
    assert response.json()["detail"] == "delegated_person_required"
    assert len(runtime.records) == 0


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
    runtime.records.admit(record)
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
    monkeypatch.setattr(
        agent_app_module, "_build_conversation_filesystem", lambda _: None
    )

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
    runtime = install_delegation()
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
    runtime = install_delegation()
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
    runtime = install_delegation()
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
    runtime = install_delegation()
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
async def test_with_the_flag_off_a_child_reads_the_updated_person_bearer(
    monkeypatch, tmp_path
):
    captured: list[OutboundCredentials] = []
    runtime_context = RuntimeContext(
        session_id="synthetic-session",
        user_id="synthetic-person",
        team_id="synthetic-team",
        access_token="person-token-1",
    )
    binding = BoundRuntimeContext(
        runtime_context=runtime_context,
        portable_context=invocation("member-1").context,
    )

    async def _fake_iterate(definition, request, **kwargs):
        captured.append(await kwargs["credential_provider"].credentials())
        yield {"kind": "final", "content": "done"}

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads", _fake_iterate
    )

    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(ToolFriendlyFakeChatModel(responses=[])),
    )
    definition = _EchoAgent()
    app = agent_app_module.create_agent_app(
        registry={"member-1": definition}, config=_build_test_config(tmp_path)
    )
    with TestClient(app):
        services = agent_app_module._build_runtime_services(
            definition,
            binding,
            team_id="synthetic-team",
            registry={"member-1": definition},
            access_token="person-token-1",
        )
        assert services.agent_invoker is not None
        await services.agent_invoker.invoke(invocation("member-1"))
        runtime_context.access_token = "person-token-2"
        await services.agent_invoker.invoke(invocation("member-1"))

    assert [item.authorization for item in captured] == [
        "Bearer person-token-1",
        "Bearer person-token-2",
    ]
    assert all(item.parameters == {} for item in captured)


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

    with RunScope.open() as scope:
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
async def test_a_run_starts_as_many_children_at_once_as_its_turn_asks_for(
    monkeypatch,
):
    """No child is refused or held back for being one too many: twelve
    members asked for at once all run at once."""
    members = 12
    registry = {f"member-{index}": _Definition() for index in range(1, members + 1)}
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

    with RunScope.open():
        fan_out = asyncio.gather(
            *(
                invoker(registry, provider).invoke(invocation(f"member-{index}"))
                for index in range(1, members + 1)
            )
        )
        for _ in range(200):
            if len(running) == members:
                break
            await asyncio.sleep(0)

        assert len(running) == members

        release.set()
        results = await asyncio.wait_for(fan_out, timeout=3)

    assert [result.is_error for result in results] == [False] * members


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

    runtime = install_delegation()
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
    assert "could not initialize" in payloads[-1]["message"]
    assert "Contact support with reference" in payloads[-1]["message"]
    reference = payloads[-1]["message"].split("reference ")[1].rstrip(".")
    assert reference in caplog.text
    assert "RuntimeError" in caplog.text
    assert "activate" in caplog.text
    assert "person=alice" not in payloads[-1]["message"]
    assert "run-7" not in payloads[-1]["message"]
    emitted = repr([record.__dict__ for record in caplog.records])
    for canary in ("alice", "run-7", "agent-a", "kf.invalid/documents"):
        assert canary not in emitted


# ---------------------------------------------------------------------------
# Routes that serve only the person's own credential
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_security() -> Iterator[None]:
    enabled = oidc.KEYCLOAK_ENABLED
    yield
    oidc.KEYCLOAK_ENABLED = enabled
    initialize_delegation(DelegationConfig())
    set_delegation_runtime(None)


def _own_credential_app(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(ToolFriendlyFakeChatModel(responses=[])),
    )
    monkeypatch.setattr(
        oidc,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="owner-a" if token == "owner-token" else "workload-subject",
            username="synthetic",
            roles=[] if token == "owner-token" else ["service_agent"],
            client_id="browser" if token == "owner-token" else "runtime-client",
            token_issuer="https://issuer.test/realms/fred",
            token_audiences=frozenset({"fred-delegation"}),
            token_type="Bearer",
            caller_roles=(
                frozenset()
                if token == "owner-token"
                else frozenset({"delegation_caller"})
            ),
        ),
    )
    monkeypatch.setattr(
        agent_app_module,
        "rebac_factory",
        lambda *args, **kwargs: SimpleNamespace(
            enforces_standing=True,
            enabled=True,
            validate_standing_model=AsyncMock(),
            is_standing_seed_ready=AsyncMock(return_value=True),
            require_user_standing=AsyncMock(),
        ),
    )
    app = agent_app_module.create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(
            tmp_path,
            user_security_enabled=True,
            act_for_people=True,
            accept_delegated_calls=True,
        ),
    )
    install_delegation_runtime(StaticWorkloadTokens())
    monkeypatch.setattr(agent_app_module, "_authorize_execution_or_raise", AsyncMock())
    return app


def _enable_workload_delegation() -> None:
    initialize_delegation(
        DelegationConfig(act_for_people=True, accept_delegated_calls=True),
        issuers=["https://issuer.test/realms/fred"],
        user_clients=["browser"],
    )


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/pod/v1/agents/sessions", {}),
        ("GET", "/pod/v1/agents/sessions/session-a/messages", {}),
        ("DELETE", "/pod/v1/agents/sessions/session-a", {}),
        ("GET", "/pod/v1/agents/checkpoints", {}),
        ("GET", "/pod/v1/agents/checkpoints/session-a", {}),
        ("DELETE", "/pod/v1/agents/checkpoints/session-a", {}),
        ("GET", "/pod/v1/agents/kpi-turns", {}),
        ("GET", "/pod/v1/agents/audit-events", {}),
        (
            "POST",
            "/pod/v1/agents/capabilities/demo_echo/validate-config",
            {"data": {"config": "{}"}},
        ),
        (
            "POST",
            "/pod/v1/agents/capabilities/chat-controls",
            {"json": {"items": []}},
        ),
        (
            "POST",
            "/v1/chat/completions",
            {
                "json": {
                    "model": "rags.sample.echo",
                    "messages": [{"role": "user", "content": "hello"}],
                }
            },
        ),
    ],
)
def test_retained_own_credential_routes_reject_asserted_subject(
    monkeypatch,
    tmp_path,
    _restore_security,
    method: str,
    path: str,
    request_kwargs: dict,
) -> None:
    app = _own_credential_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        _enable_workload_delegation()
        response = client.request(
            method,
            path,
            params={"person": "owner-a", "run": "run-a", "agent": "rags.sample.echo"},
            headers={"Authorization": "Bearer workload-token"},
            **request_kwargs,
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "requires_own_credential"
