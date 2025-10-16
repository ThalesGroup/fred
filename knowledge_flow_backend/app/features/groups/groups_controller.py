from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, get_current_user

from app.features.groups.groups_service import GroupSummary
from app.features.groups.groups_service import list_groups as list_groups_from_service

router = APIRouter(tags=["Groups"])


@router.get(
    "/groups",
    response_model=list[GroupSummary],
    response_model_exclude_none=True,
    summary="List groups registered in Keycloak.",
)
async def list_groups(_current_user: KeycloakUser = Depends(get_current_user)) -> list[GroupSummary]:
    return await list_groups_from_service()
