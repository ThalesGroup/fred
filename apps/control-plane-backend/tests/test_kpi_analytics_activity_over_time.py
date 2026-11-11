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

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from _kpi_test_doubles import SINCE, TEAM_TERMS, UNTIL, USER, FakeKpiStore, model, value
from control_plane_backend.kpi import api
from control_plane_backend.kpi.presets.analytics_activity_over_time import (
    ANALYTICS_ACTIVITY_OVER_TIME_PRESET,
    query_analytics_activity_over_time,
)
from control_plane_backend.kpi.scope import KpiScope
from control_plane_backend.kpi.utils import calendar_histogram, resolve_bucket
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from fred_core.common import TeamId

_DAY = timedelta(days=1)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1, "hour"),
        (2, "hour"),
        (7, "day"),
        (31, "day"),
        (92, "week"),
        (180, "week"),
        (365, "month"),
    ],
)
def test_auto_bucket_follows_the_period_length(days: int, expected: str) -> None:
    assert resolve_bucket("auto", SINCE, SINCE + days * _DAY) == expected


def test_explicit_bucket_wins() -> None:
    assert resolve_bucket("month", SINCE, SINCE + _DAY) == "month"


def test_explicit_bucket_too_fine_for_the_period_gets_coarser() -> None:
    # 365 days in hours would pass OpenSearch's bucket limit with the sub-aggregations.
    assert resolve_bucket("hour", SINCE, SINCE + 365 * _DAY) == "day"
    assert resolve_bucket("day", SINCE, SINCE + 3650 * _DAY) == "week"
    assert resolve_bucket("hour", SINCE, SINCE + 30 * _DAY) == "hour"


@pytest.mark.parametrize(
    ("bucket", "interval", "fmt"),
    [
        ("hour", "1h", "yyyy-MM-dd'T'HH:mm"),
        ("day", "1d", "yyyy-MM-dd"),
        ("week", "1w", "yyyy-MM-dd"),
        ("month", "1M", "yyyy-MM-dd"),
    ],
)
def test_calendar_histogram(bucket: Any, interval: str, fmt: str) -> None:
    agg = calendar_histogram(SINCE, UNTIL, bucket, "Europe/Paris")["date_histogram"]
    assert agg["calendar_interval"] == interval
    assert agg["format"] == fmt
    assert agg["time_zone"] == "Europe/Paris"
    assert agg["min_doc_count"] == 0
    assert agg["extended_bounds"] == {
        "min": int(SINCE.timestamp() * 1000),
        "max": int(UNTIL.timestamp() * 1000),
    }


@pytest.mark.asyncio
async def test_points_carry_every_series_per_bucket() -> None:
    store = FakeKpiStore(
        by_time={
            "aggregations": {
                "by_time": {
                    "buckets": [
                        {
                            "key_as_string": "2026-10-01",
                            "turns": {"doc_count": 12, "users": value(4)},
                            "visits": {"users": value(6)},
                            "sessions": {"doc_count": 3},
                            "tokens": {"by_model": {"buckets": [model("m", 100, 20)]}},
                        }
                    ]
                }
            }
        }
    )
    result = await query_analytics_activity_over_time(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("a"), TeamId("b")),
        bucket="day",
        tz="UTC",
    )
    assert TEAM_TERMS in store.filters("by_time")
    assert (
        store.body("by_time")["aggs"]["by_time"]["date_histogram"]["time_zone"] == "UTC"
    )
    assert result.bucket == "day"
    point = result.points[0]
    assert point.start == "2026-10-01"
    assert point.values["active_users"] == 4 and point.values["visitors"] == 6
    assert point.values["messages"] == 12 and point.values["conversations"] == 3
    assert point.values["input_tokens"] == 100 and point.values["output_tokens"] == 20
    assert set(point.values) == set(result.series)


def _route(name: str) -> APIRoute:
    return next(
        r
        for r in api.build_kpi_router().routes
        if isinstance(r, APIRoute) and r.path.endswith(f"/{name}")
    )


@pytest.mark.asyncio
async def test_router_passes_bucket_and_tz_and_rejects_unknown_zones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "resolve_kpi_scope", AsyncMock(return_value=KpiScope()))
    seen: list[dict[str, Any]] = []
    store = SimpleNamespace(
        client=SimpleNamespace(search=lambda **kw: seen.append(kw["body"]) or {}),
        index="kpi",
    )
    call = dict(
        request=Request({"type": "http"}),
        since=datetime(2026, 10, 1, tzinfo=timezone.utc),
        until=datetime(2026, 10, 8, tzinfo=timezone.utc),
        team_ids=[],
        user=USER,
        store=store,
    )
    route = _route("analytics_activity_over_time")
    response = await route.endpoint(bucket="week", tz="America/New_York", **call)
    assert response.bucket == "week"
    histogram = seen[0]["aggs"]["by_time"]["date_histogram"]
    assert histogram["calendar_interval"] == "1w"
    assert histogram["time_zone"] == "America/New_York"
    assert ANALYTICS_ACTIVITY_OVER_TIME_PRESET.bucketable

    with pytest.raises(HTTPException) as exc:
        await route.endpoint(bucket="auto", tz="Mars/Olympus", **call)
    assert exc.value.status_code == 400
