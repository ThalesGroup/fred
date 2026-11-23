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

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Path, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.common.avatar_image import AvatarUploadError
from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)
from control_plane_backend.teams.join_requests import (
    accept_join_request as accept_join_request_from_service,
)
from control_plane_backend.teams.join_requests import (
    cancel_my_join_request as cancel_my_join_request_from_service,
)
from control_plane_backend.teams.join_requests import (
    create_join_request as create_join_request_from_service,
)
from control_plane_backend.teams.join_requests import (
    list_my_join_requests as list_my_join_requests_from_service,
)
from control_plane_backend.teams.join_requests import (
    list_team_join_requests as list_team_join_requests_from_service,
)
from control_plane_backend.teams.join_requests import (
    refuse_join_request as refuse_join_request_from_service,
)
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    CreateTeamJoinRequest,
    CreateTeamRequest,
    DefaultTeamForNewUsers,
    EditTeamRegistryRequest,
    GrantTeamMemberRoleRequest,
    MyTeamJoinRequest,
    RemoveTeamMemberResponse,
    RescueTeamAdminRequest,
    RetentionUpdateError,
    SetDefaultTeamsForNewUsersRequest,
    Team,
    TeamAdminCharterAcceptance,
    TeamAdminCharterDisabledError,
    TeamAdminConstraintError,
    TeamAlreadyExistsError,
    TeamJoinRequest,
    TeamJoinRequestError,
    TeamMember,
    TeamMemberLastRoleError,
    TeamMemberRoleNotHeldError,
    TeamNotFoundError,
    TeamNotOpenForJoiningError,
    TeamRescueNotOrphanedError,
    TeamWithPermissions,
    UpdateTeamRequest,
    UserTeamRelation,
)
from control_plane_backend.teams.service import (
    accept_team_admin_charter as accept_team_admin_charter_from_service,
)
from control_plane_backend.teams.service import (
    add_team_member as add_team_member_from_service,
)
from control_plane_backend.teams.service import create_team as create_team_from_service
from control_plane_backend.teams.service import delete_team as delete_team_from_service
from control_plane_backend.teams.service import (
    edit_team_registry as edit_team_registry_from_service,
)
from control_plane_backend.teams.service import (
    get_default_teams_for_new_users as get_default_teams_for_new_users_from_service,
)
from control_plane_backend.teams.service import (
    get_team_admin_charter_acceptance as get_team_admin_charter_acceptance_from_service,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams.service import (
    grant_team_member_role as grant_team_member_role_from_service,
)
from control_plane_backend.teams.service import join_team as join_team_from_service
from control_plane_backend.teams.service import (
    list_all_teams_for_registry as list_all_teams_from_service,
)
from control_plane_backend.teams.service import (
    list_team_members as list_team_members_from_service,
)
from control_plane_backend.teams.service import list_teams as list_teams_from_service
from control_plane_backend.teams.service import (
    remove_team_member as remove_team_member_from_service,
)
from control_plane_backend.teams.service import (
    rescue_team_admin as rescue_team_admin_from_service,
)
from control_plane_backend.teams.service import (
    revoke_team_member_role as revoke_team_member_role_from_service,
)
from control_plane_backend.teams.service import (
    search_candidate_team_admins as search_candidate_team_admins_from_service,
)
from control_plane_backend.teams.service import (
    search_candidate_team_members as search_candidate_team_members_from_service,
)
from control_plane_backend.teams.service import (
    set_default_teams_for_new_users as set_default_teams_for_new_users_from_service,
)
from control_plane_backend.teams.service import update_team as update_team_from_service
from control_plane_backend.teams.service import (
    upload_team_avatar as upload_team_avatar_from_service,
)
from control_plane_backend.users.schemas import UserSummary

router = APIRouter(tags=["Teams"])
TeamDependencies = Annotated[
    TeamServiceDependencies,
    Depends(get_team_service_dependencies),
]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TeamNotFoundError)
    async def team_not_found_handler(_request, exc: TeamNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AvatarUploadError)
    async def avatar_upload_error_handler(
        _request,
        exc: AvatarUploadError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(TeamRescueNotOrphanedError)
    async def team_rescue_not_orphaned_handler(
        _request,
        exc: TeamRescueNotOrphanedError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(TeamAdminConstraintError)
    async def team_admin_constraint_error_handler(
        _request,
        exc: TeamAdminConstraintError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": str(exc), "code": exc.code}
        )

    @app.exception_handler(TeamAdminCharterDisabledError)
    async def team_admin_charter_disabled_handler(
        _request,
        exc: TeamAdminCharterDisabledError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(TeamAlreadyExistsError)
    async def team_already_exists_handler(
        _request,
        exc: TeamAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": str(exc), "code": exc.code}
        )

    @app.exception_handler(RetentionUpdateError)
    async def retention_update_error_handler(
        _request,
        exc: RetentionUpdateError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(TeamMemberRoleNotHeldError)
    async def team_member_role_not_held_handler(
        _request,
        exc: TeamMemberRoleNotHeldError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(TeamMemberLastRoleError)
    async def team_member_last_role_handler(
        _request,
        exc: TeamMemberLastRoleError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(TeamNotOpenForJoiningError)
    async def team_not_open_for_joining_handler(
        _request,
        exc: TeamNotOpenForJoiningError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(TeamJoinRequestError)
    async def team_join_request_error_handler(
        _request,
        exc: TeamJoinRequestError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": str(exc), "code": exc.code}
        )


@router.get(
    "/teams",
    response_model=list[Team],
    response_model_exclude_none=True,
    summary="List teams the user has access to",
)
async def list_teams(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[Team]:
    return await list_teams_from_service(user, deps)


@router.post(
    "/teams",
    status_code=201,
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Bootstrap a new team with its initial team_admin(s) (platform admin only)",
)
async def create_team(
    request: CreateTeamRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await create_team_from_service(user, request, deps)


@router.get(
    "/teams/all",
    response_model=list[Team],
    response_model_exclude_none=True,
    summary="List every team in the registry, regardless of membership (platform admin only)",
)
async def list_all_teams(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
    include_membership: Annotated[
        bool,
        Query(
            description=(
                "false skips the per-team ReBAC reads: admins, membership and "
                "member_count are left unset. For pickers that only need ids "
                "and names."
            )
        ),
    ] = True,
) -> list[Team]:
    """Registered before `/teams/{team_id}` so the literal `all` path segment
    is not swallowed by the team-id path parameter."""
    return await list_all_teams_from_service(
        user, deps, include_membership=include_membership
    )


@router.get(
    "/teams/join-requests/mine",
    response_model=list[MyTeamJoinRequest],
    summary="List the caller's own unexpired requests to join teams",
)
async def list_my_team_join_requests(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[MyTeamJoinRequest]:
    return await list_my_join_requests_from_service(user, deps)


@router.get(
    "/teams/candidate-admins",
    response_model=list[UserSummary],
    response_model_exclude_none=True,
    summary="Search users eligible to be a new team's first team_admin",
)
async def search_candidate_team_admins(
    query: Annotated[str, Query(min_length=2)],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[UserSummary]:
    """Feeds `POST /teams`' `initial_team_admin_ids` and is gated on the same
    `can_create_team`. Registered before `/teams/{team_id}` so the literal
    path segment is not swallowed by the team-id path parameter."""
    return await search_candidate_team_admins_from_service(user, query, deps)


@router.get(
    "/teams/{team_id}",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Get a specific team by ID",
)
async def get_team(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await get_team_by_id_from_service(user, team_id, deps)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Update a specific team metadata",
)
async def update_team(
    team_id: Annotated[TeamId, Path()],
    request: UpdateTeamRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await update_team_from_service(user, team_id, request, deps)


@router.patch(
    "/teams/{team_id}/registry",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Edit any team's name, description and admins (platform admin only)",
)
async def edit_team_registry(
    team_id: Annotated[TeamId, Path()],
    request: EditTeamRegistryRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await edit_team_registry_from_service(user, team_id, request, deps)


@router.post(
    "/teams/{team_id}/join",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Self-service join a team open for joining (TEAM-09)",
)
async def join_team(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    """Only succeeds when the team's `joining_mode` is `OPEN` — see
    `TeamNotOpenForJoiningError`. The caller can only ever grant themselves
    `team_member`; this is the sole membership-write route that does not
    require an existing administer-permission over the target team."""
    return await join_team_from_service(user, team_id, deps)


@router.post(
    "/teams/{team_id}/join-requests",
    status_code=201,
    response_model=MyTeamJoinRequest,
    responses={200: {"model": MyTeamJoinRequest}},
    summary="Ask to join an on_request team (201 new, 200 already pending)",
)
async def create_team_join_request(
    team_id: Annotated[TeamId, Path()],
    request: CreateTeamJoinRequest,
    response: Response,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MyTeamJoinRequest:
    """Like `POST /teams/{team_id}/join`, trusts only the caller as the target."""
    created, is_new = await create_join_request_from_service(
        user, team_id, request.message, deps
    )
    if not is_new:
        response.status_code = 200
    return created


@router.delete(
    "/teams/{team_id}/join-requests/mine",
    status_code=204,
    summary="Cancel the caller's pending request to join a team",
)
async def cancel_my_team_join_request(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await cancel_my_join_request_from_service(user, team_id, deps)


@router.get(
    "/teams/{team_id}/join-requests",
    response_model=list[TeamJoinRequest],
    summary="List a team's pending and recently refused join requests",
)
async def list_team_join_requests(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[TeamJoinRequest]:
    return await list_team_join_requests_from_service(user, team_id, deps)


@router.post(
    "/teams/{team_id}/join-requests/{request_id}/accept",
    status_code=204,
    summary="Accept a join request, pending or refused (grants team_member)",
)
async def accept_team_join_request(
    team_id: Annotated[TeamId, Path()],
    request_id: Annotated[str, Path(min_length=1)],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await accept_join_request_from_service(user, team_id, request_id, deps)


@router.post(
    "/teams/{team_id}/join-requests/{request_id}/refuse",
    status_code=204,
    summary="Refuse a pending join request",
)
async def refuse_team_join_request(
    team_id: Annotated[TeamId, Path()],
    request_id: Annotated[str, Path(min_length=1)],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await refuse_join_request_from_service(user, team_id, request_id, deps)


@router.delete(
    "/teams/{team_id}",
    status_code=204,
    summary="Delete a team's registry entry and all its relations (platform admin only)",
)
async def delete_team(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await delete_team_from_service(user, team_id, deps)


@router.post(
    "/teams/{team_id}/rescue-admin",
    status_code=204,
    summary="Grant team_admin on an orphaned team with zero admins (platform admin only)",
)
async def rescue_team_admin(
    team_id: Annotated[TeamId, Path()],
    request: RescueTeamAdminRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await rescue_team_admin_from_service(user, team_id, request.user_id, deps)


@router.get(
    "/admin/platform/default-teams",
    response_model=list[DefaultTeamForNewUsers],
    summary="List the teams every new user joins on first GCU acceptance (platform admin only)",
)
async def get_default_teams_for_new_users(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[DefaultTeamForNewUsers]:
    return await get_default_teams_for_new_users_from_service(user, deps)


@router.put(
    "/admin/platform/default-teams",
    status_code=204,
    summary="Replace the teams every new user joins on first GCU acceptance (platform admin only)",
)
async def set_default_teams_for_new_users(
    request: SetDefaultTeamsForNewUsersRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await set_default_teams_for_new_users_from_service(user, request.team_ids, deps)


@router.get(
    "/team-admin-charter",
    response_model=TeamAdminCharterAcceptance | None,
    summary="Read when the caller accepted the current team administrator charter",
)
async def get_team_admin_charter_acceptance(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamAdminCharterAcceptance | None:
    return await get_team_admin_charter_acceptance_from_service(user, deps)


@router.post(
    "/team-admin-charter",
    response_model=TeamAdminCharterAcceptance,
    summary="Accept the current team administrator charter and activate pending admin roles",
)
async def accept_team_admin_charter(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamAdminCharterAcceptance:
    return await accept_team_admin_charter_from_service(user, deps)


@router.post(
    "/teams/{team_id}/avatar",
    status_code=204,
    summary="Upload team avatar image",
)
async def upload_team_avatar(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    file: UploadFile = File(
        ..., description="Avatar image file (max 5MB, JPEG/PNG/WebP)"
    ),
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await upload_team_avatar_from_service(user, team_id, file, deps)


@router.get(
    "/teams/{team_id}/members",
    response_model=list[TeamMember],
    response_model_exclude_none=True,
    summary="List members of a specific team",
)
async def list_team_members(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[TeamMember]:
    return await list_team_members_from_service(user, team_id, deps)


@router.post(
    "/teams/{team_id}/members",
    status_code=204,
    summary="Add a member to a team",
)
async def add_team_member(
    team_id: Annotated[TeamId, Path()],
    request: AddTeamMemberRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await add_team_member_from_service(user, team_id, request, deps)


@router.get(
    "/teams/{team_id}/candidate-members",
    response_model=list[UserSummary],
    response_model_exclude_none=True,
    summary="Search Keycloak users eligible to be added to a team",
)
async def search_candidate_team_members(
    team_id: Annotated[TeamId, Path()],
    query: Annotated[str, Query(min_length=2)],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[UserSummary]:
    return await search_candidate_team_members_from_service(user, team_id, query, deps)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    status_code=202,
    response_model=RemoveTeamMemberResponse,
    summary="Remove a member from a team and enqueue session purge",
)
async def remove_team_member(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> RemoveTeamMemberResponse:
    return await remove_team_member_from_service(user, team_id, user_id, deps)


@router.post(
    "/teams/{team_id}/members/{user_id}/roles",
    status_code=204,
    summary="Grant one additional team role to an existing member",
)
async def grant_team_member_role(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    request: GrantTeamMemberRoleRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """AUTHZ-06 (RFC Part 7 §34): a member may hold `team_admin`, `team_editor`,
    and `team_analyst` simultaneously on the same team — each role is granted
    as its own explicit, independently permission-checked action, never a
    bulk role-set replace."""
    await grant_team_member_role_from_service(user, team_id, user_id, request, deps)


@router.delete(
    "/teams/{team_id}/members/{user_id}/roles/{relation}",
    status_code=204,
    summary="Revoke one team role from an existing member",
)
async def revoke_team_member_role(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    relation: Annotated[UserTeamRelation, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """Revoke one role, retaining a sole elevated-role holder as a member.

    A sole direct `team_member` is refused (409); full removal uses the member route.
    """
    await revoke_team_member_role_from_service(user, team_id, user_id, relation, deps)
