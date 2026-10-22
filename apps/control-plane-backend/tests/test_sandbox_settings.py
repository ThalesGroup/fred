from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.sandbox_settings.api import (
    get_internal_sandbox_settings,
    get_sandbox_settings,
    put_sandbox_settings,
)
from control_plane_backend.sandbox_settings.schemas import SandboxSettingsUpdate
from control_plane_backend.sandbox_settings.store import SandboxSettingsStore
from fastapi import HTTPException
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission
from fred_core.security.models import Resource
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_settings_store_defaults_and_round_trip(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = SandboxSettingsStore(control_plane_sql_engine)
    assert (await store.get()).idle_minutes == 20
    await store.set(
        idle_minutes=30, max_active_sessions=12, warm_capacity=2, updated_by="u"
    )
    saved = await store.get()
    assert (saved.idle_minutes, saved.max_active_sessions, saved.warm_capacity) == (
        30,
        12,
        2,
    )
    assert saved.updated_by == "u"


@pytest.mark.parametrize(
    "payload",
    [
        {"idle_minutes": 0, "max_active_sessions": 8, "warm_capacity": 0},
        {"idle_minutes": 121, "max_active_sessions": 8, "warm_capacity": 0},
        {"idle_minutes": 20, "max_active_sessions": 0, "warm_capacity": 0},
        {
            "idle_minutes": 20,
            "max_active_sessions": 8,
            "warm_capacity": 0,
            "runtime": "runc",
        },
    ],
)
def test_settings_reject_unsafe_or_unapproved_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SandboxSettingsUpdate.model_validate(payload)


class _Rebac:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    async def check_user_permission_or_raise(
        self, user, permission, resource_id
    ) -> None:
        assert permission is OrganizationPermission.CAN_MANAGE_PLATFORM
        if not self.allowed:
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )


class _Store:
    def __init__(self) -> None:
        self.writes = 0

    async def get(self):
        return SimpleNamespace(
            idle_minutes=20,
            max_active_sessions=8,
            warm_capacity=0,
            updated_by=None,
            updated_at=None,
        )

    async def set(self, **kwargs):
        self.writes += 1
        return SimpleNamespace(**kwargs, updated_at=None)


def _deps(allowed: bool, store: _Store) -> ProductServiceDependencies:
    return cast(
        ProductServiceDependencies,
        SimpleNamespace(
            team_dependencies=SimpleNamespace(rebac=_Rebac(allowed)),
            get_sandbox_settings_store=lambda: store,
        ),
    )


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=[], email=None)


@pytest.mark.asyncio
async def test_only_platform_admin_can_change_settings() -> None:
    store = _Store()
    request = SandboxSettingsUpdate(
        idle_minutes=30, max_active_sessions=9, warm_capacity=1
    )
    with pytest.raises(AuthorizationError):
        await get_sandbox_settings(_deps(False, store), _user())
    with pytest.raises(AuthorizationError):
        await put_sandbox_settings(request, _deps(False, store), _user())
    assert store.writes == 0
    saved = await put_sandbox_settings(request, _deps(True, store), _user())
    assert (saved.idle_minutes, saved.max_active_sessions, saved.warm_capacity) == (
        30,
        9,
        1,
    )


@pytest.mark.asyncio
async def test_internal_settings_feed_requires_service_token(monkeypatch) -> None:
    monkeypatch.setenv("FRED_SANDBOX_SETTINGS_TOKEN", "x" * 32)
    deps = _deps(False, _Store())
    with pytest.raises(HTTPException) as error:
        await get_internal_sandbox_settings(deps, "Bearer wrong")
    assert error.value.status_code == 401
    settings = await get_internal_sandbox_settings(deps, "Bearer " + "x" * 32)
    assert settings.idle_minutes == 20
