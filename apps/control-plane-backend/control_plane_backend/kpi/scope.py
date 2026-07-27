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

"""
The single authorization chokepoint for every KPI preset (OBSERV-02 v3,
`KPI-ANALYTICS-RFC.md` §2.3/§2.4).

Before v3, each preset handler re-implemented the same three-line
`check_user_permission_or_raise(CAN_OBSERVE_PLATFORM)` call. `resolve_kpi_scope`
replaces every one of those copies with one call, made once by the router
(`api.py`) before any handler runs. Preset handlers never check authorization
themselves — they only ever read `KpiScope.team_id` to decide whether to add
a `dims.team_id` filter to their query.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.common import TeamId

from control_plane_backend.app.dependencies import get_application_container


@dataclass(frozen=True)
class KpiScope:
    """The authorized scope a KPI preset query is allowed to read.

    `team_id is None` means platform-wide — the caller holds
    `can_observe_platform` on the org (or `can_manage_platform`, for the
    admin-only presets — see `resolve_kpi_scope`). Otherwise the caller holds
    `can_read_members` on that one team, and every query this scope backs
    MUST filter on `dims.team_id == team_id`; `resolve_kpi_scope` only proves
    the caller may ask, it does not filter the query for them.
    """

    team_id: TeamId | None


async def resolve_kpi_scope(
    request: Request,
    user: KeycloakUser,
    team_id: TeamId | None,
    *,
    platform_admin_only: bool = False,
    self_scoped: bool = False,
) -> KpiScope:
    """Authorize a KPI preset request and return its resolved scope.

    `team_id=None` requires `can_observe_platform` on the org (the original,
    pre-v3 behavior — unchanged), UNLESS the preset is in the platform-wide
    admin-only section (§2.4/§2.5, e.g. `storage_by_team`'s cross-team ranked
    view), in which case it requires `can_manage_platform` instead — the same
    permission already gating `/admin/capabilities` and `scope=platform` task
    queries, not a new one. A `team_id` requires `can_read_members` on that
    team: the same permission the task bus's `scope=team` Activités view
    already requires (`fred_core.tasks.authz`), so "can this user see this
    team's operational data" has one shared vocabulary across KPI presets and
    tasks, not two. `platform_admin_only` never affects the team-scoped check.

    `self_scoped` (§2.4 "Personal presets (Page 3)") is checked first and
    skips OpenFGA entirely: the preset's own query already filters on
    `dims.user_id == user.uid`, so any authenticated user may call it — the
    same "my own data" contract `team_id`/`platform_admin_only` never apply
    to. Router-level validation (`api.py`) already rejects a `team_id` for
    these (they are never `team_scopable`), so `team_id` is guaranteed None
    here in practice; the check below does not depend on that guarantee.
    """

    if self_scoped:
        return KpiScope(team_id=None)

    rebac = get_application_container(request).get_rebac_engine()
    if team_id is None:
        permission = (
            OrganizationPermission.CAN_MANAGE_PLATFORM
            if platform_admin_only
            else OrganizationPermission.CAN_OBSERVE_PLATFORM
        )
        await rebac.check_user_permission_or_raise(user, permission, ORGANIZATION_ID)
        return KpiScope(team_id=None)
    await rebac.check_user_permission_or_raise(
        user, TeamPermission.CAN_READ_MEMEBERS, str(team_id)
    )
    return KpiScope(team_id=team_id)
