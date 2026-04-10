from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from fred_core import (
    Action,
    KeycloackDisabled,
    KeycloakUser,
    Resource,
    authorize,
    create_keycloak_admin,
)
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakDeleteError, KeycloakGetError, KeycloakPostError

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.users_structures import (
    CreateUserRequest,
    KeycloakM2MUserOperationDisabledError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserSummary,
)

logger = logging.getLogger(__name__)

_USER_PAGE_SIZE = 200


def _get_keycloak_admin() -> KeycloakAdmin | KeycloackDisabled:
    """Build the Keycloak admin client from Control Plane security settings."""
    app_context = ApplicationContext.get_instance()
    return create_keycloak_admin(app_context.configuration.security.m2m)


def _get_keycloak_admin_for_user_operations() -> KeycloakAdmin:
    """Return a Keycloak admin client or raise if M2M is disabled."""
    admin = _get_keycloak_admin()
    if isinstance(admin, KeycloackDisabled):
        raise KeycloakM2MUserOperationDisabledError()
    return admin


@authorize(Action.READ, Resource.USER)
async def list_users(_current_user: KeycloakUser) -> list[UserSummary]:
    """Return all users as lightweight summaries."""
    admin = _get_keycloak_admin()
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty user list.")
        return []

    raw_users = await _fetch_all_users(admin)
    summaries: list[UserSummary] = []

    for raw_user in raw_users:
        try:
            summaries.append(UserSummary.from_raw_user(raw_user))
        except ValueError:
            logger.debug("Skipping Keycloak user without identifier: %s", raw_user)

    return summaries


@authorize(Action.CREATE, Resource.USER)
async def create_user(
    _current_user: KeycloakUser,
    request: CreateUserRequest,
) -> UserSummary:
    """Create a user in Keycloak and return the created summary."""
    admin = _get_keycloak_admin_for_user_operations()

    try:
        user_id = await admin.a_create_user(
            request.to_keycloak_payload(), exist_ok=False
        )
    except KeycloakPostError as exc:
        if exc.response_code == 409:
            raise UserAlreadyExistsError(request.username) from exc
        raise

    raw_user = await admin.a_get_user(user_id)
    return UserSummary.from_raw_user(raw_user)


@authorize(Action.DELETE, Resource.USER)
async def delete_user(_current_user: KeycloakUser, user_id: str) -> None:
    """Delete a user in Keycloak by identifier."""
    admin = _get_keycloak_admin_for_user_operations()

    try:
        await admin.a_delete_user(user_id)
    except KeycloakDeleteError as exc:
        if exc.response_code == 404:
            raise UserNotFoundError(user_id) from exc
        raise


async def get_users_by_ids(user_ids: Iterable[str]) -> dict[str, UserSummary]:
    """
    Retrieve user summaries for the provided ids.
    Falls back to id-only summaries when Keycloak is unavailable or user is missing.
    """
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}

    admin = _get_keycloak_admin()
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning fallback users.")
        return {}

    ordered_ids = sorted(unique_ids)
    coroutines = {user_id: admin.a_get_user(user_id) for user_id in ordered_ids}
    raw_results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    summaries: dict[str, UserSummary] = {}
    for user_id, result in zip(ordered_ids, raw_results):
        if isinstance(result, BaseException):
            if isinstance(result, KeycloakGetError) and result.response_code == 404:
                logger.debug("User %s not found in Keycloak.", user_id)
                summaries[user_id] = UserSummary(id=user_id)
                continue
            raise result

        if not isinstance(result, dict):
            logger.debug("Unexpected payload for user %s: %r", user_id, result)
            continue

        try:
            summaries[user_id] = UserSummary.from_raw_user(result)
        except ValueError:
            logger.debug("User %s payload missing identifier: %s", user_id, result)

    return summaries


async def _fetch_all_users(admin: KeycloakAdmin) -> list[dict]:
    users: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_users({"first": offset, "max": _USER_PAGE_SIZE})
        if not batch:
            break

        users.extend(batch)
        if len(batch) < _USER_PAGE_SIZE:
            break

        offset += _USER_PAGE_SIZE

    logger.info("Collected %d users from Keycloak.", len(users))
    return users
