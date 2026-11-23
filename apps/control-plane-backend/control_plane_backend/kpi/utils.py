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

from datetime import datetime
from typing import Any, Literal


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


Bucket = Literal["auto", "hour", "day", "week", "month"]
CalendarBucket = Literal["hour", "day", "week", "month"]

_CALENDAR_INTERVALS: dict[CalendarBucket, str] = {
    "hour": "1h",
    "day": "1d",
    "week": "1w",
    "month": "1M",
}


# Upper bound on buckets per read, well below OpenSearch's `search.max_buckets`.
MAX_CALENDAR_BUCKETS = 1000
_BUCKET_DAYS: dict[CalendarBucket, float] = {
    "hour": 1 / 24,
    "day": 1,
    "week": 7,
    "month": 28,
}


def resolve_bucket(bucket: Bucket, since: datetime, until: datetime) -> CalendarBucket:
    """`auto` picks the bucket the analytics page uses for a period of this length;
    an explicit bucket too fine for the period moves to the next coarser one."""
    days = (until - since).total_seconds() / 86400
    if bucket != "auto":
        order: list[CalendarBucket] = ["hour", "day", "week", "month"]
        for candidate in order[order.index(bucket) :]:
            if days / _BUCKET_DAYS[candidate] <= MAX_CALENDAR_BUCKETS:
                return candidate
        return "month"
    if days <= 2:
        return "hour"
    if days <= 31:
        return "day"
    if days <= 180:
        return "week"
    return "month"


def calendar_histogram(
    since: datetime, until: datetime, bucket: CalendarBucket, tz: str
) -> dict[str, Any]:
    """A `date_histogram` on calendar buckets in `tz`, keyed by ISO bucket start.

    Bounds are epoch millis: the agg `format` would otherwise parse them.
    """
    return {
        "date_histogram": {
            "field": "@timestamp",
            "calendar_interval": _CALENDAR_INTERVALS[bucket],
            "time_zone": tz,
            "format": "yyyy-MM-dd'T'HH:mm" if bucket == "hour" else "yyyy-MM-dd",
            "min_doc_count": 0,
            "extended_bounds": {
                "min": int(since.timestamp() * 1000),
                "max": int(until.timestamp() * 1000),
            },
        }
    }
