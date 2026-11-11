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
    model,
    periods,
    value,
)
from control_plane_backend.kpi.presets import analytics_agents
from control_plane_backend.kpi.presets.analytics_common import TURN_ERRORS
from control_plane_backend.kpi.presets.analytics_quality_cost import (
    query_analytics_quality_cost,
)
from control_plane_backend.kpi.presets.common import CREATION_ASSISTANT_LABEL
from fred_core.common import TeamId
from fred_core.kpi.model_impact_factors import ModelImpactFactors


@pytest.fixture(autouse=True)
def priced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: {
            "big": ModelImpactFactors(
                cost_per_1k_input_tokens=1.12, co2e_grams_per_1k_tokens=1
            ),
            "small": ModelImpactFactors(),
            "default": ModelImpactFactors(),
        },
    )
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_usd_per_eur", lambda: 1.12
    )


def _period(errors: int, turns: int) -> dict[str, Any]:
    return {
        "turns": {"doc_count": turns, "users": value(5)},
        "errors": {"doc_count": errors},
        "tokens": {
            "by_model": {
                "buckets": [
                    model("big", 10_000, 0, turns={"doc_count": 30}),
                    model("small", 40_000, 10_000, turns={"doc_count": 70}),
                ]
            }
        },
    }


_AGENTS = {
    "aggregations": {
        "by_agent": {
            "buckets": [
                {
                    "key": "Cheap",
                    "users": value(10),
                    "by_model": {"buckets": [model("small", 900, 100)]},
                },
                {
                    "key": CREATION_ASSISTANT_LABEL,
                    "users": value(0),
                    "by_model": {"buckets": [model("big", 1000, 0)]},
                },
            ]
        }
    }
}


@pytest.mark.asyncio
async def test_quality_cost() -> None:
    store = FakeKpiStore(
        periods=periods(_period(3, 100), _period(1, 50)), by_agent=_AGENTS
    )
    result = await query_analytics_quality_cost(
        cast(Any, store), user=USER, since=SINCE, until=UNTIL, request=cast(Any, None)
    )

    assert store.body()["aggs"]["periods"]["aggs"]["errors"]["filter"] == TURN_ERRORS
    assert result.failed_turn_rate.current == pytest.approx(0.03)
    assert result.failed_turn_rate.previous == pytest.approx(0.02)
    assert result.cost_eur.current == pytest.approx(10)
    assert result.cost_eur_per_active_user.current == pytest.approx(2)
    assert (
        result.input_tokens.current == 50_000 and result.output_tokens.current == 10_000
    )
    assert result.co2e_grams.current == pytest.approx(10)
    assert [(m.model, m.message_share) for m in result.models] == [
        ("small", 0.7),
        ("big", 0.3),
    ]
    assert result.models[1].cost_eur == pytest.approx(10)
    # Ranked by cost; no users means no per-user cost.
    assert [a.label for a in result.agents] == [CREATION_ASSISTANT_LABEL, "Cheap"]
    assert result.agents[0].cost_eur_per_user is None
    assert result.agents[1].cost_eur_per_user == 0


@pytest.mark.asyncio
async def test_quality_cost_filters_selected_teams() -> None:
    store = FakeKpiStore()
    result = await query_analytics_quality_cost(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("a"), TeamId("b")),
    )
    assert TEAM_TERMS in store.filters() and TEAM_TERMS in store.filters("by_agent")
    assert result.failed_turn_rate.current is None and result.models == []


def _named(instance_id: str, name: str, team: str, users: int) -> dict[str, Any]:
    source = {"dims": {"agent_instance_name": name, "team_id": team}}
    return {
        "key": instance_id,
        "users": value(users),
        "latest_dims": {"hits": {"hits": [{"_source": source}]}},
        "by_model": {"buckets": [model("small", 900, 100)]},
    }


@pytest.mark.asyncio
async def test_agents_sharing_a_name_stay_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _names(_request: Any, team_ids: list[str]) -> dict[str, str]:
        return {t: f"Team {t}" for t in team_ids}

    monkeypatch.setattr(analytics_agents, "resolve_team_names", _names)
    by_agent = {
        "aggregations": {
            "by_agent": {
                "buckets": [
                    _named("id-a", "Assistant", "a", 3),
                    _named("id-b", "Assistant", "b", 5),
                ]
            }
        }
    }
    store = FakeKpiStore(
        periods=periods(_period(1, 10), _period(1, 10)), by_agent=by_agent
    )
    result = await query_analytics_quality_cost(
        cast(Any, store), user=USER, since=SINCE, until=UNTIL, request=cast(Any, None)
    )
    by_agent_terms = store.body("by_agent")["aggs"]["by_agent"]["terms"]
    assert by_agent_terms["field"] == "dims.agent_instance_id"
    assert sorted((a.label, a.users) for a in result.agents) == [
        ("Assistant - Team a", 3),
        ("Assistant - Team b", 5),
    ]
