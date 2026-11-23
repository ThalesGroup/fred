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

"""Excluded days of the analytics: French holidays, merged local-day ranges,
the clause every day-filterable preset adds to each search, and the router."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from _kpi_test_doubles import SINCE, UNTIL, USER, FakeKpiStore, stub_side_reads
from control_plane_backend.kpi import api
from control_plane_backend.kpi.counted_days import (
    CountedDays,
    counted_days,
    easter_sunday,
    french_holidays,
)
from control_plane_backend.kpi.presets import PRESETS
from control_plane_backend.kpi.presets.analytics_activity_over_time import (
    query_analytics_activity_over_time,
)
from control_plane_backend.kpi.scope import KpiScope
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

PARIS = ZoneInfo("Europe/Paris")
WORKDAYS = CountedDays(exclude_weekends=True, exclude_holidays=True)


def _paris(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=PARIS)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("year", "easter", "movable"),
    [
        (
            2026,
            date(2026, 4, 5),
            [date(2026, 4, 6), date(2026, 5, 14), date(2026, 5, 25)],
        ),
        (
            2027,
            date(2027, 3, 28),
            [date(2027, 3, 29), date(2027, 5, 6), date(2027, 5, 17)],
        ),
    ],
)
def test_easter_based_holidays(year: int, easter: date, movable: list[date]) -> None:
    assert easter_sunday(year) == easter
    holidays = french_holidays(year)
    assert len(holidays) == 11
    assert set(movable) <= holidays
    assert {date(year, 1, 1), date(year, 7, 14), date(year, 12, 25)} <= holidays


def test_weekend_is_one_range_in_local_time_across_dst() -> None:
    # Sat 24 - Sun 25 Oct 2026: the clocks go back, the weekend lasts 49 hours.
    days = CountedDays(exclude_weekends=True)
    ranges = days.excluded_ranges(_paris(2026, 10, 22), _paris(2026, 10, 28))
    assert ranges == [(_paris(2026, 10, 24), _paris(2026, 10, 26))]
    low, high = (moment.astimezone(timezone.utc) for moment in ranges[0])
    assert high - low == timedelta(hours=49)


def test_holiday_next_to_a_weekend_merges_and_ranges_are_clipped() -> None:
    # Fri 1 May 2026 is a holiday: Fri-Sun is one range; Fri 8 May another,
    # cut at the period end.
    ranges = WORKDAYS.excluded_ranges(_paris(2026, 4, 30, 12), _paris(2026, 5, 8, 9))
    assert ranges == [
        (_paris(2026, 5, 1), _paris(2026, 5, 4)),
        (_paris(2026, 5, 8), _paris(2026, 5, 8, 9)),
    ]
    holidays_only = CountedDays(exclude_holidays=True)
    assert holidays_only.excluded_ranges(_paris(2026, 5, 2), _paris(2026, 5, 7)) == []


def test_counted_days_and_query_filter() -> None:
    assert CountedDays().query_filter(SINCE, UNTIL) == []
    assert not CountedDays().active
    clause = WORKDAYS.query_filter(_paris(2026, 7, 13), _paris(2026, 7, 20))
    assert clause == [
        {
            "bool": {
                "must_not": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": _paris(2026, 7, 14).isoformat(),
                                "lt": _paris(2026, 7, 15).isoformat(),
                            }
                        }
                    },
                    {
                        "range": {
                            "@timestamp": {
                                "gte": _paris(2026, 7, 18).isoformat(),
                                "lt": _paris(2026, 7, 20).isoformat(),
                            }
                        }
                    },
                ]
            }
        }
    ]
    week = WORKDAYS.days(_paris(2026, 7, 13), _paris(2026, 7, 20))
    assert [d.day for d in week] == [13, 15, 16, 17]


# --- every day-filterable preset filters every search ----------------------------


def _day_clauses(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        c for c in body["query"]["bool"]["filter"] if "must_not" in c.get("bool", {})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preset", [p for p in PRESETS if p.day_filterable], ids=lambda p: p.name
)
async def test_every_day_filterable_preset_filters_every_search(
    preset: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_side_reads(monkeypatch)
    store = FakeKpiStore()
    kwargs: dict[str, Any] = dict(
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        days=CountedDays(exclude_weekends=True),
    )
    if preset.team_scopable:
        kwargs["team_ids"] = ()
    if preset.bucketable or preset.zoned:
        kwargs["tz"] = "Europe/Paris"
    await preset.handler(store, **kwargs)
    assert store.bodies, f"{preset.name} ran no search"
    excluded: list[dict[str, Any]] = []
    for body in store.bodies:
        clauses = _day_clauses(body)
        assert clauses, preset.name
        excluded.extend(clauses[0]["bool"]["must_not"])
    # Sat 3 - Sun 4 Oct 2026 in Paris time, in the search of the current period.
    assert {
        "range": {
            "@timestamp": {
                "gte": _paris(2026, 10, 3).isoformat(),
                "lt": _paris(2026, 10, 5).isoformat(),
            }
        }
    } in excluded, preset.name


def test_every_time_based_analytics_preset_is_day_filterable() -> None:
    state_gauges = {
        "analytics_teams_catalog",
        "storage_by_team",
        "agents_total",
        "agent_prompt_length_distribution",
    }
    for preset in PRESETS:
        if preset.user_filterable and preset.name not in state_gauges:
            assert preset.day_filterable, preset.name


@pytest.mark.asyncio
async def test_excluded_day_buckets_leave_the_daily_series() -> None:
    days = [f"2026-10-0{d}" for d in range(1, 8)]
    store = FakeKpiStore(
        by_time={
            "aggregations": {
                "by_time": {
                    "buckets": [{"key_as_string": d, "doc_count": 0} for d in days]
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
        bucket="day",
        tz="Europe/Paris",
        days=CountedDays(exclude_weekends=True),
    )
    assert [p.start for p in result.points] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    ]


# --- router --------------------------------------------------------------------


def _route(path: str) -> APIRoute:
    return next(
        r
        for r in api.build_kpi_router().routes
        if isinstance(r, APIRoute) and r.path == path
    )


@pytest.mark.asyncio
async def test_router_passes_counted_days_in_the_request_zone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _scope(*args: Any, **kwargs: Any) -> KpiScope:
        return KpiScope()

    seen: dict[str, Any] = {}

    async def _handler(store: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return None

    monkeypatch.setattr(api, "resolve_kpi_scope", _scope)
    preset = next(p for p in PRESETS if p.name == "analytics_overview")
    monkeypatch.setattr(preset, "handler", _handler)
    await _route("/kpi/presets/analytics_overview").endpoint(
        request=Request({"type": "http"}),
        since=SINCE,
        until=UNTIL,
        team_ids=[],
        bucket="auto",
        tz="UTC",
        user_filter=None,
        exclude_weekends=True,
        exclude_holidays=False,
        user=USER,
        store=object(),
    )
    assert seen["days"] == CountedDays(exclude_weekends=True, tz="UTC")
    assert "tz" not in seen


def test_excluding_days_needs_a_bounded_period() -> None:
    with pytest.raises(HTTPException) as exc:
        counted_days(True, False, "Europe/Paris", timedelta(days=5 * 365))
    assert exc.value.status_code == 400
    # Counting every day needs no ranges, so any period is fine.
    assert not counted_days(False, False, "UTC", timedelta(days=5 * 365)).active
