from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.teams.teams_service import list_teams as list_teams_from_service
from knowledge_flow_backend.features.teams.teams_structures import Team

router = APIRouter(tags=["Teams"])


@router.get(
    "/teams",
    response_model=list[Team],
    response_model_exclude_none=True,
    summary="List teams the user has access to",
)
async def list_teams(user: KeycloakUser = Depends(get_current_user)) -> list[Team]:
    return await list_teams_from_service(user)
