# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared resolver admission cases using the real delegated credential contract."""

import asyncio
from dataclasses import dataclass

import httpx
import pytest
from conftest import MockIdentityProvider
from fastapi import HTTPException
from fred_core.security.delegation import DelegationConfig
from fred_runtime.app import agent_app
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationRuntime,
    RunRecord,
)
from fred_runtime.runtime_context import RuntimeConfig, RuntimeContext
from fred_runtime.runtime_support.authority import DelegationUnavailableError
from fred_sdk.authoring import ReActAgent
from fred_sdk.contracts.weaver import WeaverRuntimeBinding
from weaver_fixtures import resolved_binding

pytestmark = pytest.mark.asyncio


class _Template(ReActAgent):
    agent_id: str = "template"
    role: str = "Assistant"
    description: str = "Example"
    system_prompt_template: str = "Answer the question."


@dataclass
class _Admission:
    binding: WeaverRuntimeBinding
    identity: MockIdentityProvider
    delegation: DelegationRuntime
    provider: DelegatedCredentialProvider
    request: agent_app._AgentExecuteRequest

    async def resolve(self, client: httpx.AsyncClient):
        return await agent_app._resolve_agent_instance(
            request=self.request,
            registry={"template": _Template()},
            access_token="person-token-must-not-be-forwarded",
            control_plane_url="https://cp.invalid/api",
            http_client=client,
            credentials=self.provider,
        )


@pytest.fixture
def admission(monkeypatch: pytest.MonkeyPatch) -> _Admission:
    binding = resolved_binding()
    identity = MockIdentityProvider(monkeypatch, "synthetic-workload-token")
    delegation = DelegationRuntime(
        config=DelegationConfig(act_for_people=True), token_provider=identity.provider
    )
    delegation.records.admit(
        RunRecord(
            run_id="run",
            person_id=binding.subject_id,
            agent_id=str(binding.agent.instance_id),
        )
    )
    provider = DelegatedCredentialProvider(
        runtime=delegation, run_id="run", agent_id=str(binding.agent.instance_id)
    )
    context = RuntimeContext(
        RuntimeConfig(knowledge_flow_url="https://kf.invalid", service_name="pod")
    )
    monkeypatch.setattr(agent_app, "get_runtime_context", lambda: context)
    request = agent_app._AgentExecuteRequest(
        agent_instance_id=str(binding.agent.instance_id),
        message="Hello",
        context={"user_id": binding.subject_id, "space_id": str(binding.space.id)},
    )
    return _Admission(binding, identity, delegation, provider, request)


@pytest.mark.parametrize("status", [200, 401, 403, 404, 500, 503])
async def test_resolver_uses_workload_lease_and_grant_once(
    admission: _Admission, status: int
) -> None:
    # This is the real provider's contract: the grant has no Authorization.
    grant = await admission.provider.credentials()
    assert grant.authorization is None
    assert grant.delegated
    requests: list[httpx.Request] = []

    def resolver(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=admission.binding.model_dump(mode="json"))

    # A client default must not replace the service bearer or trigger another send.
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(resolver),
        auth=httpx.BasicAuth("unused", "unused"),
    ) as client:
        if status == 200:
            target = await admission.resolve(client)
            assert target.effective_agent_id == str(admission.binding.agent.instance_id)
            assert admission.request._turn_authority is not None
            assert admission.request._turn_authority.binding == admission.binding
        else:
            with pytest.raises(HTTPException) as error:
                await admission.resolve(client)
            assert error.value.status_code == (
                403 if status in (401, 403, 404) else 503
            )
            assert admission.request._turn_authority is None

    assert len(requests) == 1
    sent = requests[0]
    assert sent.headers["Authorization"] == "Bearer synthetic-workload-token"
    assert dict(sent.url.params) == {
        "person": admission.binding.subject_id,
        "run": "run",
        "agent": str(admission.binding.agent.instance_id),
    }
    assert sent.url.path == (
        f"/api/spaces/{admission.binding.space.id}"
        f"/agent-instances/{admission.binding.agent.instance_id}/runtime"
    )
    assert admission.identity.issued == ["synthetic-workload-token"]
    assert admission.identity.acquisitions == 1
    assert "person-token-must-not-be-forwarded" not in str(sent.headers)


@pytest.mark.parametrize("state", ["terminal", "discarded", "token_unavailable"])
async def test_no_resolver_or_person_fallback_without_live_workload_credential(
    admission: _Admission, state: str
) -> None:
    if state == "terminal":
        admission.delegation.records.mark_terminal("run")
    elif state == "discarded":
        admission.delegation.records.discard("run")
    else:
        admission.identity.failure = "unreachable"

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail("A failed delegated credential must not reach the resolver")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(DelegationUnavailableError):
            await admission.resolve(client)
    assert admission.request._turn_authority is None
    assert not admission.identity.issued


async def test_termination_during_token_acquisition_blocks_resolver(
    admission: _Admission, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquire = admission.identity.provider.get_token_lease

    async def acquire_then_end():
        lease = await acquire()
        admission.delegation.records.mark_terminal("run")
        return lease

    monkeypatch.setattr(
        admission.identity.provider, "get_token_lease", acquire_then_end
    )

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail("A terminated run must not use its newly acquired token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(DelegationUnavailableError):
            await admission.resolve(client)
    assert admission.identity.issued == ["synthetic-workload-token"]
    assert admission.request._turn_authority is None


async def test_termination_during_resolution_cannot_create_turn_authority(
    admission: _Admission,
) -> None:
    requests: list[httpx.Request] = []

    def resolver(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        admission.delegation.records.mark_terminal("run")
        return httpx.Response(200, json=admission.binding.model_dump(mode="json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(resolver)) as client:
        with pytest.raises(DelegationUnavailableError):
            await admission.resolve(client)
    assert len(requests) == 1
    assert admission.request._turn_authority is None


@pytest.mark.parametrize("mismatch", ["person", "agent"])
async def test_delegation_assertions_must_match_before_acquiring_token(
    admission: _Admission, mismatch: str
) -> None:
    if mismatch == "person":
        assert admission.request.context is not None
        admission.request.context["user_id"] = "another-person"
    else:
        admission.provider = admission.provider.for_agent("another-agent")

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail("Mismatched assertions must not reach the resolver")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(HTTPException) as error:
            await admission.resolve(client)
    assert error.value.status_code == 403
    assert not admission.identity.issued
    assert admission.request._turn_authority is None


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_resolver_reuses_one_client_and_keeps_request_headers_isolated(
    admission, concurrent
):

    calls = []

    async def respond(request):
        calls.append(request)
        await asyncio.sleep(0)
        return httpx.Response(200, json=admission.binding.model_dump(mode="json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

        async def resolve(index):
            return await agent_app._resolve_agent_instance(
                request=admission.request.model_copy(),
                registry={"template": _Template()},
                access_token=f"person-token-{index}",
                control_plane_url="https://cp.invalid/api",
                http_client=client,
                credentials=admission.provider,
                request_id=f"request-{index}",
            )

        if concurrent:
            results = await asyncio.gather(*(resolve(i) for i in range(10)))
        else:
            results = [await resolve(i) for i in range(10)]
        assert len(results) == 10
        assert "Authorization" not in client.headers
    assert len(calls) == 10
    assert {r.headers["X-Request-Id"] for r in calls} == {
        f"request-{i}" for i in range(10)
    }
    assert {r.headers["Authorization"] for r in calls} == {
        "Bearer synthetic-workload-token"
    }


@pytest.mark.parametrize("mode", ["message", "continue", "hitl"])
async def test_configuration_conflict_is_preserved_before_execution(
    admission: _Admission, mode: str
) -> None:
    assert admission.request.context is not None
    admission.request.context["session_id"] = "conversation"
    if mode == "continue":
        admission.request.interrupted_action = "continue"
        admission.request.interruption_id = "interruption"
    elif mode == "hitl":
        admission.request.resume_payload = {"answer": "yes"}
    calls: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            409, json={"code": "agent_configuration_changed", "detail": "Changed"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        with pytest.raises(HTTPException) as error:
            await admission.resolve(client)
    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": "agent_configuration_changed",
        "message": "This agent has changed since this conversation started. Start a new conversation to use its new configuration.",
    }
    assert len(calls) == 1
    assert calls[0].url.params["conversation"] == "conversation"
    assert admission.request._turn_authority is None
