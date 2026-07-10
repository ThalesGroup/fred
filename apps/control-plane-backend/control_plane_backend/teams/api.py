from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Path, UploadFile
from fastapi.responses import JSONResponse
from fred_core import AuthorizationError, KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    BannerUploadError,
    CreateTeamRequest,
    RemoveTeamMemberResponse,
    RescueTeamAdminRequest,
    RetentionUpdateError,
    Team,
    TeamAdminConstraintError,
    TeamAlreadyExistsError,
    TeamMember,
    TeamNotFoundError,
    TeamRescueNotOrphanedError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
)
from control_plane_backend.teams.service import (
    add_team_member as add_team_member_from_service,
)
from control_plane_backend.teams.service import create_team as create_team_from_service
from control_plane_backend.teams.service import delete_team as delete_team_from_service
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
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
from control_plane_backend.teams.service import update_team as update_team_from_service
from control_plane_backend.teams.service import (
    update_team_member as update_team_member_from_service,
)
from control_plane_backend.teams.service import (
    upload_team_banner as upload_team_banner_from_service,
)

router = APIRouter(tags=["Teams"])
TeamDependencies = Annotated[
    TeamServiceDependencies,
    Depends(get_team_service_dependencies),
]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TeamNotFoundError)
    async def team_not_found_handler(_request, exc: TeamNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(BannerUploadError)
    async def banner_upload_error_handler(
        _request,
        exc: BannerUploadError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        _request,
        exc: AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

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
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(TeamAlreadyExistsError)
    async def team_already_exists_handler(
        _request,
        exc: TeamAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(RetentionUpdateError)
    async def retention_update_error_handler(
        _request,
        exc: RetentionUpdateError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})


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
) -> list[Team]:
    """Registered before `/teams/{team_id}` so the literal `all` path segment
    is not swallowed by the team-id path parameter."""
    return await list_all_teams_from_service(user, deps)


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


@router.post(
    "/teams/{team_id}/banner",
    status_code=204,
    summary="Upload team banner image",
)
async def upload_team_banner(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    file: UploadFile = File(
        ..., description="Banner image file (max 5MB, JPEG/PNG/WebP)"
    ),
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await upload_team_banner_from_service(user, team_id, file, deps)


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


@router.patch(
    "/teams/{team_id}/members/{user_id}",
    status_code=204,
    summary="Update a team member role",
)
async def update_team_member(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    request: UpdateTeamMemberRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await update_team_member_from_service(user, team_id, user_id, request, deps)
