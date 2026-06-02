from __future__ import annotations

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId, personal_team_id

from control_plane_backend.teams.schemas import Team, TeamWithPermissions


async def build_personal_team(
    user: KeycloakUser, personal_max_resources_storage_size: int | None
) -> TeamWithPermissions:
    """Build the reserved personal team using the standard team DTOs.

    Why this function exists:
    - the personal team is a first-class product contract but is not backed by a
      Keycloak group
    - centralizing its shape avoids duplicating the same synthetic team payload
      across bootstrap, `/teams`, and temporary helper endpoints

    How to use it:
    - call from control-plane services that need the personal team as a normal
      selectable `TeamWithPermissions`

    Example:
    - `personal_team = await build_personal_team(user, personal_limit)`
    """
    import logging
    from uuid import UUID

    from fred_core.users.store.postgres_user_store import get_user_store

    logger = logging.getLogger(__name__)

    try:
        user_uuid = UUID(_user.uid)
    except ValueError:
        import uuid as _uuid_mod

        user_uuid = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_DNS, f"dev-user-{_user.uid}")

    current_size = 0
    try:
        user_store = get_user_store()
        user_row = await user_store.find_user_by_id(user_uuid)
        if user_row:
            current_size = user_row.current_resources_storage_size or 0
    except Exception as e:
        logger.warning(f"Failed to fetch personal space storage size: {e}")

    return TeamWithPermissions(
        id=personal_team_id(user.uid),
        name="Equipe personnelle",
        member_count=1,
        is_private=True,
        owners=[],
        permissions=[
            TeamPermission("can_read"),
            TeamPermission("can_update_resources"),
            TeamPermission("can_update_agents"),
        ],
        max_resources_storage_size=personal_max_resources_storage_size,
        current_resources_storage_size=current_size,
    )


async def get_system_team(
    user: KeycloakUser, team_id: TeamId, personal_max_resources_storage_size: int | None
) -> TeamWithPermissions | None:
    """Resolve one reserved system team by id.

    Why this function exists:
    - reserved teams such as `personal` should materialize through one control-
      plane-owned resolver instead of ad hoc `if personal` branches in multiple
      endpoints
    - the same mechanism can later host additional reserved teams such as an
      admin workspace without changing the public team DTOs

    How to use it:
    - call from team-facing services before consulting collaborative-team
      backends such as Keycloak

    Example:
    - `team = await get_system_team(user, team_id, personal_limit)`
    """

    if team_id in (personal_team_id(user.uid), TeamId("personal")):
        return await build_personal_team(user, personal_max_resources_storage_size)
    return None


async def list_system_teams(
    user: KeycloakUser, personal_max_resources_storage_size: int | None
) -> list[TeamWithPermissions]:
    """List all reserved system teams visible to the current user.

    Why this function exists:
    - control-plane should expose selectable system teams through the same team
      discovery surface as collaborative teams

    How to use it:
    - call from `/teams` and bootstrap builders, then merge with collaborative
      teams by id

    Example:
    - `teams = await list_system_teams(user, personal_limit)`
    """

    return [await build_personal_team(user, personal_max_resources_storage_size)]


def to_team_summary(team: TeamWithPermissions) -> Team:
    """Drop permissions from a resolved system team for list endpoints.

    Why this function exists:
    - `/teams` returns `Team`, while bootstrap and `/teams/{team_id}` use
      `TeamWithPermissions`

    How to use it:
    - call when one list surface should expose a reserved team through the
      shared `Team` model

    Example:
    - `payload = to_team_summary(build_personal_team(user))`
    """

    return Team(**team.model_dump(exclude={"permissions"}))
