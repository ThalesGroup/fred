from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, get_current_user

from app.features.users.users_service import UserSummary
from app.features.users.users_service import list_users as list_users_from_service

router = APIRouter(tags=["Users"])


@router.get(
    "/users",
    response_model=list[UserSummary],
    response_model_exclude_none=True,
    tags=["Users"],
    summary="List users registered in Keycloak.",
)
async def list_users(user: KeycloakUser = Depends(get_current_user)) -> list[UserSummary]:
    return await list_users_from_service(user)
