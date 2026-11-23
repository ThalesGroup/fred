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

from typing import Any, cast

import pytest
from _kpi_test_doubles import (
    SINCE,
    TEAM_TERMS,
    UNTIL,
    USER,
    FakeKpiStore,
    periods,
    value,
)
from control_plane_backend.kpi.counted_days import CountedDays
from control_plane_backend.kpi.presets.analytics_usage import (
    ANALYTICS_USAGE_PRESET,
    query_analytics_usage,
)
from fred_core.common import TeamId


def _terms(*counts: int) -> dict[str, Any]:
    return {"buckets": [{"key": f"k{i}", "doc_count": c} for i, c in enumerate(counts)]}


def _period(days: list[tuple[str, float]], *, scale: int = 1) -> dict[str, Any]:
    return {
        "sessions": {"doc_count": 6 * scale, "by_user": _terms(1, 2, 3)},
        "turns": {
            "doc_count": 10 * scale,
            "users": value(4),
            "by_session": _terms(1, 1, 3, 5),
            "by_day": {
                "buckets": [{"key_as_string": d, "users": value(u)} for d, u in days]
            },
            "by_user": {
                "buckets": [
                    {"key": "u1", "days": value(2)},
                    {"key": "u2", "days": value(4)},
                ]
            },
        },
    }


WEEKDAYS = CountedDays(exclude_weekends=True)


def test_counted_days_skip_weekends_in_the_zone() -> None:
    # Thu 1 Oct 00:00 UTC -> Thu 8 Oct 00:00 UTC (exclusive): Thu, Fri, Mon-Wed.
    days = CountedDays(exclude_weekends=True, tz="UTC").days(SINCE, UNTIL)
    assert [d.isoformat() for d in days] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    ]


@pytest.mark.asyncio
async def test_usage_reads_both_periods() -> None:
    current = _period([("2026-10-01", 3), ("2026-10-03", 9), ("2026-10-05", 2)])
    store = FakeKpiStore(periods=periods(current, _period([], scale=2)))
    result = await query_analytics_usage(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("a"), TeamId("b")),
        tz="UTC",
        days=WEEKDAYS,
    )
    assert TEAM_TERMS in store.filters()
    assert sorted(
        k for b in store.bodies for k in b["aggs"]["periods"]["filters"]["filters"]
    ) == ["current", "previous"]
    by_day = store.body()["aggs"]["periods"]["aggs"]["turns"]["aggs"]["by_day"]
    assert by_day["date_histogram"]["time_zone"] == "UTC"
    assert result.messages.current == 10 and result.messages.previous == 20
    assert result.conversations.current == 6
    # Saturday 3 Oct is skipped: (3 + 2) users over 5 working days.
    assert result.active_users_per_workday.current == pytest.approx(1)
    assert result.daily_usage_share.current == pytest.approx(0.25)
    assert result.active_users_per_workday.previous == 0
    # One week: per-user distinct days 2 and 4.
    assert result.days_per_week_median.current == 3
    assert result.conversations_per_user_median.current == 2
    assert result.messages_per_conversation_median.current == 2
    assert result.single_exchange_share.current == pytest.approx(0.5)
    assert [(p.label, p.value) for p in result.conversation_distribution] == [
        ("1", 1),
        ("2-3", 2),
        ("4-10", 0),
        ("11-30", 0),
        ("31+", 0),
    ]
    assert ANALYTICS_USAGE_PRESET.zoned and ANALYTICS_USAGE_PRESET.team_scopable
    assert ANALYTICS_USAGE_PRESET.day_filterable


@pytest.mark.asyncio
async def test_per_day_denominators_follow_the_counted_days() -> None:
    current = _period([("2026-10-01", 3), ("2026-10-03", 9), ("2026-10-05", 2)])
    store = FakeKpiStore(periods=periods(current, _period([])))

    async def read(days: CountedDays) -> Any:
        return await query_analytics_usage(
            cast(Any, store),
            user=USER,
            since=SINCE,
            until=UNTIL,
            request=cast(Any, None),
            tz="UTC",
            days=days,
        )

    every_day = await read(CountedDays())
    # Saturday counts: (3 + 9 + 2) users over 7 days, one 7-day week.
    assert every_day.active_users_per_workday.current == pytest.approx(2)
    assert every_day.days_per_week_median.current == 3
    weekdays = await read(WEEKDAYS)
    assert weekdays.active_users_per_workday.current == pytest.approx(1)
    # Five counted weekdays make one week, so a daily user scores 5, not 3.6.
    assert weekdays.days_per_week_median.current == 3


@pytest.mark.asyncio
async def test_usage_without_data_has_no_medians() -> None:
    store = FakeKpiStore(periods=periods({"doc_count": 0}, {"doc_count": 0}))
    result = await query_analytics_usage(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        tz="UTC",
    )
    assert result.conversations_per_user_median.current is None
    assert result.single_exchange_share.current is None
    assert result.daily_usage_share.current is None
