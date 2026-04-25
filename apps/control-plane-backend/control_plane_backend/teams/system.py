from __future__ import annotations

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import PERSONAL_TEAM_ID, TeamId

from control_plane_backend.teams.schemas import Team, TeamWithPermissions


def build_personal_team(_user: KeycloakUser) -> TeamWithPermissions:
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
    - `personal_team = build_personal_team(user)`
    """

    return TeamWithPermissions(
        id=PERSONAL_TEAM_ID,
        name="Equipe personnelle",
        member_count=1,
        is_private=True,
        owners=[],
        permissions=[
            TeamPermission("can_read"),
            TeamPermission("can_update_resources"),
            TeamPermission("can_update_agents"),
        ],
    )


def get_system_team(user: KeycloakUser, team_id: TeamId) -> TeamWithPermissions | None:
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
    - `team = get_system_team(user, team_id)`
    """

    if team_id == PERSONAL_TEAM_ID:
        return build_personal_team(user)
    return None


def list_system_teams(user: KeycloakUser) -> list[TeamWithPermissions]:
    """List all reserved system teams visible to the current user.

    Why this function exists:
    - control-plane should expose selectable system teams through the same team
      discovery surface as collaborative teams

    How to use it:
    - call from `/teams` and bootstrap builders, then merge with collaborative
      teams by id

    Example:
    - `teams = list_system_teams(user)`
    """

    return [build_personal_team(user)]


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
