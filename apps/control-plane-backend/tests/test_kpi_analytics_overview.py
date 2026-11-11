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
    PREVIOUS_SINCE,
    SINCE,
    TEAM_TERMS,
    UNTIL,
    USER,
    FakeKpiStore,
    model,
    periods,
    value,
)
from control_plane_backend.kpi.presets.analytics_common import TURNS, VISITS
from control_plane_backend.kpi.presets.analytics_overview import (
    ANALYTICS_OVERVIEW_PRESET,
    query_analytics_overview,
)
from fred_core.common import TeamId
from fred_core.kpi.model_impact_factors import ModelImpactFactors


@pytest.fixture
def priced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: {
            "m": ModelImpactFactors(cost_per_1k_input_tokens=1.12),
            "default": ModelImpactFactors(),
        },
    )
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_usd_per_eur", lambda: 1.12
    )


def _bucket(*, users: float, messages: int, cost_input_k: float) -> dict[str, Any]:
    return {
        "doc_count": messages,
        "turns": {
            "doc_count": messages,
            "users": value(users),
            "team_space": {"teams": value(3)},
        },
        "visits": {"users": value(users * 2)},
        "sessions": {"doc_count": 7},
        "tokens": {"by_model": {"buckets": [model("m", cost_input_k * 1000, 0)]}},
    }


async def _run(store: FakeKpiStore, **kwargs: Any):
    return await query_analytics_overview(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_overview_splits_the_two_periods_in_one_search(priced: None) -> None:
    store = FakeKpiStore(
        periods=periods(
            _bucket(users=10, messages=40, cost_input_k=20),
            _bucket(users=5, messages=10, cost_input_k=5),
        )
    )
    result = await _run(store)

    assert len(store.bodies) == 1
    filters = store.body()["aggs"]["periods"]["filters"]["filters"]
    assert filters["current"]["range"]["@timestamp"]["gte"] == SINCE.isoformat()
    assert filters["previous"]["range"]["@timestamp"] == {
        "gte": PREVIOUS_SINCE.isoformat(),
        "lt": SINCE.isoformat(),
    }
    aggs = store.body()["aggs"]["periods"]["aggs"]
    assert aggs["turns"]["filter"] == TURNS
    assert aggs["visits"]["filter"] == VISITS
    assert result.active_users.current == 10 and result.active_users.previous == 5
    assert result.visitors.current == 20
    assert result.messages.current == 40 and result.conversations.current == 7
    assert result.active_teams.current == 3
    # 20k input tokens at 1.12 USD per 1k = 22.40 USD = 20 EUR.
    assert result.cost_eur.current == pytest.approx(20)
    assert result.cost_eur_per_active_user.current == pytest.approx(2)
    assert result.previous_since == PREVIOUS_SINCE


@pytest.mark.asyncio
async def test_overview_filters_selected_teams() -> None:
    store = FakeKpiStore()
    result = await _run(store, team_ids=(TeamId("a"), TeamId("b")))
    assert TEAM_TERMS in store.filters()
    assert ANALYTICS_OVERVIEW_PRESET.team_scopable
    assert result.active_users.current is None


@pytest.mark.asyncio
async def test_overview_per_user_cost_is_null_without_active_users(
    priced: None,
) -> None:
    store = FakeKpiStore(
        periods=periods(
            _bucket(users=0, messages=0, cost_input_k=1),
            _bucket(users=0, messages=0, cost_input_k=0),
        )
    )
    result = await _run(store)
    assert result.cost_eur_per_active_user.current is None
