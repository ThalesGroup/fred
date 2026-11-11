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

"""Overview tab headline: reach, volumes and cost, each against the previous period."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.presets.analytics_common import (
    SESSIONS,
    TEAM_SPACE,
    TURNS,
    VISITS,
    PeriodValue,
    Windows,
    distinct,
    doc_count,
    per_period,
    ratio,
    search,
    sub_value,
    token_aggs,
    token_totals,
    two_period_body,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import TOKEN_USAGE_FILTER


class AnalyticsOverviewResponse(BaseModel):
    visitors: PeriodValue
    active_users: PeriodValue
    active_teams: PeriodValue
    conversations: PeriodValue
    messages: PeriodValue
    cost_eur: PeriodValue
    cost_eur_per_active_user: PeriodValue
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def overview_body(
    windows: Windows, team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> dict:
    return two_period_body(
        windows,
        team_ids,
        [TURNS, VISITS, SESSIONS, TOKEN_USAGE_FILTER],
        {
            "turns": {
                "filter": TURNS,
                "aggs": {
                    "users": distinct("dims.user_id"),
                    "team_space": {
                        "filter": TEAM_SPACE,
                        "aggs": {"teams": distinct("dims.team_id")},
                    },
                },
            },
            "visits": {"filter": VISITS, "aggs": {"users": distinct("dims.user_id")}},
            "sessions": {"filter": SESSIONS},
            "tokens": token_aggs(),
        },
        user_ids=user_ids,
    )


async def query_analytics_overview(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
) -> AnalyticsOverviewResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request
    windows = Windows.of(since, until)
    response = await search(store, overview_body(windows, team_ids, user_ids))

    active_users = per_period(response, sub_value("turns", "users"))
    cost = per_period(response, lambda b: token_totals(b.get("tokens", {})).cost_eur)
    return AnalyticsOverviewResponse(
        visitors=per_period(response, sub_value("visits", "users")),
        active_users=active_users,
        active_teams=per_period(
            response,
            lambda b: float(
                b.get("turns", {}).get("team_space", {}).get("teams", {}).get("value")
                or 0
            ),
        ),
        conversations=per_period(response, doc_count("sessions")),
        messages=per_period(response, doc_count("turns")),
        cost_eur=cost,
        cost_eur_per_active_user=ratio(cost, active_users),
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_OVERVIEW_PRESET = PresetDef(
    name="analytics_overview",
    response_model=AnalyticsOverviewResponse,
    handler=query_analytics_overview,
    summary="Overview headline (visitors, active users, active teams, volumes, cost in EUR) for the period and the previous one",
    team_scopable=True,
    user_filterable=True,
)
