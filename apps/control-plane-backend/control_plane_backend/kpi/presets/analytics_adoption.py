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

"""Adoption tab: from access to usage, then whether new users start and come back."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.counted_days import ALL_DAYS, CountedDays
from control_plane_backend.kpi.presets.analytics_common import (
    TURNS,
    VISITS,
    PeriodValue,
    Windows,
    distinct,
    per_period,
    ratio,
    search,
    sub_value,
    two_period_body,
)
from control_plane_backend.kpi.presets.analytics_platform_counts import (
    people_with_access,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.user_lifecycle import user_lifecycle


class AnalyticsCohortRow(BaseModel):
    """Users whose first visit fell in `month` (YYYY-MM, request time zone), and the
    share of them who sent a message 1, 2 and 3 months later (null = not yet)."""

    month: str
    size: int
    returns: list[float | None]


class AnalyticsAdoptionResponse(BaseModel):
    # Today's count: access is not recorded over time, so both periods' rates use it.
    people_with_access: int | None = None
    visitors: PeriodValue
    active_users: PeriodValue
    visit_rate: PeriodValue
    visitor_to_active_rate: PeriodValue
    adoption_rate: PeriodValue
    # First-ever human KPI event in the period (and, for teams, an event in them).
    new_users: PeriodValue
    first_message_within_7_days_rate: PeriodValue
    median_days_to_first_message: PeriodValue
    # Previous month's new users active in the month of the period end.
    next_month_return: PeriodValue
    cohorts: list[AnalyticsCohortRow]
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def funnel_body(
    windows: Windows, team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    return two_period_body(
        windows,
        team_ids,
        [TURNS, VISITS],
        {
            "turns": {"filter": TURNS, "aggs": {"users": distinct("dims.user_id")}},
            "visits": {"filter": VISITS, "aggs": {"users": distinct("dims.user_id")}},
        },
        user_ids=user_ids,
    )


async def query_analytics_adoption(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
    tz: str = "Europe/Paris",
    days: CountedDays = ALL_DAYS,
) -> AnalyticsAdoptionResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user
    windows = Windows.of(since, until, days)
    response, people, lifecycle = await asyncio.gather(
        search(store, funnel_body(windows, team_ids, user_ids)),
        people_with_access(request, team_ids, user_ids),
        user_lifecycle(store, windows, team_ids, tz, user_ids),
    )
    visitors = per_period(response, sub_value("visits", "users"))
    active_users = per_period(response, sub_value("turns", "users"))
    access = PeriodValue(
        current=float(people) if people is not None else None,
        previous=float(people) if people is not None else None,
    )
    return AnalyticsAdoptionResponse(
        people_with_access=people,
        visitors=visitors,
        active_users=active_users,
        visit_rate=ratio(visitors, access),
        visitor_to_active_rate=ratio(active_users, visitors),
        adoption_rate=ratio(active_users, access),
        new_users=lifecycle.new_users,
        first_message_within_7_days_rate=lifecycle.first_message_within_7_days_rate,
        median_days_to_first_message=lifecycle.median_days_to_first_message,
        next_month_return=lifecycle.next_month_return,
        cohorts=[
            AnalyticsCohortRow(month=row.month, size=row.size, returns=row.returns)
            for row in lifecycle.cohorts
        ],
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_ADOPTION_PRESET = PresetDef(
    name="analytics_adoption",
    response_model=AnalyticsAdoptionResponse,
    handler=query_analytics_adoption,
    summary="Adoption funnel, new users, activation, next-month return and monthly cohorts",
    team_scopable=True,
    user_filterable=True,
    zoned=True,
    day_filterable=True,
)
