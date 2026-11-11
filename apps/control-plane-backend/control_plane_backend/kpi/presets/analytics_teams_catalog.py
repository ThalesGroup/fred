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

"""Teams offered by the analytics scope selector, with their member count.

Platform observers cannot list every team (`can_list_all_teams` excludes
them), so the selector reads this observer-gated preset instead. Scoped to
`team_ids`, it gives a team admin the member counts of their own teams.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId, is_personal_team_id
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import BaseModel

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.teams.service import team_member_counts


class AnalyticsTeamRow(BaseModel):
    team_id: str
    name: str
    member_count: int


class AnalyticsTeamsCatalogResponse(BaseModel):
    rows: list[AnalyticsTeamRow]


async def team_catalog(
    request: Request, team_ids: Sequence[TeamId] = ()
) -> list[AnalyticsTeamRow]:
    """The selected non-personal teams (all when none) sorted by name.
    Members are only counted for listed teams."""
    container = get_application_container(request)
    teams = [
        team
        for team in await container.get_team_metadata_store().list_all()
        if not is_personal_team_id(str(team.id))
    ]
    selected = set(team_ids)
    listed = [team for team in teams if not selected or team.id in selected]
    counts = await team_member_counts(
        container.get_rebac_engine(), [team.id for team in listed]
    )
    rows = [
        AnalyticsTeamRow(
            team_id=str(team.id), name=team.name, member_count=counts.get(team.id, 0)
        )
        for team in listed
    ]
    rows.sort(key=lambda row: row.name.casefold())
    return rows


async def query_analytics_teams_catalog(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
) -> AnalyticsTeamsCatalogResponse:
    # Authorization already resolved by the router; the period does not apply.
    del store, user, since, until
    return AnalyticsTeamsCatalogResponse(rows=await team_catalog(request, team_ids))


ANALYTICS_TEAMS_CATALOG_PRESET = PresetDef(
    name="analytics_teams_catalog",
    response_model=AnalyticsTeamsCatalogResponse,
    handler=query_analytics_teams_catalog,
    summary="Non-personal teams with their member count, for the analytics scope selector",
    team_scopable=True,
)
