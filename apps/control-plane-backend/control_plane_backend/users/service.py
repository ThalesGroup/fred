from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Optional
from uuid import UUID

from fred_core import (
    BaseUserStore,
    KeycloackDisabled,
    KeycloakUser,
)
from fred_core.users import GcuVersionsType, UserRow
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakDeleteError, KeycloakGetError, KeycloakPostError

from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import (
    CreateUserRequest,
    KeycloakM2MUserOperationDisabledError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserSummary,
)

logger = logging.getLogger(__name__)

_USER_PAGE_SIZE = 200


def _get_keycloak_admin(
    deps: UserServiceDependencies,
) -> KeycloakAdmin | KeycloackDisabled:
    """
    Build the Keycloak admin client from explicit user-service dependencies.

    Why this function exists:
    - user administration should resolve security collaborators from injected
      dependencies instead of the global application context

    How to use it:
    - call after resolving `UserServiceDependencies`
    - use the returned client for Keycloak reads or writes

    Example:
    - `admin = _get_keycloak_admin(user_deps)`
    """
    return deps.create_keycloak_admin_client()


def _get_keycloak_admin_for_user_operations(
    deps: UserServiceDependencies,
) -> KeycloakAdmin:
    """
    Return a Keycloak admin client or raise if M2M user writes are disabled.

    Why this function exists:
    - create/delete user flows must fail with a clear domain error when M2M
      credentials are not configured

    How to use it:
    - call from write operations after resolving explicit user dependencies
    - catch `KeycloakM2MUserOperationDisabledError` at the API layer

    Example:
    - `admin = _get_keycloak_admin_for_user_operations(user_deps)`
    """
    admin = _get_keycloak_admin(deps)
    if isinstance(admin, KeycloackDisabled):
        raise KeycloakM2MUserOperationDisabledError()
    return admin


async def list_users(
    _current_user: KeycloakUser,
    deps: UserServiceDependencies,
) -> list[UserSummary]:
    """
    Return all Keycloak users as lightweight control-plane summaries.

    Why this function exists:
    - the admin API needs one typed projection of Keycloak users without
      exposing raw provider payloads to the HTTP layer

    How to use it:
    - pass request-scoped `UserServiceDependencies` from the API layer
    - the function returns an empty list when Keycloak M2M is disabled

    Example:
    - `users = await list_users(current_user, deps)`
    """
    admin = _get_keycloak_admin(deps)
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


async def create_user(
    _current_user: KeycloakUser,
    request: CreateUserRequest,
    deps: UserServiceDependencies,
) -> UserSummary:
    """
    Create one Keycloak user and return the created control-plane summary.

    Why this function exists:
    - temporary admin bootstrap flows still need a typed, explicit user-create
      use case while the broader platform migration continues

    How to use it:
    - pass the authenticated admin user, the validated request payload, and the
      request-scoped dependency bundle
    - expect `UserAlreadyExistsError` on username conflicts

    Example:
    - `summary = await create_user(current_user, request, deps)`
    """
    admin = _get_keycloak_admin_for_user_operations(deps)

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


async def delete_user(
    _current_user: KeycloakUser,
    user_id: str,
    deps: UserServiceDependencies,
) -> None:
    """
    Delete one Keycloak user by identifier.

    Why this function exists:
    - temporary admin cleanup flows need one explicit deletion use case with
      typed error mapping

    How to use it:
    - pass the authenticated admin user, target user id, and request-scoped
      dependencies from the API layer
    - expect `UserNotFoundError` when the Keycloak subject does not exist

    Example:
    - `await delete_user(current_user, "user-123", deps)`
    """
    admin = _get_keycloak_admin_for_user_operations(deps)

    try:
        await admin.a_delete_user(user_id)
    except KeycloakDeleteError as exc:
        if exc.response_code == 404:
            raise UserNotFoundError(user_id) from exc
        raise


async def get_users_by_ids(
    user_ids: Iterable[str],
    deps: UserServiceDependencies,
) -> dict[str, UserSummary]:
    """
    Retrieve user summaries for a set of ids with graceful Keycloak fallbacks.

    Why this function exists:
    - team and product flows often need user display data, but they should not
      break when Keycloak is unavailable or some users are missing

    How to use it:
    - pass any iterable of user ids; empty or falsey ids are ignored
    - missing Keycloak users fall back to `UserSummary(id=...)`

    Example:
    - `summaries = await get_users_by_ids(["u-1", "u-2"], deps)`
    """
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}

    admin = _get_keycloak_admin(deps)
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
    """
    Fetch every Keycloak user page using the configured page size.

    Why this function exists:
    - the public user-list endpoint needs one internal paginator that hides the
      provider-specific paging loop

    How to use it:
    - pass an initialized Keycloak admin client
    - the helper continues until a short page or empty page is returned

    Example:
    - `raw_users = await _fetch_all_users(admin)`
    """
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


async def find_user_details_by_id(
    user_id: UUID,
    user_store: BaseUserStore,
) -> Optional[UserRow]:
    """
    Load one persisted user row from the shared user store.

    Why this function exists:
    - helper endpoints still need access to stored GCU acceptance metadata
      without duplicating store calls at each route

    How to use it:
    - pass the UUID-backed user id and an explicit `BaseUserStore`
    - expect `None` when no persisted row exists

    Example:
    - `row = await find_user_details_by_id(user_uuid, user_store)`
    """
    return await user_store.find_user_by_id(user_id)


async def update_gcu_validation(
    user_id: UUID,
    user_store: BaseUserStore,
    deps: UserServiceDependencies,
) -> None:
    """
    Persist the active GCU version for one UUID-backed user.

    Why this function exists:
    - control-plane stores GCU acceptance in the shared Fred user store, but
      the active version comes from control-plane configuration

    How to use it:
    - pass the persisted user id, the injected user store, and optional
      request-scoped user dependencies
    - the function becomes a no-op when no GCU version is configured

    Example:
    - `await update_gcu_validation(user_uuid, user_store, deps)`
    """
    cfg = deps.configuration
    if cfg.app.gcu_version is None:
        return

    await user_store.update_gcu_version(user_id, GcuVersionsType(cfg.app.gcu_version))
