# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The single authorization chokepoint for every KPI preset: the router calls
`resolve_kpi_scope` before any handler; handlers only read `KpiScope.team_ids`
and `KpiScope.user_ids`."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import HTTPException, Request
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.common import TeamId, is_personal_team_id

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.user_filter import (
    AnalyticsUserFilter,
    ResolvedUserFilter,
    resolve_user_filter,
)

MAX_SCOPE_TEAMS = 200


@dataclass(frozen=True)
class KpiScope:
    """Authorized scope: empty = platform-wide, else every query MUST filter on
    `dims.team_id IN team_ids` (the resolver authorizes, it does not filter)."""

    team_ids: tuple[TeamId, ...] = ()
    # Set only by a user filter: every query MUST also filter on these users.
    user_filter: ResolvedUserFilter | None = None

    @property
    def user_ids(self) -> tuple[str, ...] | None:
        return self.user_filter.match.user_ids if self.user_filter else None


async def resolve_kpi_scope(
    request: Request,
    user: KeycloakUser,
    team_ids: Sequence[TeamId],
    *,
    self_scoped: bool = False,
    user_filter: AnalyticsUserFilter | None = None,
) -> KpiScope:
    """No team: org `can_observe_platform`. Teams: observers may read any real
    teams, others need `can_read_analytics` (team admin) on each; personal
    spaces always need it, so observers never read a private space.
    A user filter needs `can_observe_platform` too. `self_scoped`: no check."""

    if self_scoped:
        return KpiScope()
    scope = await _team_scope(request, user, team_ids)
    if user_filter is None:
        return scope
    # Account attributes are platform data: a team admin never filters on them.
    # Without teams, `_team_scope` has just checked it.
    if scope.team_ids:
        rebac = get_application_container(request).get_rebac_engine()
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
    match = await resolve_user_filter(user_filter)
    return KpiScope(
        team_ids=scope.team_ids,
        user_filter=ResolvedUserFilter(filter=user_filter, match=match),
    )


async def _team_scope(
    request: Request, user: KeycloakUser, team_ids: Sequence[TeamId]
) -> KpiScope:
    unique = tuple(dict.fromkeys(TeamId(str(t)) for t in team_ids))
    if len(unique) > MAX_SCOPE_TEAMS:
        raise HTTPException(
            status_code=400,
            detail=f"at most {MAX_SCOPE_TEAMS} teams can be selected",
        )

    rebac = get_application_container(request).get_rebac_engine()
    if not unique:
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
        return KpiScope()

    if not any(is_personal_team_id(str(t)) for t in unique) and (
        await rebac.has_user_permission(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
    ):
        return KpiScope(team_ids=unique)

    await asyncio.gather(
        *(
            rebac.check_user_permission_or_raise(
                user, TeamPermission.CAN_READ_ANALYTICS, str(team_id)
            )
            for team_id in unique
        )
    )
    return KpiScope(team_ids=unique)
