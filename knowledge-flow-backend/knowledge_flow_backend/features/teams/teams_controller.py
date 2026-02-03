from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, Request
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.teams.team_id import TeamId
from knowledge_flow_backend.features.teams.teams_service import add_team_member as add_team_member_from_service
from knowledge_flow_backend.features.teams.teams_service import get_team_by_id as get_team_by_id_from_service
from knowledge_flow_backend.features.teams.teams_service import list_team_members as list_team_members_from_service
from knowledge_flow_backend.features.teams.teams_service import list_teams as list_teams_from_service
from knowledge_flow_backend.features.teams.teams_service import remove_team_member as remove_team_member_from_service
from knowledge_flow_backend.features.teams.teams_service import update_team as update_team_from_service
from knowledge_flow_backend.features.teams.teams_service import update_team_member as update_team_member_from_service
from knowledge_flow_backend.features.teams.teams_structures import AddTeamMemberRequest, Team, TeamMember, TeamNotFoundError, TeamUpdate, UpdateTeamMemberRequest

router = APIRouter(tags=["Teams"])


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for team-related exceptions."""

    @app.exception_handler(TeamNotFoundError)
    async def team_not_found_handler(request: Request, exc: TeamNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})


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
    response_model=Team,
    response_model_exclude_none=True,
    summary="Get a specific team by ID",
)
async def get_team(team_id: Annotated[TeamId, Path()], user: KeycloakUser = Depends(get_current_user)) -> Team:
    return await get_team_by_id_from_service(user, team_id)


@router.patch(
    "/teams/{team_id}",
    response_model=Team,
    response_model_exclude_none=True,
    summary="Update a team",
)
async def update_team(team_id: Annotated[TeamId, Path()], update_data: TeamUpdate, user: KeycloakUser = Depends(get_current_user)) -> Team:
    return await update_team_from_service(user, team_id, update_data)


@router.get(
    "/teams/{team_id}/members",
    response_model=list[TeamMember],
    response_model_exclude_none=True,
    summary="List members of a specific team",
)
async def list_team_members(team_id: Annotated[TeamId, Path()], user: KeycloakUser = Depends(get_current_user)) -> list[TeamMember]:
    return await list_team_members_from_service(user, team_id)


@router.post(
    "/teams/{team_id}/members",
    status_code=204,
    summary="Add a member to a team",
)
async def add_team_member(team_id: Annotated[TeamId, Path()], request: AddTeamMemberRequest, user: KeycloakUser = Depends(get_current_user)) -> None:
    await add_team_member_from_service(user, team_id, request)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    status_code=204,
    summary="Remove a member from a team",
)
async def remove_team_member(team_id: Annotated[TeamId, Path()], user_id: Annotated[str, Path()], user: KeycloakUser = Depends(get_current_user)) -> None:
    await remove_team_member_from_service(user, team_id, user_id)


@router.patch(
    "/teams/{team_id}/members/{user_id}",
    status_code=204,
    summary="Update a team member's role",
)
async def update_team_member(team_id: Annotated[TeamId, Path()], user_id: Annotated[str, Path()], request: UpdateTeamMemberRequest, user: KeycloakUser = Depends(get_current_user)) -> None:
    await update_team_member_from_service(user, team_id, user_id, request)
