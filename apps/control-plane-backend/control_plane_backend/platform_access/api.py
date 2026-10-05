# SPDX-License-Identifier: Apache-2.0
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fred_core import get_current_user
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.oidc import get_own_user_for_platform_access
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
)
from fred_pod.security.structure import KeycloakUser

from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.config.models import Configuration
from control_plane_backend.platform_access import service
from control_plane_backend.platform_access.schemas import (
    AcceptFreeEnrollmentCgu,
    FreeEnrollmentPreview,
    PlatformAccessState,
    PlatformAccessStatus,
    PlatformAccessTeam,
    PlatformAccessUsersPage,
    PlatformEnrollmentLink,
    PlatformT0Preview,
    SetPlatformAccessTeam,
    SetPlatformFiltering,
)

router = APIRouter(tags=["PlatformAccess"])
Access = Annotated[PlatformAccess, Depends(get_platform_access)]
Config = Annotated[Configuration, Depends(get_application_configuration)]
OwnUser = Annotated[KeycloakUser, Depends(get_own_user_for_platform_access)]


async def require_access_admin(
    access: Access, user: KeycloakUser = Depends(get_current_user)
) -> KeycloakUser:
    await access.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )
    return user


Admin = Annotated[KeycloakUser, Depends(require_access_admin)]


@router.get("/admin/platform/access", response_model=PlatformAccessState)
async def get_platform_access_state(access: Access, user: Admin) -> PlatformAccessState:
    return service.state_view(await access.state())


@router.patch("/admin/platform/access", response_model=PlatformAccessState)
async def set_platform_access_filtering(
    body: SetPlatformFiltering, access: Access, user: Admin
) -> PlatformAccessState:
    result = await service.set_filtering(access, user, body.filtering_enabled)
    emit_audit_log(
        "platform.access.filtering.updated",
        actor_uid=user.uid,
        filtering_enabled=body.filtering_enabled,
    )
    return result


@router.get("/admin/platform/access/users", response_model=PlatformAccessUsersPage)
async def list_platform_access_users(
    access: Access,
    user: Admin,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    query: str = Query("", max_length=200),
) -> PlatformAccessUsersPage:
    await access.state()
    return await service.users_page(access, offset, limit, query)


@router.put("/admin/platform/access/users/{user_id}", status_code=204)
async def grant_platform_access_user(
    user_id: UUID, access: Access, user: Admin
) -> None:
    await service.set_user(access, user, user_id, True)
    emit_audit_log(
        "platform.access.user.granted", actor_uid=user.uid, target_uid=str(user_id)
    )


@router.delete("/admin/platform/access/users/{user_id}", status_code=204)
async def revoke_platform_access_user(
    user_id: UUID, access: Access, user: Admin
) -> None:
    await service.set_user(access, user, user_id, False)
    emit_audit_log(
        "platform.access.user.revoked", actor_uid=user.uid, target_uid=str(user_id)
    )


@router.get("/admin/platform/access/t0-preview", response_model=PlatformT0Preview)
async def preview_platform_access_t0(access: Access, user: Admin) -> PlatformT0Preview:
    return await service.t0(access)


@router.post("/admin/platform/access/t0-import", response_model=PlatformT0Preview)
async def import_platform_access_t0(access: Access, user: Admin) -> PlatformT0Preview:
    result = await service.t0(access, user)
    emit_audit_log(
        "platform.access.t0.imported",
        actor_uid=user.uid,
        completed_at=result.completed_at,
    )
    return result


@router.get("/admin/platform/access/teams", response_model=list[PlatformAccessTeam])
async def list_platform_access_teams(
    access: Access, user: Admin
) -> list[PlatformAccessTeam]:
    await access.state()
    return [service.team_view(team) for team in await access.store.teams()]


@router.patch(
    "/admin/platform/access/teams/{team_id}", response_model=PlatformAccessTeam
)
async def set_platform_access_team(
    team_id: str, body: SetPlatformAccessTeam, access: Access, user: Admin
) -> PlatformAccessTeam:
    result = await service.set_team(access, user, team_id, body.allowed, body.free)
    emit_audit_log(
        "platform.access.team.updated",
        actor_uid=user.uid,
        team_id=team_id,
        allowed=body.allowed,
        free=body.free,
    )
    return result


@router.post(
    "/admin/platform/access/teams/{team_id}/enrollment-link",
    response_model=PlatformEnrollmentLink,
)
async def generate_platform_enrollment_link(
    team_id: str, access: Access, user: Admin
) -> PlatformEnrollmentLink:
    token = await service.generate_link(access, team_id)
    emit_audit_log("platform.access.link.rotated", actor_uid=user.uid, team_id=team_id)
    return PlatformEnrollmentLink(token=token)


@router.get("/platform-access/status", response_model=PlatformAccessStatus)
async def get_platform_access_status(
    access: Access, config: Config, user: OwnUser
) -> PlatformAccessStatus:
    return await service.self_status(access, user, config.app.gcu_version)


@router.get("/platform-access/free/{token}", response_model=FreeEnrollmentPreview)
async def preview_free_enrollment(
    token: str, access: Access, config: Config, user: OwnUser
) -> FreeEnrollmentPreview:
    return await service.preview_link(access, user, token, config.app.gcu_version)


@router.post("/platform-access/free/{token}/gcu", status_code=204)
async def accept_free_enrollment_cgu(
    token: str,
    body: AcceptFreeEnrollmentCgu,
    access: Access,
    config: Config,
    user: OwnUser,
) -> None:
    await service.accept_cgu(access, user, token, body.version, config.app.gcu_version)


@router.post(
    "/platform-access/free/{token}/enroll", response_model=PlatformAccessStatus
)
async def enroll_free_team(
    token: str, access: Access, config: Config, user: OwnUser
) -> PlatformAccessStatus:
    return await service.enroll(access, user, token, config.app.gcu_version)
