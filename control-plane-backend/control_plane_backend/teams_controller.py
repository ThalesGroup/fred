from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Path, UploadFile
from fastapi.responses import JSONResponse
from fred_core import AuthorizationError, KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.teams_service import (
    add_team_member as add_team_member_from_service,
)
from control_plane_backend.teams_service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams_service import (
    list_team_members as list_team_members_from_service,
)
from control_plane_backend.teams_service import list_teams as list_teams_from_service
from control_plane_backend.teams_service import (
    remove_team_member as remove_team_member_from_service,
)
from control_plane_backend.teams_service import update_team as update_team_from_service
from control_plane_backend.teams_service import (
    update_team_member as update_team_member_from_service,
)
from control_plane_backend.teams_service import (
    upload_team_banner as upload_team_banner_from_service,
)
from control_plane_backend.teams_structures import (
    AddTeamMemberRequest,
    BannerUploadError,
    KeycloakM2MDisabledError,
    RemoveTeamMemberResponse,
    Team,
    TeamMember,
    TeamMembershipSyncError,
    TeamNotFoundError,
    TeamOwnerConstraintError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
)

router = APIRouter(tags=["Teams"])


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


@router.get(
    "/teams",
    response_model=list[Team],
    response_model_exclude_none=True,
    summary="List teams the user has access to",
)
async def list_teams(user: KeycloakUser = Depends(get_current_user)) -> list[Team]:
    return await list_teams_from_service(user)


@router.get(
    "/teams/{team_id}",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Get a specific team by ID",
)
async def get_team(
    team_id: Annotated[TeamId, Path()],
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await get_team_by_id_from_service(user, team_id)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamWithPermissions,
    response_model_exclude_none=True,
    summary="Update a specific team metadata",
)
async def update_team(
    team_id: Annotated[TeamId, Path()],
    request: UpdateTeamRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamWithPermissions:
    return await update_team_from_service(user, team_id, request)


@router.post(
    "/teams/{team_id}/banner",
    status_code=204,
    summary="Upload team banner image",
)
async def upload_team_banner(
    team_id: Annotated[TeamId, Path()],
    file: UploadFile = File(
        ..., description="Banner image file (max 5MB, JPEG/PNG/WebP)"
    ),
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await upload_team_banner_from_service(user, team_id, file)


@router.get(
    "/teams/{team_id}/members",
    response_model=list[TeamMember],
    response_model_exclude_none=True,
    summary="List members of a specific team",
)
async def list_team_members(
    team_id: Annotated[TeamId, Path()],
    user: KeycloakUser = Depends(get_current_user),
) -> list[TeamMember]:
    return await list_team_members_from_service(user, team_id)


@router.post(
    "/teams/{team_id}/members",
    status_code=204,
    summary="Add a member to a team",
)
async def add_team_member(
    team_id: Annotated[TeamId, Path()],
    request: AddTeamMemberRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await add_team_member_from_service(user, team_id, request)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    status_code=202,
    response_model=RemoveTeamMemberResponse,
    summary="Remove a member from a team and enqueue session purge",
)
async def remove_team_member(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    user: KeycloakUser = Depends(get_current_user),
) -> RemoveTeamMemberResponse:
    return await remove_team_member_from_service(user, team_id, user_id)


@router.patch(
    "/teams/{team_id}/members/{user_id}",
    status_code=204,
    summary="Update a team member role",
)
async def update_team_member(
    team_id: Annotated[TeamId, Path()],
    user_id: Annotated[str, Path(min_length=1)],
    request: UpdateTeamMemberRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await update_team_member_from_service(user, team_id, user_id, request)
