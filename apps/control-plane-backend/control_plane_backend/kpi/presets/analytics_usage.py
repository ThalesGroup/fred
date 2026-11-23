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

"""Usage tab: volumes, habit (frequency medians, daily use) and how conversations are spread."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.counted_days import ALL_DAYS, CountedDays
from control_plane_backend.kpi.presets.analytics_common import (
    SESSIONS,
    TURNS,
    PeriodValue,
    Windows,
    distinct,
    doc_count,
    per_period,
    period_buckets,
    ratio,
    search_by_period,
    sub_value,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint
from control_plane_backend.kpi.presets.distribution_utils import (
    CONVERSATION_BUCKETS,
    TERMS_SIZE,
    bucket_counts,
    median_of,
    terms_counts,
    top_decile_share,
)

# Distinct local days of a user's turns: the KPI documents carry no day field.
_LOCAL_DAY_SCRIPT = (
    "doc['@timestamp'].value.withZoneSameInstant(ZoneId.of(params.tz))"
    ".toLocalDate().toString()"
)


class AnalyticsUsageResponse(BaseModel):
    conversations: PeriodValue
    messages: PeriodValue
    active_users: PeriodValue
    active_users_per_workday: PeriodValue
    daily_usage_share: PeriodValue
    days_per_week_median: PeriodValue
    conversations_per_user_median: PeriodValue
    messages_per_conversation_median: PeriodValue
    single_exchange_share: PeriodValue
    top_decile_conversation_share: PeriodValue
    # Active users by number of conversations opened, current period.
    conversation_distribution: list[LabelValuePoint]
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def usage_aggs(tz: str) -> dict[str, Any]:
    return {
        "sessions": {
            "filter": SESSIONS,
            "aggs": {
                "by_user": {"terms": {"field": "dims.user_id", "size": TERMS_SIZE}}
            },
        },
        "turns": {
            "filter": TURNS,
            "aggs": {
                "users": distinct("dims.user_id"),
                "by_session": {
                    "terms": {"field": "dims.session_id", "size": TERMS_SIZE}
                },
                "by_day": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "calendar_interval": "1d",
                        "time_zone": tz,
                        "format": "yyyy-MM-dd",
                    },
                    "aggs": {"users": distinct("dims.user_id")},
                },
                "by_user": {
                    "terms": {"field": "dims.user_id", "size": TERMS_SIZE},
                    "aggs": {
                        "days": {
                            "cardinality": {
                                "script": {
                                    "source": _LOCAL_DAY_SCRIPT,
                                    "lang": "painless",
                                    "params": {"tz": tz},
                                }
                            }
                        }
                    },
                },
            },
        },
    }


def mean_per_day(turns: dict[str, Any], days: list[date]) -> float | None:
    """Mean daily active users over the counted days."""
    if not days:
        return None
    wanted = {d.isoformat() for d in days}
    total = sum(
        float(b.get("users", {}).get("value") or 0)
        for b in turns.get("by_day", {}).get("buckets", [])
        if str(b.get("key_as_string")) in wanted
    )
    return total / len(days)


def weeks_of(days: CountedDays, counted: int) -> float:
    """Weeks of counted days: a week holds five of them when weekends are left out."""
    return max(1.0, counted / (5 if days.exclude_weekends else 7))


def days_per_week(turns: dict[str, Any], weeks: float) -> float | None:
    per_user = [
        float(b.get("days", {}).get("value") or 0) / weeks
        for b in turns.get("by_user", {}).get("buckets", [])
    ]
    return median_of(per_user)


def single_exchange(turns: dict[str, Any]) -> float | None:
    counts = terms_counts(turns, "by_session")
    return sum(1 for c in counts if c == 1) / len(counts) if counts else None


async def query_analytics_usage(
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
) -> AnalyticsUsageResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request
    days = replace(days, tz=tz)
    windows = Windows.of(since, until, days)
    # Up to three 10 000-term aggs per period: one search per period.
    response = await search_by_period(
        store, windows, team_ids, [TURNS, SESSIONS], usage_aggs(tz), user_ids
    )
    current, previous = period_buckets(response)

    def both(read: Any) -> PeriodValue:
        return PeriodValue(
            current=read(current, since, until) if current else None,
            previous=read(previous, windows.previous_since, since)
            if previous
            else None,
        )

    active_users = per_period(response, sub_value("turns", "users"))
    per_workday = both(
        lambda b, start, end: mean_per_day(b.get("turns", {}), days.days(start, end))
    )
    return AnalyticsUsageResponse(
        conversations=per_period(response, doc_count("sessions")),
        messages=per_period(response, doc_count("turns")),
        active_users=active_users,
        active_users_per_workday=per_workday,
        daily_usage_share=ratio(per_workday, active_users),
        days_per_week_median=both(
            lambda b, start, end: days_per_week(
                b.get("turns", {}), weeks_of(days, len(days.days(start, end)))
            )
        ),
        conversations_per_user_median=per_period(
            response,
            lambda b: median_of(terms_counts(b.get("sessions", {}), "by_user")),
        ),
        messages_per_conversation_median=per_period(
            response,
            lambda b: median_of(terms_counts(b.get("turns", {}), "by_session")),
        ),
        single_exchange_share=per_period(
            response, lambda b: single_exchange(b.get("turns", {}))
        ),
        top_decile_conversation_share=per_period(
            response,
            lambda b: top_decile_share(terms_counts(b.get("sessions", {}), "by_user")),
        ),
        conversation_distribution=bucket_counts(
            terms_counts(current.get("sessions", {}), "by_user"), CONVERSATION_BUCKETS
        ),
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_USAGE_PRESET = PresetDef(
    name="analytics_usage",
    response_model=AnalyticsUsageResponse,
    handler=query_analytics_usage,
    summary="Usage volumes, frequency medians, daily use and conversation spread, with the previous period",
    team_scopable=True,
    user_filterable=True,
    zoned=True,
    day_filterable=True,
)
