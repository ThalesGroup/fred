from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, status
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.users_service import (
    create_user as create_user_from_service,
)
from control_plane_backend.users_service import (
    delete_user as delete_user_from_service,
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


@router.get(
    "/user",
    summary="Temporary bouchon endpoint to get a user.",
)
async def get_user_details(
    user: KeycloakUser = Depends(get_current_user),
) -> dict[str, str]:
    return {"personalTeamId": "personal"}
