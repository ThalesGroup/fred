# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app, authorization


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,expected", [({"allowed": True}, True), ({"allowed": False}, False)]
)
async def test_platform_decision_forwards_credential_and_preserves_denial(
    monkeypatch, body, expected
):
    calls = []

    async def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer person-token"
        assert request.url.path == "/authorize/platform"
        assert request.content == b'{"permission":"manage_platform"}'
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            authorization,
            "get_runtime_context",
            lambda: SimpleNamespace(
                config=SimpleNamespace(
                    control_plane_url="https://authority.test",
                    control_plane_http_client=client,
                )
            ),
        )
        assert (
            await authorization.is_allowed("Bearer person-token", "manage_platform")
            is expected
        )
        assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body", [(500, {}), (200, {}), (200, {"allowed": "true"}), (200, [])]
)
async def test_unknown_authority_result_is_unavailable(monkeypatch, status, body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    ) as client:
        monkeypatch.setattr(
            authorization,
            "get_runtime_context",
            lambda: SimpleNamespace(
                config=SimpleNamespace(
                    control_plane_url="https://authority.test",
                    control_plane_http_client=client,
                )
            ),
        )
        with pytest.raises(HTTPException) as error:
            await authorization.is_allowed("Bearer person-token", "manage_platform")
        assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,permission",
    [
        ("get_kpi_turns", "manage_platform"),
        ("get_audit_events", "manage_platform"),
        ("list_web_research_activity", "manage_platform"),
        ("erase_web_research_activity", "administer_users"),
    ],
)
async def test_admin_routes_require_the_control_plane_permission(
    monkeypatch, name, permission
):
    from unittest.mock import AsyncMock

    decision = AsyncMock(side_effect=HTTPException(403, "access_denied"))
    monkeypatch.setattr(agent_app, "require_permission", decision)
    router = agent_app._build_agent_router(
        registry={}, security_enabled=True, max_chat_input_chars=5000
    )
    endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.endpoint.__name__ == name
    )
    request = Request(
        {"type": "http", "headers": [(b"authorization", b"Bearer person-token")]}
    )
    kwargs = {
        "http_request": request,
        "caller": KeycloakUser(uid="person", username="person", roles=[]),
        "container": SimpleNamespace(),
    }
    if name == "erase_web_research_activity":
        kwargs["user_id"] = "other"
    with pytest.raises(HTTPException) as error:
        await endpoint(**kwargs)
    assert error.value.status_code == 403
    decision.assert_awaited_once_with("Bearer person-token", permission)


@pytest.mark.asyncio
async def test_closed_authorization_client_is_unavailable(monkeypatch):
    async with httpx.AsyncClient() as client:
        pass
    monkeypatch.setattr(
        authorization,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                control_plane_url="https://authority.test",
                control_plane_http_client=client,
            )
        ),
    )
    with pytest.raises(HTTPException) as error:
        await authorization.is_allowed("Bearer person-token", "manage_platform")
    assert error.value.status_code == 503
