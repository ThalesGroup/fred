import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from fred_core import Action, KeycloakUser, Resource, authorize
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from app.features.users.users_structures import UserSummary
from app.security.keycloack_admin_client import create_keycloak_admin

logger = logging.getLogger(__name__)

_USER_PAGE_SIZE = 200


@authorize(Action.READ, Resource.USER)
async def list_users(_curent_user: KeycloakUser) -> list[UserSummary]:
    admin = create_keycloak_admin()
    if not admin:
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


def get_users_by_ids(user_ids: Iterable[str]) -> dict[str, UserSummary]:
    """
    Retrieve user summaries for the provided ids.
    Falls back to id-only summaries when Keycloak is unavailable or the user is missing.
    """
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}

    admin = create_keycloak_admin()
    if not admin:
        logger.info("Keycloak admin client not configured; returning fallback users.")
        return {user_id: UserSummary(id=user_id) for user_id in unique_ids}

    ordered_ids = sorted(unique_ids)

    async def _collect() -> dict[str, UserSummary]:
        coroutines = {user_id: admin.a_get_user(user_id) for user_id in ordered_ids}
        raw_results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

        summaries: dict[str, UserSummary] = {}
        for user_id, result in zip(ordered_ids, raw_results):
            if isinstance(result, BaseException):
                if isinstance(result, KeycloakGetError) and result.response_code == 404:
                    logger.debug("User %s not found in Keycloak.", user_id)
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

    summaries = asyncio.run(_collect())

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
