import logging
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
)
from fred_core.common import PERSONAL_TEAM_ID
from fred_core.users.store.postgres_user_store import get_user_store
from pydantic import BaseModel

from control_plane_backend.teams_service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams_structures import (
    TeamWithPermissions,
)
from control_plane_backend.users_service import (
    create_user as create_user_from_service,
)
from control_plane_backend.users_service import (
    delete_user as delete_user_from_service,
)
from control_plane_backend.users_service import (
    find_user_details_by_id,
    update_gcu_validation,
)
from control_plane_backend.users_service import (
    list_users as list_users_from_service,
)
from control_plane_backend.users_structures import (
    CreateUserRequest,
    KeycloakM2MUserOperationDisabledError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserSummary,
)

router = APIRouter(tags=["Users"])
logger = logging.getLogger(__name__)


def _parse_user_uuid(user: KeycloakUser) -> UUID | None:
    """
    Return the persisted user UUID when the authenticated subject uses one.

    Why this function exists:
    - control-plane now persists GCU acceptance in the shared `fred_core.users`
      store, but no-security mode still injects a mock admin with `uid="admin"`
    - helper endpoints must tolerate that mock subject without redefining the
      personal-team contract

    How to use it:
    - call before reading or writing GCU state; handle `None` as "no persisted
      user row available for this subject"

    Example:
    - `user_uuid = _parse_user_uuid(user)`
    """
    try:
        return UUID(user.uid)
    except ValueError:
        return None


def register_exception_handlers(app: FastAPI) -> None:
    """Register user-domain exception handlers."""

    @app.exception_handler(KeycloakM2MUserOperationDisabledError)
    async def keycloak_disabled_for_users_handler(
        _request,
        exc: KeycloakM2MUserOperationDisabledError,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

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
    summary="List users registered in Keycloak.",
)
async def list_users(
    user: KeycloakUser = Depends(get_current_user),
) -> list[UserSummary]:
    return await list_users_from_service(user)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserSummary,
    response_model_exclude_none=True,
    summary="Temporary bootstrap endpoint to create a user.",
)
async def create_user(
    request: CreateUserRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> UserSummary:
    """Create a user in Keycloak for temporary bootstrap and testing flows."""
    return await create_user_from_service(user, request)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Temporary bootstrap endpoint to delete a user.",
)
async def delete_user(
    user_id: Annotated[str, Path(min_length=1)],
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """Delete a user in Keycloak for temporary bootstrap and testing flows."""
    await delete_user_from_service(user, user_id)


class UserDetails(BaseModel):
    cguValidated: GcuVersionsType | None
    personalTeam: TeamWithPermissions


@router.get(
    "/user",
    summary="Return user informations.",
)
async def get_user_details(
    user: KeycloakUser = Depends(get_current_user_without_gcu),
    user_store: BaseUserStore = Depends(get_user_store),
) -> UserDetails:
    """Return the personal team through the shared team resolver.

    Why this function exists:
    - this temporary helper endpoint must not duplicate personal-team shaping
      while the shell migrates away from it

    How to use it:
    - treat it as a temporary helper only; bootstrap should use
      `/frontend/bootstrap`
    """
    user_uuid = _parse_user_uuid(user)
    user_details = (
        await find_user_details_by_id(user_uuid, user_store)
        if user_uuid is not None
        else None
    )
    personal_team = await get_team_by_id_from_service(user, PERSONAL_TEAM_ID)

    return UserDetails(
        cguValidated=user_details.gcuVersionAccepted if user_details else None,
        personalTeam=personal_team,
    )


@router.post("/gcu")
async def validate_gcu(
    user: KeycloakUser = Depends(get_current_user_without_gcu),
    user_store: BaseUserStore = Depends(get_user_store),
) -> None:
    """
    Persist the current user's accepted GCU version when a persisted UUID exists.

    Why this function exists:
    - GCU acceptance must be writable before the stricter `get_current_user()`
      dependency starts enforcing it
    - no-security mode still uses a mock admin subject without a UUID-backed
      user row

    How to use it:
    - call after the user accepts the active GCU version; in no-security mode
      the endpoint becomes a no-op because there is no persisted user identity

    Example:
    - `POST /control-plane/v1/gcu`
    """
    user_uuid = _parse_user_uuid(user)
    if user_uuid is None:
        logger.info(
            "Skipping GCU persistence for subject %r because it is not UUID-backed.",
            user.uid,
        )
        return
    await update_gcu_validation(user_uuid, user_store)
