from __future__ import annotations

import json

import httpx
import pytest
from fred_core.security.backend_to_backend_auth import M2MTokenProvider
from fred_core.security.delegation import DelegationConfig
from fred_runtime.app.agent_app import _AgentExecuteRequest, _resolve_agent_instance
from fred_runtime.common.kf_vectorsearch_client import _with_transient_retry
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationRuntime,
    RunRecord,
)
from fred_runtime.common.run_lifecycle import register_run, report_run_end
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.authoring import ReActAgent


class _RegistrationAgent(ReActAgent):
    agent_id: str = "synthetic.registration"
    role: str = "Synthetic registration agent"
    description: str = "Exercises managed run registration."
    system_prompt_template: str = "Answer briefly."


class _Tokens(M2MTokenProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def get_token(self) -> str:
        self.calls += 1
        return f"workload-{self.calls}"


def _provider(tokens: _Tokens) -> DelegatedCredentialProvider:
    runtime = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime"]),
        token_provider=tokens,
    )
    runtime.records.put(
        RunRecord(
            run_id="run-a",
            person_id="person-a",
            agent_id="agent-a",
            team_id="team-a",
        )
    )
    provider = runtime.provider_for(run_id="run-a", agent_id="agent-a")
    assert isinstance(provider, DelegatedCredentialProvider)
    return provider


@pytest.mark.asyncio
async def test_registration_uses_workload_only_and_receiver_ceiling() -> None:
    tokens = _Tokens()
    provider = _provider(tokens)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"run_id": "run-a", "run_ceiling_seconds": 37.0, "binding": {}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        receipt = await register_run(
            provider,
            http_client=client,
            control_plane_url="http://control-plane.test",
            agent_instance_id="instance-a",
            agent_id=None,
            run_ceiling_seconds=60.0,
        )

    assert receipt.run_ceiling_seconds == 37.0
    assert seen[0].headers["authorization"] == "Bearer workload-1"
    assert "person-a" not in seen[0].headers["authorization"]
    assert dict(seen[0].url.params) == {
        "person": "person-a",
        "run": "run-a",
        "agent": "agent-a",
    }


@pytest.mark.asyncio
async def test_managed_bindings_receive_distinct_effective_ceilings() -> None:
    definition = _RegistrationAgent()
    registry = {definition.agent_id: definition}

    async def resolve(ceiling: float):
        tokens = _Tokens()
        provider = _provider(tokens)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "run_id": "run-a",
                    "run_ceiling_seconds": ceiling,
                    "binding": {
                        "agent_instance_id": "instance-a",
                        "template_agent_id": definition.agent_id,
                        "owner_scope": "team",
                        "owner_team_id": "team-a",
                        "tuning": {
                            "role": definition.role,
                            "description": definition.description,
                        },
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            target = await _resolve_agent_instance(
                request=_AgentExecuteRequest(
                    agent_instance_id="instance-a", message="synthetic request"
                ),
                registry=registry,
                access_token=None,
                control_plane_url="http://control-plane.test",
                http_client=client,
                team_id="team-a",
                credentials=provider,
            )
        return target, tokens

    short, short_tokens = await resolve(11.0)
    long, long_tokens = await resolve(89.0)

    assert short.run_limits is not None
    assert long.run_limits is not None
    assert short.run_limits.wall_clock_seconds == 11.0
    assert long.run_limits.wall_clock_seconds == 89.0
    assert (
        short.run_limits.max_concurrent_children
        == long.run_limits.max_concurrent_children
    )
    # Registration is the sole managed admission call and should acquire exactly
    # one current workload bearer for each run.
    assert short_tokens.calls == 1
    assert long_tokens.calls == 1


@pytest.mark.asyncio
async def test_failed_managed_registration_stops_before_template_resolution() -> None:
    tokens = _Tokens()
    provider = _provider(tokens)

    class _UnreachableRegistry(dict):
        def get(self, key, default=None):
            pytest.fail("template resolution must not run after failed admission")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DelegationUnavailableError):
            await _resolve_agent_instance(
                request=_AgentExecuteRequest(
                    agent_instance_id="instance-a", message="synthetic request"
                ),
                registry=_UnreachableRegistry(),
                access_token=None,
                control_plane_url="http://control-plane.test",
                http_client=client,
                team_id="team-a",
                credentials=provider,
            )

    assert tokens.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_registration_authority_refusal_is_terminal_without_retry(
    status: int,
) -> None:
    tokens = _Tokens()
    provider = _provider(tokens)
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthorityLostError):
            await register_run(
                provider,
                http_client=client,
                control_plane_url="http://control-plane.test",
                agent_instance_id="instance-a",
                agent_id=None,
                run_ceiling_seconds=60.0,
            )

    assert requests == 1
    assert tokens.calls == 1


@pytest.mark.asyncio
async def test_permitted_transport_retry_gets_fresh_bearer_with_same_grant(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "fred_runtime.common.kf_vectorsearch_client.asyncio.sleep",
        lambda delay: _done(),
    )
    tokens = _Tokens()
    provider = _provider(tokens)
    attempts: list[tuple[str | None, dict[str, str]]] = []

    async def request() -> str:
        credentials = await provider.credentials()
        attempts.append((credentials.authorization, dict(credentials.parameters)))
        if len(attempts) == 1:
            raise httpx.ConnectError("synthetic disconnect")
        return "ok"

    assert await _with_transient_retry(request) == "ok"
    assert [authorization for authorization, _ in attempts] == [
        "Bearer workload-1",
        "Bearer workload-2",
    ]
    assert attempts[0][1] == attempts[1][1]


async def _done() -> None:
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason, expected",
    [
        ("authority_lost", "authority_lost"),
        ("child_limit_reached", "child_limit_reached"),
        ("execution_failed", None),
        ("registration_failed", None),
    ],
)
async def test_terminal_report_is_single_bounded_call_and_404_is_not_retried(
    reason: str, expected: str | None
) -> None:
    tokens = _Tokens()
    provider = _provider(tokens)
    provider.finalize_registration(run_ceiling_seconds=60.0)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await report_run_end(
            provider,
            http_client=client,
            control_plane_url="http://control-plane.test",
            outcome="failed",
            reason=reason,
        )

    assert len(requests) == 1
    assert json.loads(requests[0].content)["reason"] == expected
    assert tokens.calls == 1
    with pytest.raises(Exception):
        await provider.credentials()
