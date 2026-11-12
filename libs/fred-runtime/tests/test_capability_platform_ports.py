# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability routes use CP decisions; optional vision never bypasses admission."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException, Request
from fred_runtime.capabilities import platform_ports
from fred_runtime.runtime_context import RuntimeConfig, RuntimeContext
from fred_sdk.contracts.runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelUnavailableError,
)


@pytest.fixture(autouse=True)
def runtime_context(monkeypatch):
    config = RuntimeConfig(
        knowledge_flow_url="http://unused.invalid", service_name="pod-a"
    )
    monkeypatch.setattr(
        platform_ports, "get_runtime_context", lambda: RuntimeContext(config)
    )
    return config


@pytest.mark.asyncio
async def test_authorizer_uses_cp_space_and_platform_permissions(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(platform_ports, "require_permission", check)
    authorizer = platform_ports.WeaverCapabilityAuthorizer("Bearer person")
    await authorizer.require_agent_editor("project-space")
    check.assert_awaited_with("Bearer person", "write", space_id="project-space")
    await authorizer.require_capability_manager()
    check.assert_awaited_with("Bearer person", "manage_platform")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 503])
async def test_denied_or_unavailable_authority_never_grants_access(monkeypatch, status):
    monkeypatch.setattr(
        platform_ports,
        "require_permission",
        AsyncMock(side_effect=HTTPException(status)),
    )
    authorizer = platform_ports.WeaverCapabilityAuthorizer(None)
    with pytest.raises(HTTPException) as error:
        await authorizer.require_capability_manager()
    assert error.value.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("security_enabled", [False, True])
async def test_binder_keeps_cp_checks_when_local_jwt_is_disabled(
    monkeypatch, security_enabled
):
    check = AsyncMock(side_effect=HTTPException(403))
    monkeypatch.setattr(platform_ports, "require_permission", check)
    request = Request(
        {"type": "http", "headers": [(b"authorization", b"Bearer person")]}
    )
    await platform_ports.team_authorizer_binder(security_enabled=security_enabled)(
        request
    )
    authorizer = getattr(request.state, CAPABILITY_TEAM_AUTHORIZER_STATE)
    with pytest.raises(HTTPException):
        await authorizer.require_agent_editor("space")
    check.assert_awaited_with("Bearer person", "write", space_id="space")
    port = getattr(request.state, CAPABILITY_PLATFORM_MODEL_STATE)
    with pytest.raises(CapabilityModelUnavailableError):
        await port.ainvoke([], profile_id="untrusted")
    with pytest.raises(CapabilityModelUnavailableError):
        await port.require_vision_profile("untrusted")


def test_mounted_capability_router_receives_the_weaver_authorizer(monkeypatch):
    from unittest.mock import MagicMock

    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient
    from fred_runtime.app.agent_app import _mount_capability_routers
    from fred_sdk.contracts.runtime import (
        CapabilityTeamAuthorizer,
        capability_team_authorizer,
    )

    router = APIRouter()

    @router.put("/settings")
    async def settings(
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ):
        await authorizer.require_capability_manager()
        return {"saved": True}

    check = AsyncMock(side_effect=HTTPException(403, "access_denied"))
    monkeypatch.setattr(platform_ports, "require_permission", check)
    root = APIRouter()
    registry = MagicMock()
    registry.routers.return_value = [("test", router)]
    _mount_capability_routers(root, registry, security_enabled=False)
    app = FastAPI()
    app.include_router(root)
    with TestClient(app) as client:
        response = client.put(
            "/capabilities/test/settings", headers={"Authorization": "Bearer user"}
        )
        assert response.status_code == 403
        check.assert_awaited_with("Bearer user", "manage_platform")
        check.side_effect = None
        assert client.put(
            "/capabilities/test/settings", headers={"Authorization": "Bearer user"}
        ).json() == {"saved": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("organization", [False, True])
@pytest.mark.parametrize("reference", ["current", "foreign-or-obsolete"])
@pytest.mark.parametrize("authorization", ["Bearer person", "bearer person"])
@pytest.mark.parametrize("status", [200, 403, 503])
async def test_prepared_preview_uses_current_cp_resolution_and_server_pod(
    monkeypatch, runtime_context, reference, authorization, organization, status
):
    space, agent = str(uuid4()), None if organization else str(uuid4())
    check = AsyncMock()
    monkeypatch.setattr(platform_ports, "require_permission", check)

    def cp(request):
        assert request.url.path == f"/spaces/{space}/powerpoint-template" + (
            "/settings" if organization else ""
        )
        assert request.url.params["runtime_id"] == "pod-a"
        if agent:
            assert request.url.params["agent_instance_id"] == agent
        else:
            assert "agent_instance_id" not in request.url.params
        assert request.headers["authorization"] == "Bearer person"
        payload = {"analysis_reference": "current"}
        return httpx.Response(
            status,
            json={
                "current": payload,
                "replacement": {"analysis_reference": "candidate"},
            }
            if organization
            else payload,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(cp), auth=httpx.BasicAuth("workload", "unused")
    ) as client:
        configured = replace(
            runtime_context,
            control_plane_url="http://cp.invalid",
            control_plane_http_client=client,
        )
        monkeypatch.setattr(
            platform_ports, "get_runtime_context", lambda: RuntimeContext(configured)
        )
        authorizer = platform_ports.WeaverCapabilityAuthorizer(authorization)
        if reference == "current" and status == 200:
            await authorizer.require_preparation_access(reference, space, agent)
        else:
            with pytest.raises(HTTPException) as error:
                await authorizer.require_preparation_access(reference, space, agent)
            assert error.value.status_code == 403
            assert error.value.detail == "preparation_access_denied"
        if organization:
            check.assert_not_awaited()  # CP settings owns the Owner decision.
        else:
            check.assert_awaited_once_with(authorization, "write", space_id=space)
