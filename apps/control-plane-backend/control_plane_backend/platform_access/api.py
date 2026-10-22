# SPDX-License-Identifier: Apache-2.0
import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fred_core import get_current_user
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.oidc import (
    decode_jwt,
    get_own_user_for_platform_access,
    oauth2_scheme,
)
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
    TeamPermission,
)
from fred_pod.security.platform_access import PlatformAccessPolicy
from fred_pod.security.structure import KeycloakUser

from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.config.models import Configuration
from control_plane_backend.platform_access import service
from control_plane_backend.platform_access.directory import PlatformAccessDirectory
from control_plane_backend.platform_access.schemas import (
    AcceptFreeEnrollmentCgu,
    CreatePlatformEnrollmentLink,
    DeletedPlatformEnrollmentLinks,
    EnrollmentResult,
    FreeEnrollmentPreview,
    GrantPlatformAccessUsers,
    PlatformAccessActivationPreview,
    PlatformAccessOwnClaims,
    PlatformAccessPolicyPreview,
    PlatformAccessState,
    PlatformAccessStatus,
    PlatformAccessTeam,
    PlatformAccessUsersPage,
    PlatformEnrollmentJoinersPage,
    PlatformEnrollmentLink,
    PlatformEnrollmentLinksPage,
    PlatformEnrollmentLinkStatus,
    PlatformT0Preview,
    PlatformT0RefreshMode,
    RefreshPlatformT0,
    SetPlatformAccessPolicy,
    SetPlatformAccessTeam,
    SetPlatformFiltering,
    SetTeamJoinLink,
    TeamJoinLink,
)
from control_plane_backend.users.dependencies import (
    UserServiceDependencies,
    get_user_service_dependencies,
)

router = APIRouter(tags=["PlatformAccess"])
Access = Annotated[PlatformAccess, Depends(get_platform_access)]
Config = Annotated[Configuration, Depends(get_application_configuration)]
UserDeps = Annotated[UserServiceDependencies, Depends(get_user_service_dependencies)]
OwnUser = Annotated[KeycloakUser, Depends(get_own_user_for_platform_access)]


async def require_access_admin(
    access: Access, user: KeycloakUser = Depends(get_current_user)
) -> KeycloakUser:
    await access.rebac.check_user_permission_or_raise(
        user,
        OrganizationPermission.CAN_MANAGE_PLATFORM_ACCESS,
        ORGANIZATION_ID,
        consistency_token=access.rebac.HIGHER_CONSISTENCY,
    )
    return user


Admin = Annotated[KeycloakUser, Depends(require_access_admin)]


@router.get("/admin/platform/access", response_model=PlatformAccessState)
async def get_platform_access_state(access: Access, user: Admin) -> PlatformAccessState:
    return await service.state_view(access, await access.state())


@router.patch("/admin/platform/access", response_model=PlatformAccessState)
async def set_platform_access_filtering(
    body: SetPlatformFiltering, access: Access, user: Admin
) -> PlatformAccessState:
    result = await service.set_filtering(
        access, user, body.filtering_enabled, body.expected_revision
    )
    emit_audit_log(
        "platform.access.filtering.updated",
        actor_uid=user.uid,
        filtering_enabled=body.filtering_enabled,
        revision=result.revision,
    )
    return result


@router.get(
    "/admin/platform/access/activation-preview",
    response_model=PlatformAccessActivationPreview,
)
async def preview_platform_access_activation(
    access: Access, user: Admin, response: Response, deps: UserDeps
) -> PlatformAccessActivationPreview:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(120):
            return await service.activation_preview(
                access, PlatformAccessDirectory(deps)
            )
    except TimeoutError:
        raise HTTPException(503, "platform_access_unavailable") from None


@router.get("/admin/platform/access/own-claims", response_model=PlatformAccessOwnClaims)
async def get_platform_access_own_claims(
    access: Access,
    user: Admin,
    response: Response,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> PlatformAccessOwnClaims:
    service.require_own_credential(user)
    if not token:
        raise HTTPException(401, "requires_own_credential")
    await access.state()
    payload: dict[str, object] = {}
    verified = await asyncio.to_thread(decode_jwt, token, verified_payload=payload)
    service.require_own_credential(verified)
    if verified.uid != user.uid:
        raise HTTPException(403, "requires_own_credential")
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(service.own_claims, payload)


@router.post(
    "/admin/platform/access/policy-preview", response_model=PlatformAccessPolicyPreview
)
async def preview_platform_access_policy(
    body: PlatformAccessPolicy, access: Access, user: Admin
) -> PlatformAccessPolicyPreview:
    return await service.preview_policy(access, user, body)


@router.put("/admin/platform/access/policy", response_model=PlatformAccessState)
async def save_platform_access_policy(
    body: SetPlatformAccessPolicy, access: Access, user: Admin
) -> PlatformAccessState:
    result = await service.save_policy(
        access, user, body.policy, body.expected_revision
    )
    emit_audit_log(
        "platform.access.policy.updated", actor_uid=user.uid, revision=result.revision
    )
    return result


@router.get("/admin/platform/access/users", response_model=PlatformAccessUsersPage)
async def list_platform_access_users(
    access: Access,
    user: Admin,
    deps: UserDeps,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    query: str = Query("", max_length=200),
    exceptions_only: bool = Query(
        False, description="Only users holding an individual exception."
    ),
) -> PlatformAccessUsersPage:
    return await service.users_page(
        access, offset, limit, query, exceptions_only, PlatformAccessDirectory(deps)
    )


@router.post("/admin/platform/access/users", status_code=204)
async def grant_platform_access_users(
    body: GrantPlatformAccessUsers, access: Access, user: Admin, deps: UserDeps
) -> None:
    granted_count = await service.grant_users(
        access, user, body.user_ids, PlatformAccessDirectory(deps)
    )
    emit_audit_log(
        "platform.access.users.granted",
        actor_uid=user.uid,
        count=len(set(body.user_ids)),
        granted_count=granted_count,
    )


@router.put("/admin/platform/access/users/{user_id}", status_code=204)
async def grant_platform_access_user(
    user_id: UUID, access: Access, user: Admin, deps: UserDeps
) -> None:
    await service.set_user(access, user, user_id, True, PlatformAccessDirectory(deps))
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
async def preview_platform_access_t0(
    access: Access,
    user: Admin,
    deps: UserDeps,
    refresh_mode: PlatformT0RefreshMode | None = None,
) -> PlatformT0Preview:
    return await service.t0(
        access, directory=PlatformAccessDirectory(deps), refresh_mode=refresh_mode
    )


@router.post("/admin/platform/access/t0-import", response_model=PlatformT0Preview)
async def import_platform_access_t0(
    access: Access,
    user: Admin,
    deps: UserDeps,
    body: RefreshPlatformT0 | None = None,
) -> PlatformT0Preview:
    result, imported_count = await service.import_t0(
        access, user, directory=PlatformAccessDirectory(deps), refresh=body
    )
    if imported_count is not None:
        emit_audit_log(
            "platform.access.t0.imported",
            actor_uid=user.uid,
            completed_at=result.completed_at,
            candidates=result.candidates,
            matching=result.matching,
            imported_count=imported_count,
            mode=body.mode if body is not None else None,
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
    team_id: str,
    body: CreatePlatformEnrollmentLink,
    access: Access,
    user: Admin,
    response: Response,
) -> PlatformEnrollmentLink:
    service.require_own_credential(user)
    token, link_id = await service.generate_link_record(access, team_id, user, body)
    response.headers["Cache-Control"] = "no-store"
    emit_audit_log(
        "platform.access.link.created",
        actor_uid=user.uid,
        team_id=team_id,
        link_id=str(link_id),
    )
    return PlatformEnrollmentLink(token=token)


@router.get(
    "/admin/platform/access/teams/{team_id}/enrollment-links",
    response_model=PlatformEnrollmentLinksPage,
)
async def list_platform_enrollment_links(
    team_id: str,
    access: Access,
    user: Admin,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    status: PlatformEnrollmentLinkStatus | None = None,
) -> PlatformEnrollmentLinksPage:
    return await service.list_links(access, team_id, offset, limit, status)


@router.get(
    "/admin/platform/access/teams/{team_id}/enrollment-links/{link_id}/joiners",
    response_model=PlatformEnrollmentJoinersPage,
)
async def list_platform_enrollment_joiners(
    team_id: str,
    link_id: UUID,
    access: Access,
    user: Admin,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
) -> PlatformEnrollmentJoinersPage:
    return await service.list_link_joiners(access, team_id, link_id, offset, limit)


@router.delete(
    "/admin/platform/access/teams/{team_id}/enrollment-links/inactive",
    response_model=DeletedPlatformEnrollmentLinks,
)
async def delete_inactive_platform_enrollment_links(
    team_id: str, access: Access, user: Admin
) -> DeletedPlatformEnrollmentLinks:
    deleted = await service.delete_inactive_links(access, team_id)
    emit_audit_log(
        "platform.access.links.deleted",
        actor_uid=user.uid,
        team_id=team_id,
        deleted_count=deleted,
    )
    return DeletedPlatformEnrollmentLinks(deleted_count=deleted)


@router.post(
    "/admin/platform/access/teams/{team_id}/enrollment-links/{link_id}/reveal",
    response_model=PlatformEnrollmentLink,
)
async def reveal_platform_enrollment_link(
    team_id: str, link_id: UUID, access: Access, user: Admin, response: Response
) -> PlatformEnrollmentLink:
    service.require_own_credential(user)
    token = await service.reveal_link(access, team_id, link_id)
    response.headers["Cache-Control"] = "no-store"
    emit_audit_log(
        "platform.access.link.revealed",
        actor_uid=user.uid,
        team_id=team_id,
        link_id=str(link_id),
    )
    return PlatformEnrollmentLink(token=token)


@router.delete(
    "/admin/platform/access/teams/{team_id}/enrollment-links/{link_id}", status_code=204
)
async def revoke_platform_enrollment_link(
    team_id: str, link_id: UUID, access: Access, user: Admin
) -> None:
    await service.revoke_link(access, team_id, link_id)
    emit_audit_log(
        "platform.access.link.revoked",
        actor_uid=user.uid,
        team_id=team_id,
        link_id=str(link_id),
    )


async def require_team_members_admin(
    team_id: str, access: Access, user: KeycloakUser = Depends(get_current_user)
) -> KeycloakUser:
    await access.rebac.check_user_permission_or_raise(
        user,
        TeamPermission.CAN_ADMINISTER_MEMBERS,
        team_id,
        consistency_token=access.rebac.HIGHER_CONSISTENCY,
    )
    # The response carries the reusable URL, as the administrators' reveal does.
    service.require_own_credential(user)
    return user


TeamAdmin = Annotated[KeycloakUser, Depends(require_team_members_admin)]
TEAM_LINK = "/teams/{team_id}/join-link"


@router.get(TEAM_LINK, response_model=TeamJoinLink, tags=["Teams"])
async def get_team_join_link(
    team_id: str, access: Access, user: TeamAdmin, response: Response
) -> TeamJoinLink:
    response.headers["Cache-Control"] = "no-store"
    return await service.get_team_link(access, team_id)


@router.put(TEAM_LINK, response_model=TeamJoinLink, tags=["Teams"])
async def set_team_join_link(
    team_id: str,
    body: SetTeamJoinLink,
    access: Access,
    user: TeamAdmin,
    response: Response,
) -> TeamJoinLink:
    result = await service.set_team_link(access, team_id, user, body.enabled)
    response.headers["Cache-Control"] = "no-store"
    emit_audit_log(
        "team.join_link.enabled" if body.enabled else "team.join_link.paused",
        actor_uid=user.uid,
        team_id=team_id,
    )
    return result


@router.post(TEAM_LINK + "/regenerate", response_model=TeamJoinLink, tags=["Teams"])
async def regenerate_team_join_link(
    team_id: str, access: Access, user: TeamAdmin, response: Response
) -> TeamJoinLink:
    result = await service.regenerate_team_link(access, team_id, user)
    response.headers["Cache-Control"] = "no-store"
    emit_audit_log("team.join_link.regenerated", actor_uid=user.uid, team_id=team_id)
    return result


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


@router.post("/platform-access/free/{token}/opening", status_code=204)
async def record_free_enrollment_opening(
    token: str, access: Access, user: OwnUser
) -> None:
    await service.record_opening(access, token, user)


@router.post("/platform-access/free/{token}/gcu", status_code=204)
async def accept_free_enrollment_cgu(
    token: str,
    body: AcceptFreeEnrollmentCgu,
    access: Access,
    config: Config,
    user: OwnUser,
) -> None:
    await service.accept_cgu(access, user, token, body.version, config.app.gcu_version)


@router.post("/platform-access/free/{token}/enroll", response_model=EnrollmentResult)
async def enroll_free_team(
    token: str, access: Access, config: Config, user: OwnUser
) -> EnrollmentResult:
    return await service.enroll(access, user, token, config.app.gcu_version)
