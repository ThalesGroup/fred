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
from control_plane_backend.kpi.presets import analytics_adoption
from control_plane_backend.kpi.presets.analytics_adoption import (
    ANALYTICS_ADOPTION_PRESET,
    query_analytics_adoption,
)
from fred_core.common import TeamId


def _funnel(visitors: float, active: float) -> dict[str, Any]:
    return {"visits": {"users": value(visitors)}, "turns": {"users": value(active)}}


@pytest.fixture
def access(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    env: dict[str, Any] = {"people": 200, "scopes": []}

    async def _people(_request: Any, team_ids: Any, user_ids: Any = None) -> int | None:
        env["scopes"].append(tuple(team_ids))
        env["user_ids"] = user_ids
        return env["people"]

    monkeypatch.setattr(analytics_adoption, "people_with_access", _people)
    return env


async def _run(store: FakeKpiStore, **kwargs: Any):
    return await query_analytics_adoption(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_funnel_steps_and_rates(access: dict[str, Any]) -> None:
    store = FakeKpiStore(periods=periods(_funnel(100, 60), _funnel(80, 40)))
    result = await _run(store)

    assert result.people_with_access == 200
    assert (result.visitors.current, result.active_users.current) == (100, 60)
    assert result.visit_rate.model_dump() == {"current": 0.5, "previous": 0.4}
    assert result.visitor_to_active_rate.model_dump() == {
        "current": 0.6,
        "previous": 0.5,
    }
    assert result.adoption_rate.model_dump() == {"current": 0.3, "previous": 0.2}
    aggs = store.body()["aggs"]["periods"]["aggs"]
    assert set(aggs) == {"turns", "visits"}


@pytest.mark.asyncio
async def test_team_scope_filters_events_and_access(access: dict[str, Any]) -> None:
    store = FakeKpiStore(periods=periods(_funnel(10, 5), _funnel(0, 0)))
    result = await _run(store, team_ids=(TeamId("a"), TeamId("b")))

    assert TEAM_TERMS in store.filters()
    assert access["scopes"] == [("a", "b")]
    # No visitor in the previous period: its step rate has no value.
    assert result.visitor_to_active_rate.previous is None


@pytest.mark.asyncio
async def test_unknown_access_leaves_rates_empty(access: dict[str, Any]) -> None:
    access["people"] = None
    store = FakeKpiStore(periods=periods(_funnel(10, 5), _funnel(8, 4)))
    result = await _run(store)

    assert result.people_with_access is None
    assert result.visit_rate.current is None and result.adoption_rate.current is None
    assert result.visitor_to_active_rate.current == 0.5


@pytest.mark.asyncio
async def test_no_data(access: dict[str, Any]) -> None:
    result = await _run(FakeKpiStore())
    assert result.visitors.current is None and result.adoption_rate.current is None


def test_adoption_is_team_scopable() -> None:
    assert ANALYTICS_ADOPTION_PRESET.team_scopable is True


@pytest.mark.asyncio
async def test_new_users_and_cohorts_come_from_the_lifecycle_scan(
    access: dict[str, Any],
) -> None:
    first = SINCE.timestamp() * 1000 + 3_600_000
    bucket = {
        "key": {"user": "u1"},
        "first_seen": value(first),
        "first_turn": {"at": value(first + 86_400_000)},
        "scoped": {"periods": {"buckets": {"current": {"doc_count": 2}}}},
    }
    store = FakeKpiStore(
        periods=periods(_funnel(1, 1), _funnel(0, 0)),
        users={"aggregations": {"users": {"buckets": [bucket]}}},
    )
    result = await _run(store, tz="Europe/Paris")

    assert result.new_users.model_dump() == {"current": 1, "previous": 0}
    assert result.first_message_within_7_days_rate.current == 1
    assert result.median_days_to_first_message.current == 1
    assert [row.month for row in result.cohorts][-1] == "2026-10"
    assert result.cohorts[-1].size == 1 and result.cohorts[-1].returns == [
        None,
        None,
        None,
    ]
    assert ANALYTICS_ADOPTION_PRESET.zoned is True
