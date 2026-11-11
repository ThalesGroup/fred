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

from types import SimpleNamespace
from typing import Any, cast

import pytest
from _kpi_test_doubles import (
    PREVIOUS_SINCE,
    SINCE,
    TEAM_TERMS,
    UNTIL,
    USER,
    FakeKpiStore,
    periods,
    value,
)
from control_plane_backend.kpi.presets import (
    analytics_agents,
    analytics_platform_counts,
)
from control_plane_backend.kpi.presets.analytics_agents import query_analytics_agents
from fred_core.common import TeamId


def _instance(team: str, *capabilities: str) -> Any:
    return SimpleNamespace(
        team_id=team, tuning=SimpleNamespace(selected_capability_ids=list(capabilities))
    )


class _Instances:
    def __init__(self) -> None:
        self.rows = [
            _instance("a", "web_research", "document_access"),
            _instance("a", "web_research", "web_research"),
            _instance("b", "document_access"),
            _instance("c", "spreadsheet"),
        ]
        self.calls: list[str] = []
        self.web_research = True

    async def list_all(self) -> list[Any]:
        self.calls.append("all")
        return self.rows

    async def list_by_team(self, team_id: str) -> list[Any]:
        self.calls.append(team_id)
        return [r for r in self.rows if r.team_id == team_id]

    async def count_published_created(
        self,
        windows: list[Any],
        team_ids: list[str],
        *,
        created_by: Any = None,
        excluded: Any = (),
    ) -> list[int]:
        self.published_args = (windows, team_ids)
        self.created_by = created_by
        return [3, 1]


@pytest.fixture
def instances(monkeypatch: pytest.MonkeyPatch) -> _Instances:
    store = _Instances()
    container = SimpleNamespace(get_agent_instance_store=lambda: store)
    for module in (analytics_agents, analytics_platform_counts):
        monkeypatch.setattr(module, "get_application_container", lambda _r: container)

    async def _names(_request: Any, team_ids: list[str]) -> dict[str, str]:
        return {t: f"Team {t}" for t in team_ids}

    monkeypatch.setattr(analytics_agents, "resolve_team_names", _names)
    store.web_research = True

    async def _web(_request: Any) -> bool:
        return store.web_research

    monkeypatch.setattr(analytics_agents, "web_research_enabled", _web)
    return store


def _period(agents: float) -> dict[str, Any]:
    return {
        "turns": {"agents": value(agents)},
        "created": {"doc_count": 2},
        "documents": {"doc_count": 30, "team_space": {"teams": value(4)}},
        "searches": {"doc_count": 99},
    }


_TOP = {
    "aggregations": {
        "by_agent": {
            "buckets": [
                {
                    "key": "agent-1",
                    "doc_count": 40,
                    "users": value(12),
                    "conversations": value(9),
                    "latest_dims": {
                        "hits": {
                            "hits": [
                                {
                                    "_source": {
                                        "dims": {
                                            "agent_instance_name": "Helper",
                                            "team_id": "a",
                                        }
                                    }
                                }
                            ]
                        }
                    },
                }
            ]
        }
    }
}


async def _run(store: FakeKpiStore, **kwargs: Any):
    return await query_analytics_agents(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_platform_scope(instances: _Instances) -> None:
    store = FakeKpiStore(periods=periods(_period(8), _period(6)), by_agent=_TOP)
    result = await _run(store)

    top_order = store.body("by_agent")["aggs"]["by_agent"]["terms"]["order"]
    assert top_order == [{"conversations": "desc"}, {"users": "desc"}]
    assert result.agents_used.current == 8 and result.agents_used.previous == 6
    assert result.agents_created.current == 2
    assert result.agents_created_published.model_dump() == {
        "current": 3,
        "previous": 1,
    }
    assert instances.published_args == (
        [(SINCE, UNTIL), (PREVIOUS_SINCE, SINCE)],
        [],
    )
    assert result.documents_added.current == 30
    assert result.teams_feeding_corpus.current == 4
    assert result.corpus_searches is not None and result.corpus_searches.current == 99
    [agent] = result.top_agents
    assert (agent.label, agent.users, agent.conversations, agent.messages) == (
        "Helper - Team a",
        12,
        9,
        40,
    )
    # An agent selecting a capability twice counts once.
    assert [(c.capability_id, c.agents_equipped) for c in result.capabilities] == [
        ("document_access", 2),
        ("web_research", 2),
        ("spreadsheet", 1),
    ]
    assert instances.calls == ["all"]


@pytest.mark.asyncio
async def test_team_scope_drops_corpus_searches(instances: _Instances) -> None:
    store = FakeKpiStore(periods=periods(_period(1), _period(1)), by_agent=_TOP)
    result = await _run(store, team_ids=(TeamId("a"), TeamId("b")))

    assert TEAM_TERMS in store.filters() and TEAM_TERMS in store.filters("by_agent")
    assert "searches" not in store.body()["aggs"]["periods"]["aggs"]
    assert result.corpus_searches is None
    assert instances.published_args[1] == ["a", "b"]
    assert instances.calls == ["all"]
    assert {c.capability_id for c in result.capabilities} == {
        "web_research",
        "document_access",
    }


_USAGE = {
    "aggregations": {
        "by_capability": {
            "buckets": [
                {
                    "key": "document_access",
                    "doc_count": 10,
                    "agents": value(1),
                    "users": value(3),
                    "failed": {"doc_count": 1},
                },
                {
                    "key": "retired_cap",
                    "doc_count": 4,
                    "agents": value(1),
                    "users": value(1),
                    "failed": {"doc_count": 0},
                },
            ]
        }
    }
}


@pytest.mark.asyncio
async def test_capability_usage_joins_tool_calls_with_equipped_agents(
    instances: _Instances,
) -> None:
    store = FakeKpiStore(
        periods=periods(_period(1), _period(1)), by_agent=_TOP, by_capability=_USAGE
    )
    result = await _run(store, team_ids=(TeamId("a"), TeamId("b")))

    rows = {c.capability_id: c for c in result.capabilities}
    doc = rows["document_access"]
    assert (doc.agents_equipped, doc.agents_used, doc.calls, doc.users) == (2, 1, 10, 3)
    assert doc.failed_calls == 1
    # Equipped but never called: zero usage. Called but equipped nowhere: still listed.
    assert rows["web_research"].calls == 0 and rows["web_research"].agents_equipped == 2
    assert rows["retired_cap"].agents_equipped == 0 and rows["retired_cap"].calls == 4
    assert [c.capability_id for c in result.capabilities][-1] == "retired_cap"

    body = store.body("by_capability")
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"metric.name": "agent.tool_latency_ms"}} in filters
    assert {"exists": {"field": "dims.capability_id"}} in filters
    assert TEAM_TERMS in filters
    assert body["query"]["bool"]["must_not"] == [
        {"term": {"dims.status": "awaiting_human"}}
    ]


@pytest.mark.asyncio
async def test_web_research_row_is_dropped_when_the_capability_is_disabled(
    instances: _Instances,
) -> None:
    instances.web_research = False
    store = FakeKpiStore(periods=periods(_period(1), _period(1)), by_agent=_TOP)
    result = await _run(store)

    assert "web_research" not in {c.capability_id for c in result.capabilities}
    assert {c.capability_id for c in result.capabilities} == {
        "document_access",
        "spreadsheet",
    }
