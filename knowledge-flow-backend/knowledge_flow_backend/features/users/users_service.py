import asyncio
import logging
from collections.abc import Iterable

from fred_core import Action, KeycloackDisabled, KeycloakUser, Resource, authorize, create_keycloak_admin
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.features.users.users_structures import UserSummary

logger = logging.getLogger(__name__)

_USER_PAGE_SIZE = 200


@authorize(Action.READ, Resource.USER)
async def list_users(_curent_user: KeycloakUser) -> list[UserSummary]:
    admin = create_keycloak_admin(get_configuration().security.m2m)
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


async def get_users_by_ids(user_ids: Iterable[str]) -> dict[str, UserSummary]:
    """
    Retrieve user summaries for the provided ids.
    Falls back to id-only summaries when Keycloak is unavailable or the user is missing.
    """
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}

    admin = create_keycloak_admin(get_configuration().security.m2m)
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
                # Returning unkown user so that it can be handled throug UI (like removed from a team)
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
