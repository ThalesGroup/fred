import logging

from fred_core import Action, KeycloakUser, Resource, authorize
from keycloak import KeycloakAdmin
from pydantic import BaseModel

from app.security.keycloack_admin_client import create_keycloak_admin

logger = logging.getLogger(__name__)

_USER_PAGE_SIZE = 200


class UserSummary(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


@authorize(Action.READ, Resource.USER)
async def list_users(_curent_user: KeycloakUser) -> list[UserSummary]:
    admin = create_keycloak_admin()
    if not admin:
        logger.info("Keycloak admin client not configured; returning empty user list.")
        return []

    raw_users = await _fetch_all_users(admin)
    summaries: list[UserSummary] = []

    for raw_user in raw_users:
        user_id = raw_user.get("id")
        if not user_id:
            logger.debug("Skipping Keycloak user without identifier: %s", raw_user)
            continue
        summaries.append(
            UserSummary(
                id=user_id,
                first_name=_sanitize(raw_user.get("firstName")),
                last_name=_sanitize(raw_user.get("lastName")),
                username=_sanitize(raw_user.get("username")),
            )
        )

    return summaries


def _sanitize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
