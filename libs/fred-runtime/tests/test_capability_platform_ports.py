# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability routes use CP decisions; optional vision never bypasses admission."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fred_runtime.capabilities import platform_ports
from fred_sdk.contracts.runtime import (
    CAPABILITY_PLATFORM_MODEL_STATE,
    CAPABILITY_TEAM_AUTHORIZER_STATE,
    CapabilityModelUnavailableError,
)


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
