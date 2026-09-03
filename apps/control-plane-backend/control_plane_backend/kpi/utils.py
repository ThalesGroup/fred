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

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from fastapi import Request
from fred_core.common import TeamId

from control_plane_backend.teams.dependencies import get_team_service_dependencies


def resolve_interval(since: datetime, until: datetime) -> tuple[str, str]:
    """Return (opensearch_fixed_interval, strftime_format) for the given range.

    Thresholds mirror the frontend getPrecisionForRange() in timeAxis.ts.
    """
    diff = until - since
    diff_hours = diff.total_seconds() / 3600
    diff_days = diff_hours / 24

    if diff.total_seconds() <= 10:
        return "1s", "%H:%M:%S"
    if diff_hours < 10:
        return "1m", "%H:%M"
    if diff_days <= 3:
        return "1h", "%Y-%m-%d %H:00"
    return "1d", "%Y-%m-%d"


# How many buckets a trend point pools before taking its median (issue #2428).
# Expressed in buckets, not in hours or days, so the window always follows
# whatever `resolve_interval` picked: 7 daily buckets → a 7-day window, 7 hourly
# buckets → a 7-hour one. There is deliberately no "unsmoothed" special case.
TREND_WINDOW_BUCKETS = 7

# Duration of one bucket, keyed by the `fixed_interval` strings above. Kept next
# to `resolve_interval` so a new interval cannot be added there without the
# trend window noticing (a missing key raises rather than silently mis-sizing
# the window).
_BUCKET_DURATIONS: dict[str, timedelta] = {
    "1s": timedelta(seconds=1),
    "1m": timedelta(minutes=1),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


class TrendInterval(NamedTuple):
    """Bucket interval and trailing window, resolved together.

    The window is `TREND_WINDOW_BUCKETS × interval` by construction, so the two
    cannot drift apart — every trend preset resolves both in this one call
    rather than picking an interval and then guessing a window beside it.
    """

    interval: str  # OpenSearch `fixed_interval`, e.g. "1d"
    date_fmt: str  # strftime format for the row labels
    bucket: timedelta  # duration of one bucket
    window: str  # wire form of the trailing window, same style as `interval`
    window_buckets: int  # the same window, in buckets — what the reducer pools
    lookback: timedelta  # how far before `since` the query must reach


def resolve_trend_interval(since: datetime, until: datetime) -> TrendInterval:
    """Resolve the bucket interval and the trailing window for a trend preset.

    `lookback` is exactly the window, which is what makes the first point of the
    range honest: the earliest bucket the query returns starts at or before
    `since - window`, so the seven buckets pooled into the first displayed point
    are all fully covered by the query range — none of them is clipped.
    """
    interval, date_fmt = resolve_interval(since, until)
    bucket = _BUCKET_DURATIONS[interval]
    return TrendInterval(
        interval=interval,
        date_fmt=date_fmt,
        bucket=bucket,
        # "1d" → "7d": the frontend localizes the unit letter, so the count and
        # the unit never have to be hardcoded there. `window_buckets` is the
        # same number handed to the reducer, so the label and the actual pooling
        # width come from this single spot.
        window=f"{TREND_WINDOW_BUCKETS}{interval[1:]}",
        window_buckets=TREND_WINDOW_BUCKETS,
        lookback=TREND_WINDOW_BUCKETS * bucket,
    )


async def resolve_team_names(request: Request, team_ids: list[str]) -> dict[str, str]:
    """Return {team_id: display_name} for each id. Falls back to the id on any error.

    A team's name lives in `team_metadata_store` — no Keycloak group backs it
    anymore (AUTHZ-05 review item 9). Shared by every preset that shows a team
    to a human rather than just aggregating on its id.
    """
    if not team_ids:
        return {}
    try:
        deps = get_team_service_dependencies(request)
        metadata_by_id = await deps.get_team_metadata_store().get_by_team_ids(
            [TeamId(tid) for tid in team_ids]
        )
        return {
            tid: metadata_by_id[TeamId(tid)].name
            if TeamId(tid) in metadata_by_id
            else tid
            for tid in team_ids
        }
    except Exception:
        return {tid: tid for tid in team_ids}
