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

"""
Admin capability-enablement routes (CAPAB-01 / #1980, RFC §8.5).

All routes are gated on `capability#can_manage` (org admin). Structural FGA
tuples are written only through this surface — callers everywhere else check
`can_use`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId
from fred_core.security.models import AuthorizationError

from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.capabilities.enablement import (
    CapabilityNotFound,
    CapabilitySettingsInvalid,
    DefaultOnNotAllowed,
    PersonalScopeNotAllowed,
)
from control_plane_backend.capabilities.schemas import (
    CapabilityDefaultOnResult,
    CapabilityEnablementList,
    CapabilityImpactPreview,
    CapabilityPersonalScopeResult,
    EnableTeamCapabilityRequest,
    SetCapabilityDefaultOnRequest,
    SetCapabilityPersonalScopeRequest,
    TeamCapabilityEnablementResult,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["Capabilities"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthorizationError):
        return HTTPException(status_code=403, detail=str(exc))
    status = getattr(exc, "http_status", None)
    if isinstance(status, int):
        return HTTPException(status_code=status, detail=str(exc))
    raise exc


@router.get(
    "/admin/capabilities",
    response_model=CapabilityEnablementList,
    summary="List capabilities with their team-scope and enablement state.",
)
async def get_admin_capabilities(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> CapabilityEnablementList:
    try:
        return await capability_service.list_capability_enablement(user=user, deps=deps)
    except (AuthorizationError, CapabilityNotFound) as exc:
        raise _map_error(exc) from exc


@router.get(
    "/admin/capabilities/{capability_id}/revoke-impact",
    response_model=CapabilityImpactPreview,
    summary="Preview which agents revoking a capability would suspend.",
)
async def get_capability_revoke_impact(
    capability_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    team_id: Annotated[
        TeamId | None,
        Query(
            description=(
                "Preview one team's disable. Omit for a platform-wide "
                "default-off preview."
            )
        ),
    ] = None,
    user: KeycloakUser = Depends(get_current_user),
) -> CapabilityImpactPreview:
    try:
        return await capability_service.preview_capability_revoke(
            user=user,
            capability_id=capability_id,
            team_id=team_id,
            deps=deps,
        )
    except (AuthorizationError, CapabilityNotFound) as exc:
        raise _map_error(exc) from exc


@router.put(
    "/admin/capabilities/{capability_id}/teams/{team_id}",
    response_model=TeamCapabilityEnablementResult,
    summary="Enable a capability for a team with validated settings.",
)
async def put_team_capability(
    capability_id: Annotated[str, Path(min_length=1)],
    team_id: Annotated[TeamId, Path()],
    body: EnableTeamCapabilityRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamCapabilityEnablementResult:
    try:
        return await capability_service.enable_team_capability(
            user=user,
            capability_id=capability_id,
            team_id=team_id,
            settings=body.settings,
            deps=deps,
        )
    except (
        AuthorizationError,
        CapabilityNotFound,
        CapabilitySettingsInvalid,
        DefaultOnNotAllowed,
    ) as exc:
        raise _map_error(exc) from exc


@router.delete(
    "/admin/capabilities/{capability_id}/teams/{team_id}",
    response_model=TeamCapabilityEnablementResult,
    summary="Disable a capability for a team, or reset it to the platform default.",
)
async def delete_team_capability(
    capability_id: Annotated[str, Path(min_length=1)],
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    mode: Annotated[
        Literal["disable", "default"],
        Query(
            description=(
                "`disable` writes an explicit opt-out (tri-state 'disabled'); "
                "`default` clears both the grant and the opt-out so the "
                "platform default applies (tri-state 'default'). Both suspend "
                "dependent instances when the team loses access."
            ),
        ),
    ] = "disable",
    user: KeycloakUser = Depends(get_current_user),
) -> TeamCapabilityEnablementResult:
    try:
        if mode == "default":
            return await capability_service.reset_team_capability(
                user=user,
                capability_id=capability_id,
                team_id=team_id,
                deps=deps,
            )
        return await capability_service.disable_team_capability(
            user=user,
            capability_id=capability_id,
            team_id=team_id,
            deps=deps,
        )
    except (AuthorizationError, CapabilityNotFound) as exc:
        raise _map_error(exc) from exc


@router.put(
    "/admin/capabilities/{capability_id}/default-on",
    response_model=CapabilityDefaultOnResult,
    summary="Toggle a capability's platform-wide default-on marker.",
)
async def put_capability_default_on(
    capability_id: Annotated[str, Path(min_length=1)],
    body: SetCapabilityDefaultOnRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> CapabilityDefaultOnResult:
    try:
        return await capability_service.set_default_on(
            user=user,
            capability_id=capability_id,
            default_on=body.default_on,
            deps=deps,
        )
    except (
        AuthorizationError,
        CapabilityNotFound,
        DefaultOnNotAllowed,
    ) as exc:
        raise _map_error(exc) from exc


@router.put(
    "/admin/capabilities/{capability_id}/personal-scope",
    response_model=CapabilityPersonalScopeResult,
    summary="Set the personal-space class tri-state for a capability.",
)
async def put_capability_personal_scope(
    capability_id: Annotated[str, Path(min_length=1)],
    body: SetCapabilityPersonalScopeRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> CapabilityPersonalScopeResult:
    try:
        return await capability_service.set_personal_scope(
            user=user,
            capability_id=capability_id,
            scope=body.scope,
            deps=deps,
        )
    except (
        AuthorizationError,
        CapabilityNotFound,
        PersonalScopeNotAllowed,
    ) as exc:
        raise _map_error(exc) from exc
