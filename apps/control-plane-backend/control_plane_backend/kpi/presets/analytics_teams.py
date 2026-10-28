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

"""Teams tab: team vs personal conversations, and activity per team space.

Member counts come from `analytics_teams_catalog`; the page joins them in.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.presets.analytics_common import (
    SESSIONS,
    TEAM_SPACE,
    TURNS,
    PeriodValue,
    Windows,
    distinct,
    period_buckets,
    ratio,
    search,
    two_period_body,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.team_names import resolve_team_names

TEAMS_SIZE = 1000


class AnalyticsTeamUsageRow(BaseModel):
    team_id: str
    name: str
    active_members: int
    messages: int
    messages_previous: int


class AnalyticsTeamsResponse(BaseModel):
    # Null under a team scope: every conversation of a team scope is a team one.
    team_conversations: PeriodValue | None = None
    personal_conversations: PeriodValue | None = None
    team_share: PeriodValue | None = None
    active_teams: PeriodValue
    rows: list[AnalyticsTeamUsageRow]
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def teams_body(
    windows: Windows, team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    return two_period_body(
        windows,
        team_ids,
        [TURNS, SESSIONS],
        {
            "by_scope": {
                "filter": SESSIONS,
                "aggs": {"scopes": {"terms": {"field": "dims.scope_type", "size": 10}}},
            },
            "team_turns": {
                "filter": {"bool": {"filter": [TURNS, TEAM_SPACE]}},
                "aggs": {
                    "teams": {
                        "terms": {"field": "dims.team_id", "size": TEAMS_SIZE},
                        "aggs": {"users": distinct("dims.user_id")},
                    }
                },
            },
        },
        user_ids=user_ids,
    )


def _scope_counts(bucket: dict[str, Any]) -> tuple[float, float]:
    counts = {
        str(b["key"]): float(b["doc_count"])
        for b in bucket.get("by_scope", {}).get("scopes", {}).get("buckets", [])
    }
    return counts.get("team", 0.0), counts.get("personal", 0.0)


def _team_buckets(bucket: dict[str, Any]) -> list[dict[str, Any]]:
    return bucket.get("team_turns", {}).get("teams", {}).get("buckets", [])


async def query_analytics_teams(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
) -> AnalyticsTeamsResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user
    windows = Windows.of(since, until)
    response = await search(store, teams_body(windows, team_ids, user_ids))
    current, previous = period_buckets(response)

    previous_messages = {
        str(b["key"]): int(b["doc_count"]) for b in _team_buckets(previous)
    }
    current_buckets = _team_buckets(current)
    names = await resolve_team_names(request, [str(b["key"]) for b in current_buckets])
    rows = [
        AnalyticsTeamUsageRow(
            team_id=str(b["key"]),
            name=names.get(str(b["key"]), str(b["key"])),
            active_members=int(b.get("users", {}).get("value") or 0),
            messages=int(b["doc_count"]),
            messages_previous=previous_messages.get(str(b["key"]), 0),
        )
        for b in current_buckets
    ]
    active_teams = PeriodValue(
        current=float(len(current_buckets)), previous=float(len(previous_messages))
    )

    if team_ids:
        return AnalyticsTeamsResponse(
            active_teams=active_teams,
            rows=rows,
            since=since,
            until=until,
            previous_since=windows.previous_since,
        )
    team_now, personal_now = _scope_counts(current)
    team_before, personal_before = _scope_counts(previous)
    team = PeriodValue(current=team_now, previous=team_before)
    personal = PeriodValue(current=personal_now, previous=personal_before)
    total = PeriodValue(
        current=team_now + personal_now, previous=team_before + personal_before
    )
    return AnalyticsTeamsResponse(
        team_conversations=team,
        personal_conversations=personal,
        team_share=ratio(team, total),
        active_teams=active_teams,
        rows=rows,
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_TEAMS_PRESET = PresetDef(
    name="analytics_teams",
    response_model=AnalyticsTeamsResponse,
    handler=query_analytics_teams,
    summary="Team vs personal conversations and activity per team space, with the previous period",
    team_scopable=True,
    user_filterable=True,
)
