import logging
import uuid as _uuid_mod
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Path, status
from fastapi.responses import JSONResponse
from fred_core import (
    BaseUserStore,
    GcuVersionsType,
    KeycloakUser,
    get_current_user,
    get_current_user_without_gcu,
    require_admin,
)
from fred_core.common import personal_team_id
from fred_core.users.store.postgres_user_store import get_user_store
from pydantic import BaseModel

from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)
from control_plane_backend.teams.schemas import (
    TeamWithPermissions,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.users.dependencies import (
    UserServiceDependencies,
    get_user_service_dependencies,
)
from control_plane_backend.users.schemas import (
    CreateUserRequest,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserSummary,
)
from control_plane_backend.users.service import (
    create_user as create_user_from_service,
)
from control_plane_backend.users.service import (
    delete_user as delete_user_from_service,
)
from control_plane_backend.users.service import (
    find_user_details_by_id,
    update_gcu_validation,
    upsert_user_from_jwt,
)
from control_plane_backend.users.service import (
    get_user_by_id as get_user_by_id_from_service,
)
from control_plane_backend.users.service import (
    list_users as list_users_from_service,
)

router = APIRouter(tags=["Users"])
logger = logging.getLogger(__name__)
UserDependencies = Annotated[
    UserServiceDependencies,
    Depends(get_user_service_dependencies),
]
TeamDependencies = Annotated[
    TeamServiceDependencies,
    Depends(get_team_service_dependencies),
]


def _parse_user_uuid(user: KeycloakUser) -> UUID:
    try:
        return UUID(user.uid)
    except ValueError:
        return _uuid_mod.uuid5(_uuid_mod.NAMESPACE_DNS, f"dev-user-{user.uid}")


def register_exception_handlers(app: FastAPI) -> None:
    """Register user-domain exception handlers."""

    @app.exception_handler(UserAlreadyExistsError)
    async def user_already_exists_handler(
        _request,
        exc: UserAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(_request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})


@router.get(
    "/users",
    response_model=list[UserSummary],
    response_model_exclude_none=True,
    summary="List users.",
)
async def list_users(
    deps: UserDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[UserSummary]:
    require_admin(user)
    return await list_users_from_service(user, deps)


@router.get(
    "/users/{user_id}",
    response_model=UserSummary,
    response_model_exclude_none=True,
    summary="Get a user by id.",
)
async def get_user_by_id(
    user_id: Annotated[str, Path(min_length=1)],
    deps: UserDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> UserSummary:
    require_admin(user)
    return await get_user_by_id_from_service(user_id, deps)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserSummary,
    response_model_exclude_none=True,
    summary="Create a user.",
)
async def create_user(
    request: CreateUserRequest,
    deps: UserDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> UserSummary:
    require_admin(user)
    return await create_user_from_service(user, request, deps)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user.",
)
async def delete_user(
    user_id: Annotated[str, Path(min_length=1)],
    deps: UserDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    require_admin(user)
    await delete_user_from_service(user, user_id, deps)


class UserDetails(BaseModel):
    cguValidated: GcuVersionsType | None
    personalTeam: TeamWithPermissions
    currentUser: UserSummary | None = None


@router.get(
    "/user",
    summary="Return user informations.",
)
async def get_user_details(
    team_deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user_without_gcu),
    user_store: BaseUserStore = Depends(get_user_store),
) -> UserDetails:
    user_uuid = _parse_user_uuid(user)
    user_details = await find_user_details_by_id(user_uuid, user_store)
    personal_team = await get_team_by_id_from_service(
        user, personal_team_id(user.uid), team_deps
    )
    return UserDetails(
        cguValidated=user_details.gcuVersionAccepted if user_details else None,
        personalTeam=personal_team,
        currentUser=UserSummary(id=user.uid, username=user.username, email=user.email),
    )


@router.post("/gcu")
async def validate_gcu(
    deps: UserDependencies,
    user: KeycloakUser = Depends(get_current_user_without_gcu),
    user_store: BaseUserStore = Depends(get_user_store),
) -> None:
    await upsert_user_from_jwt(user, deps)
    user_uuid = _parse_user_uuid(user)
    await update_gcu_validation(user_uuid, user_store, deps)
