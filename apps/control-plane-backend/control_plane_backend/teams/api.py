from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Path, UploadFile, status
from fastapi.responses import JSONResponse
from fred_core import AuthorizationError, KeycloakUser, get_current_user, require_admin
from fred_core.common import TeamId

from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    BannerUploadError,
    CreateTeamRequest,
    KeycloakM2MDisabledError,
    PersonalTeamDeletionError,
    RemoveTeamMemberResponse,
    Team,
    TeamAlreadyExistsError,
    TeamMember,
    TeamMembershipSyncError,
    TeamNotFoundError,
    TeamOwnerConstraintError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
)
from control_plane_backend.teams.service import (
    add_team_member as add_team_member_from_service,
)
from control_plane_backend.teams.service import (
    create_team as create_team_from_service,
)
from control_plane_backend.teams.service import (
    delete_team as delete_team_from_service,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams.service import (
    list_team_members as list_team_members_from_service,
)
from control_plane_backend.teams.service import list_teams as list_teams_from_service
from control_plane_backend.teams.service import (
    remove_team_member as remove_team_member_from_service,
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

    @app.exception_handler(KeycloakM2MDisabledError)
    async def keycloak_disabled_handler(
        _request,
        exc: KeycloakM2MDisabledError,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        _request,
        exc: AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(TeamMembershipSyncError)
    async def team_membership_sync_error_handler(
        _request,
        exc: TeamMembershipSyncError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(TeamOwnerConstraintError)
    async def team_owner_constraint_error_handler(
        _request,
        exc: TeamOwnerConstraintError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(TeamAlreadyExistsError)
    async def team_already_exists_handler(
        _request,
        exc: TeamAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(PersonalTeamDeletionError)
    async def personal_team_deletion_handler(
        _request,
        exc: PersonalTeamDeletionError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


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
    status_code=status.HTTP_201_CREATED,
    response_model=Team,
    response_model_exclude_none=True,
    summary="Create a new collaborative team (admin only)",
)
async def create_team(
    request: CreateTeamRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Team:
    require_admin(user)
    return await create_team_from_service(user, request, deps)


@router.delete(
    "/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a collaborative team and its ReBAC relations (admin only)",
)
async def delete_team(
    team_id: Annotated[TeamId, Path()],
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    require_admin(user)
    await delete_team_from_service(user, team_id, deps)


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
