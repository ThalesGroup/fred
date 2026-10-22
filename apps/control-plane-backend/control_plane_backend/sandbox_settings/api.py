# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fred_core import KeycloakUser, OrganizationPermission, get_current_user
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.sandbox_settings.schemas import (
    SandboxSettingsUpdate,
    SandboxSettingsView,
)
from control_plane_backend.sandbox_settings.store import (
    SandboxSettingsStore,
    StoredSandboxSettings,
)

router = APIRouter(tags=["SandboxSettings"])
Dependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


def _store(deps: ProductServiceDependencies) -> SandboxSettingsStore:
    factory = deps.get_sandbox_settings_store
    if factory is None:
        raise HTTPException(503, "sandbox_settings_unavailable")
    return factory()


def _view(stored: StoredSandboxSettings) -> SandboxSettingsView:
    return SandboxSettingsView(
        idle_minutes=stored.idle_minutes,
        max_active_sessions=stored.max_active_sessions,
        profile_id=os.getenv("FRED_SANDBOX_PROFILE_ID", "unconfigured"),
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def _require_admin(deps: ProductServiceDependencies, user: KeycloakUser) -> None:
    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


@router.get("/admin/platform/sandbox-settings", response_model=SandboxSettingsView)
async def get_sandbox_settings(
    deps: Dependencies, user: KeycloakUser = Depends(get_current_user)
) -> SandboxSettingsView:
    await _require_admin(deps, user)
    return _view(await _store(deps).get())


@router.put("/admin/platform/sandbox-settings", response_model=SandboxSettingsView)
async def put_sandbox_settings(
    request: SandboxSettingsUpdate,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> SandboxSettingsView:
    await _require_admin(deps, user)
    stored = await _store(deps).set(
        idle_minutes=request.idle_minutes,
        max_active_sessions=request.max_active_sessions,
        updated_by=user.uid,
    )
    emit_audit_log(
        "platform.sandbox_settings.updated",
        actor_uid=user.uid,
        idle_minutes=request.idle_minutes,
        max_active_sessions=request.max_active_sessions,
    )
    return _view(stored)


@router.get(
    "/internal/sandbox-settings",
    response_model=SandboxSettingsView,
    include_in_schema=False,
)
async def get_internal_sandbox_settings(
    deps: Dependencies, authorization: str | None = Header(default=None)
) -> SandboxSettingsView:
    expected = os.getenv("FRED_SANDBOX_SETTINGS_TOKEN", "")
    if len(expected) < 32 or not hmac.compare_digest(
        authorization or "", f"Bearer {expected}"
    ):
        raise HTTPException(401, "unauthorized")
    return _view(await _store(deps).get())
