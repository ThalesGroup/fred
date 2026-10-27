# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Direct-turn shared policy and compatibility through public HTTP/metadata seams."""

import json

import httpx
import pytest
from conftest import StaticWorkloadTokens, admitted_provider
from fastapi import HTTPException
from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
)
from fred_runtime.skills.policy import (
    legacy_skill_metadata_response,
    resolve_direct_skill_policy,
)
from fred_sdk.contracts.skills import SkillCatalog, SkillDetail, SkillSummary


@pytest.mark.asyncio
async def test_direct_turn_reads_fresh_policy_with_person_identity() -> None:
    disabled = ["mermaid"]
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"disabled_skill_names": disabled})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        first = await resolve_direct_skill_policy(
            control_plane_url="https://platform.invalid/control-plane/v1/",
            http_client=client,
            access_token="person-token",
            request_id="request-1",
        )
        disabled = []
        second = await resolve_direct_skill_policy(
            control_plane_url="https://platform.invalid/control-plane/v1",
            http_client=client,
            access_token="person-token",
        )
    assert first == ("mermaid",)
    assert second == ()
    assert len(requests) == 2
    assert requests[0].url.path == "/control-plane/v1/platform/skills/policy"
    assert requests[0].headers["Authorization"] == "Bearer person-token"
    assert requests[0].headers["X-Request-Id"] == "request-1"
    assert requests[0].extensions["timeout"]["read"] == 10.0


@pytest.mark.asyncio
async def test_direct_policy_delegates_using_live_grant_and_workload_identity() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"disabled_skill_names": []})

    provider = admitted_provider(StaticWorkloadTokens("workload-token"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token="must-not-forward-person",
                credentials=provider,
            )
            == ()
        )
    assert requests[0].headers["Authorization"] == "Bearer workload-token"
    assert dict(requests[0].url.params) == {
        GRANT_PARAM_PERSON: "alice",
        GRANT_PARAM_RUN: "run-7",
        GRANT_PARAM_AGENT: "agent-a",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(401, 403), (403, 403), (404, 503), (503, 503), (307, 503)]
)
async def test_direct_policy_refuses_failures_and_never_follows_redirects(
    status: int, expected: int
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://elsewhere.invalid"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), follow_redirects=True
    ) as client:
        with pytest.raises(HTTPException) as exc:
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token="person",
            )
    assert exc.value.status_code == expected
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"disabled_skill_names": ["../escape"]},
        {"disabled_skill_names": ["mermaid"], "unknown": True},
    ],
)
async def test_direct_policy_rejects_invalid_metadata(
    payload: dict[str, object],
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(HTTPException) as exc:
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token=None,
            )
    assert exc.value.status_code == 503


@pytest.mark.parametrize("detail", [False, True])
def test_legacy_metadata_keeps_original_shape_and_opt_in_exposes_new_fields(
    detail: bool,
) -> None:
    summary = SkillSummary(
        name="mermaid", description="Draw", builtin=True, user_invocable=False
    )
    value = (
        SkillDetail(skill=summary, revision="r1", content="# Draw")
        if detail
        else SkillCatalog(skills=(summary,), policy_supported=True)
    )
    legacy = json.loads(bytes(legacy_skill_metadata_response(value).body))
    full = json.loads(
        bytes(legacy_skill_metadata_response(value, metadata_version=1).body)
    )
    old_summary = legacy["skill"] if detail else legacy["skills"][0]
    new_summary = full["skill"] if detail else full["skills"][0]
    assert old_summary == {
        "name": "mermaid",
        "description": "Draw",
        "argument_hint": None,
    }
    assert new_summary["builtin"] is True
    assert new_summary["user_invocable"] is False
    if not detail:
        assert "policy_supported" not in legacy
        assert full["policy_supported"] is True


@pytest.mark.asyncio
async def test_standalone_skips_policy_network_but_missing_delegation_fails_closed() -> (
    None
):
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"disabled_skill_names": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (
            await resolve_direct_skill_policy(
                control_plane_url=None, http_client=client, access_token=None
            )
            == ()
        )
        with pytest.raises(HTTPException) as exc:
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token=None,
                credentials=admitted_provider(None),
            )
    assert exc.value.status_code == 503
    assert requests == []


@pytest.mark.asyncio
async def test_account_status_denial_retains_stable_cause_header() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                503, headers={DENIAL_CAUSE_HEADER: ACCOUNT_STATUS_UNAVAILABLE_CAUSE}
            )
        )
    ) as client:
        with pytest.raises(HTTPException) as exc:
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token="person",
            )
    assert exc.value.status_code == 503
    assert exc.value.headers == {DENIAL_CAUSE_HEADER: ACCOUNT_STATUS_UNAVAILABLE_CAUSE}


@pytest.mark.asyncio
async def test_policy_timeout_does_not_run_without_restrictions() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as exc:
            await resolve_direct_skill_policy(
                control_plane_url="https://platform.invalid",
                http_client=client,
                access_token="person",
            )
    assert exc.value.status_code == 503
