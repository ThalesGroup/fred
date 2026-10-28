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

"""Activity per calendar bucket: visitors, active users, conversations, messages, tokens, cost, footprint."""

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
    TURNS,
    VISITS,
    BucketPoint,
    distinct,
    search,
    time_range,
    token_aggs,
    token_totals,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import TOKEN_USAGE_FILTER, scope_filter
from control_plane_backend.kpi.utils import (
    Bucket,
    CalendarBucket,
    calendar_histogram,
    resolve_bucket,
)

SERIES = (
    "visitors",
    "active_users",
    "conversations",
    "messages",
    "input_tokens",
    "output_tokens",
    "cost_eur",
    "co2e_grams",
    "kwh",
)


class AnalyticsActivityResponse(BaseModel):
    bucket: CalendarBucket
    series: list[str]
    points: list[BucketPoint]
    since: AwareDatetime
    until: AwareDatetime


def activity_body(
    since: datetime,
    until: datetime,
    team_ids: Sequence[str],
    bucket: CalendarBucket,
    tz: str,
    user_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    histogram = calendar_histogram(since, until, bucket, tz)
    histogram["aggs"] = {
        "turns": {"filter": TURNS, "aggs": {"users": distinct("dims.user_id")}},
        "visits": {"filter": VISITS, "aggs": {"users": distinct("dims.user_id")}},
        "sessions": {"filter": SESSIONS},
        "tokens": token_aggs(),
    }
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    time_range(since, until),
                    {
                        "bool": {
                            "should": [TURNS, VISITS, SESSIONS, TOKEN_USAGE_FILTER],
                            "minimum_should_match": 1,
                        }
                    },
                    *scope_filter(team_ids, user_ids),
                ]
            }
        },
        "aggs": {"by_time": histogram},
    }


def point(bucket: dict[str, Any]) -> BucketPoint:
    tokens = token_totals(bucket.get("tokens", {}))
    return BucketPoint(
        start=str(bucket["key_as_string"]),
        values={
            "visitors": float(
                bucket.get("visits", {}).get("users", {}).get("value") or 0
            ),
            "active_users": float(
                bucket.get("turns", {}).get("users", {}).get("value") or 0
            ),
            "conversations": float(bucket.get("sessions", {}).get("doc_count", 0)),
            "messages": float(bucket.get("turns", {}).get("doc_count", 0)),
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "cost_eur": tokens.cost_eur,
            "co2e_grams": tokens.co2e_grams,
            "kwh": tokens.kwh,
        },
    )


async def query_analytics_activity_over_time(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
    bucket: Bucket = "auto",
    tz: str = "Europe/Paris",
) -> AnalyticsActivityResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request
    resolved = resolve_bucket(bucket, since, until)
    response = await search(
        store, activity_body(since, until, team_ids, resolved, tz, user_ids)
    )
    buckets = response.get("aggregations", {}).get("by_time", {}).get("buckets", [])
    return AnalyticsActivityResponse(
        bucket=resolved,
        series=list(SERIES),
        points=[point(b) for b in buckets],
        since=since,
        until=until,
    )


ANALYTICS_ACTIVITY_OVER_TIME_PRESET = PresetDef(
    name="analytics_activity_over_time",
    response_model=AnalyticsActivityResponse,
    handler=query_analytics_activity_over_time,
    summary="Visitors, active users, conversations, messages, tokens, cost (EUR) and footprint (gCO2e, kWh) per calendar bucket",
    team_scopable=True,
    user_filterable=True,
    bucketable=True,
)
