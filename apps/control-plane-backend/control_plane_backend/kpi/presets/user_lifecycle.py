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

"""Per-user first visit and first message, for new users, activation and cohorts.

A new user is one whose first-ever human KPI event falls in a range. The scan
reads the requested window page by page (composite aggregation on the user),
then one bounded pass over older events tells which of those users came before.
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.analytics_common import (
    TURNS,
    PeriodValue,
    Windows,
    search,
    time_range,
)
from control_plane_backend.kpi.presets.common import team_filter, user_filter

PAGE_SIZE = 1000
PRIOR_CONCURRENCY = 4
COHORT_MONTHS = 5
RETURN_MONTHS = 3
ACTIVATION_DELAY = timedelta(days=7)
MONTH_FORMAT = "yyyy-MM"

HUMAN_EVENTS: list[dict[str, Any]] = [
    {"term": {"dims.actor_type": "human"}},
    {"exists": {"field": "dims.user_id"}},
]


@dataclass
class UserLifecycle:
    first_seen: datetime
    first_turn: datetime | None = None
    # Seen before the scanned window: new in none of its ranges.
    prior: bool = False
    # Events attributed to the scope (every event for the whole platform).
    scoped_current: bool = False
    scoped_previous: bool = False
    scoped_months: set[str] = field(default_factory=set)
    turn_months: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CohortRow:
    month: str
    size: int
    returns: list[float | None]


def month_key(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%Y-%m")


def shift_month(month: str, delta: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_start(month: str, zone: ZoneInfo) -> datetime:
    year, number = (int(part) for part in month.split("-"))
    return datetime(year, number, 1, tzinfo=zone)


def cohort_months(until: datetime, zone: ZoneInfo) -> list[str]:
    """The last calendar months up to the one holding the period end, oldest first."""
    last = month_key(until - timedelta(microseconds=1), zone)
    return [shift_month(last, -k) for k in range(COHORT_MONTHS - 1, -1, -1)]


def _months_agg(tz: str) -> dict[str, Any]:
    return {
        "date_histogram": {
            "field": "@timestamp",
            "calendar_interval": "1M",
            "time_zone": tz,
            "format": MONTH_FORMAT,
            "min_doc_count": 1,
        }
    }


def lifecycle_body(
    windows: Windows,
    window_start: datetime,
    cohort_start: datetime,
    team_ids: Sequence[str],
    tz: str,
    after: dict[str, Any] | None = None,
    user_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    # The team clause scopes the periods; the user filter scopes who is scanned.
    scope = team_filter(team_ids)
    composite: dict[str, Any] = {
        "size": PAGE_SIZE,
        "sources": [{"user": {"terms": {"field": "dims.user_id"}}}],
    }
    if after is not None:
        composite["after"] = after
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    *HUMAN_EVENTS,
                    time_range(window_start, windows.until),
                    *user_filter(user_ids),
                ]
            }
        },
        "aggs": {
            "users": {
                "composite": composite,
                "aggs": {
                    "first_seen": {"min": {"field": "@timestamp"}},
                    "first_turn": {
                        "filter": TURNS,
                        "aggs": {"at": {"min": {"field": "@timestamp"}}},
                    },
                    "scoped": {
                        "filter": {"bool": {"filter": scope}}
                        if scope
                        else {"match_all": {}},
                        "aggs": {
                            "periods": {
                                "filters": {
                                    "filters": {
                                        "current": time_range(
                                            windows.since, windows.until
                                        ),
                                        "previous": time_range(
                                            windows.previous_since,
                                            windows.since,
                                            inclusive_end=False,
                                        ),
                                    }
                                }
                            },
                            "recent": {
                                "filter": time_range(cohort_start, windows.until),
                                "aggs": {
                                    "months": _months_agg(tz),
                                    "turns": {
                                        "filter": TURNS,
                                        "aggs": {"months": _months_agg(tz)},
                                    },
                                },
                            },
                        },
                    },
                },
            }
        },
    }


def prior_body(user_ids: Sequence[str], before: datetime) -> dict[str, Any]:
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    *HUMAN_EVENTS,
                    {"terms": {"dims.user_id": list(user_ids)}},
                    {"range": {"@timestamp": {"lt": before.isoformat()}}},
                ]
            }
        },
        "aggs": {"prior": {"terms": {"field": "dims.user_id", "size": len(user_ids)}}},
    }


EARLIEST_BODY: dict[str, Any] = {
    "size": 1,
    "_source": False,
    "query": {"bool": {"filter": HUMAN_EVENTS}},
    "sort": [{"@timestamp": {"order": "asc"}}],
    "fields": ["@timestamp"],
}


def _instant(value: Any) -> datetime | None:
    """A `min` aggregation value (epoch millis), or None for an empty bucket."""
    if value is None:
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=ZoneInfo("UTC"))


def _months(bucket: dict[str, Any]) -> set[str]:
    return {
        str(b["key_as_string"])
        for b in bucket.get("months", {}).get("buckets", [])
        if b.get("doc_count")
    }


def parse_user(bucket: dict[str, Any]) -> UserLifecycle | None:
    first_seen = _instant(bucket.get("first_seen", {}).get("value"))
    if first_seen is None:
        return None
    scoped = bucket.get("scoped", {})
    periods = scoped.get("periods", {}).get("buckets", {})
    recent = scoped.get("recent", {})
    return UserLifecycle(
        first_seen=first_seen,
        first_turn=_instant(bucket.get("first_turn", {}).get("at", {}).get("value")),
        scoped_current=bool(periods.get("current", {}).get("doc_count")),
        scoped_previous=bool(periods.get("previous", {}).get("doc_count")),
        scoped_months=_months(recent),
        turn_months=_months(recent.get("turns", {})),
    )


async def _earliest_event(store: OpenSearchKPIStore) -> datetime | None:
    response = await search(store, EARLIEST_BODY)
    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        return None
    sort = hits[0].get("sort") or []
    return _instant(sort[0]) if sort else None


async def scan_users(
    store: OpenSearchKPIStore,
    windows: Windows,
    window_start: datetime,
    cohort_start: datetime,
    team_ids: Sequence[str],
    tz: str,
    user_ids: Sequence[str] | None = None,
) -> dict[str, UserLifecycle]:
    """Every user seen in `[window_start, until]`, flagged when seen before it too."""
    users: dict[str, UserLifecycle] = {}
    after: dict[str, Any] | None = None
    while True:
        response = await search(
            store,
            lifecycle_body(
                windows, window_start, cohort_start, team_ids, tz, after, user_ids
            ),
        )
        page = response.get("aggregations", {}).get("users", {})
        buckets = page.get("buckets", [])
        for bucket in buckets:
            parsed = parse_user(bucket)
            if parsed is not None:
                users[str(bucket["key"]["user"])] = parsed
        after = page.get("after_key")
        if not buckets or after is None or len(buckets) < PAGE_SIZE:
            break

    earliest = await _earliest_event(store) if users else None
    if earliest is None or earliest >= window_start:
        return users
    ids = sorted(users)
    slots = asyncio.Semaphore(PRIOR_CONCURRENCY)

    async def prior(batch: list[str]) -> list[str]:
        async with slots:
            response = await search(store, prior_body(batch, window_start))
        buckets = response.get("aggregations", {}).get("prior", {}).get("buckets", [])
        return [str(b["key"]) for b in buckets]

    batches = [ids[i : i + PAGE_SIZE] for i in range(0, len(ids), PAGE_SIZE)]
    for seen in await asyncio.gather(*(prior(batch) for batch in batches)):
        for user_id in seen:
            if user_id in users:
                users[user_id].prior = True
    return users


@dataclass(frozen=True)
class Lifecycle:
    new_users: PeriodValue
    first_message_within_7_days_rate: PeriodValue
    median_days_to_first_message: PeriodValue
    next_month_return: PeriodValue
    cohorts: list[CohortRow]


def _new_in(
    users: dict[str, UserLifecycle],
    start: datetime,
    end: datetime,
    *,
    inclusive_end: bool,
    scoped: str | None,
) -> list[UserLifecycle]:
    def within(moment: datetime) -> bool:
        return start <= moment and (moment <= end if inclusive_end else moment < end)

    return [
        u
        for u in users.values()
        if not u.prior
        and within(u.first_seen)
        and (scoped is None or getattr(u, scoped))
    ]


def _activation(new: list[UserLifecycle]) -> tuple[float | None, float | None]:
    delays = [
        (u.first_turn - u.first_seen).total_seconds() / 86400
        for u in new
        if u.first_turn is not None
    ]
    within = sum(delay <= ACTIVATION_DELAY.total_seconds() / 86400 for delay in delays)
    rate = within / len(new) if new else None
    return rate, (statistics.median(delays) if delays else None)


def summarize(
    users: dict[str, UserLifecycle],
    windows: Windows,
    months: list[str],
    zone: ZoneInfo,
    *,
    team_scoped: bool,
) -> Lifecycle:
    current = _new_in(
        users,
        windows.since,
        windows.until,
        inclusive_end=True,
        scoped="scoped_current" if team_scoped else None,
    )
    previous = _new_in(
        users,
        windows.previous_since,
        windows.since,
        inclusive_end=False,
        scoped="scoped_previous" if team_scoped else None,
    )
    rate, median = _activation(current)
    previous_rate, previous_median = _activation(previous)

    last = months[-1]
    by_month: dict[str, list[UserLifecycle]] = {month: [] for month in months}
    for user in users.values():
        month = month_key(user.first_seen, zone)
        if (
            not user.prior
            and month in by_month
            and (not team_scoped or month in user.scoped_months)
        ):
            by_month[month].append(user)
    cohorts = [
        CohortRow(
            month=month,
            size=len(members),
            returns=[
                None
                if not members or shift_month(month, k) > last
                else sum(shift_month(month, k) in u.turn_months for u in members)
                / len(members)
                for k in range(1, RETURN_MONTHS + 1)
            ],
        )
        for month, members in by_month.items()
    ]
    by_key = {row.month: row for row in cohorts}
    return Lifecycle(
        new_users=PeriodValue(
            current=float(len(current)), previous=float(len(previous))
        ),
        first_message_within_7_days_rate=PeriodValue(
            current=rate, previous=previous_rate
        ),
        median_days_to_first_message=PeriodValue(
            current=median, previous=previous_median
        ),
        next_month_return=PeriodValue(
            current=by_key[shift_month(last, -1)].returns[0],
            previous=by_key[shift_month(last, -2)].returns[0],
        ),
        cohorts=cohorts,
    )


async def user_lifecycle(
    store: OpenSearchKPIStore,
    windows: Windows,
    team_ids: Sequence[str],
    tz: str,
    user_ids: Sequence[str] | None = None,
) -> Lifecycle:
    zone = ZoneInfo(tz)
    months = cohort_months(windows.until, zone)
    cohort_start = month_start(months[0], zone)
    window_start = min(windows.previous_since, cohort_start)
    users = await scan_users(
        store, windows, window_start, cohort_start, team_ids, tz, user_ids
    )
    return summarize(users, windows, months, zone, team_scoped=bool(team_ids))
