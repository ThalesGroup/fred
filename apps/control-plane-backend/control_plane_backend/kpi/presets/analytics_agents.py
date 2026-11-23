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

"""Agents and tools tab: agents used and created, top agents, capabilities, corpora.

Capability usage counts tool calls tagged with `dims.capability_id`; calls
recorded before tool KPIs carried it are not attributed.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId, is_personal_team_id
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.counted_days import ALL_DAYS, CountedDays
from control_plane_backend.kpi.presets.analytics_common import (
    AGENT_CREATED_METRIC,
    DOCUMENT_CREATED_METRIC,
    RAG_SEARCH_METRIC,
    TEAM_SPACE,
    TURNS,
    PeriodValue,
    Windows,
    distinct,
    doc_count,
    metric,
    per_period,
    search,
    sub_value,
    time_range,
    two_period_body,
)
from control_plane_backend.kpi.presets.analytics_platform_counts import (
    agents_created_published,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import scope_filter
from control_plane_backend.kpi.presets.team_names import (
    build_agent_labels,
    resolve_team_names,
)
from control_plane_backend.kpi.presets.web_research_summary import (
    WEB_RESEARCH_CAPABILITY_ID,
    web_research_enabled,
)

TOP_N = 10
TOOL_LATENCY_METRIC = "agent.tool_latency_ms"
MAX_CAPABILITIES = 500
AGENT_TURNS: dict[str, Any] = {
    "bool": {"filter": [TURNS, {"exists": {"field": "dims.agent_instance_id"}}]}
}


class AnalyticsAgentRow(BaseModel):
    agent_instance_id: str
    label: str
    users: int
    conversations: int
    messages: int


class AnalyticsCapabilityRow(BaseModel):
    """Agents equipped today; the other counts cover the current period only."""

    capability_id: str
    agents_equipped: int
    agents_used: int = 0
    calls: int = 0
    users: int = 0
    failed_calls: int = 0


class AnalyticsAgentsResponse(BaseModel):
    agents_used: PeriodValue
    agents_created: PeriodValue
    # Agents created in the period and published to the marketplace at least once.
    agents_created_published: PeriodValue
    documents_added: PeriodValue
    teams_feeding_corpus: PeriodValue
    # Platform only: corpus searches carry no team. Null under a team scope.
    corpus_searches: PeriodValue | None = None
    top_agents: list[AnalyticsAgentRow]
    capabilities: list[AnalyticsCapabilityRow]
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def agents_body(
    windows: Windows, team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    metrics = [
        AGENT_TURNS,
        metric(AGENT_CREATED_METRIC),
        metric(DOCUMENT_CREATED_METRIC),
    ]
    aggs: dict[str, Any] = {
        "turns": {
            "filter": AGENT_TURNS,
            "aggs": {"agents": distinct("dims.agent_instance_id")},
        },
        "created": {"filter": metric(AGENT_CREATED_METRIC)},
        "documents": {
            "filter": metric(DOCUMENT_CREATED_METRIC),
            "aggs": {
                "team_space": {
                    "filter": TEAM_SPACE,
                    "aggs": {"teams": distinct("dims.team_id")},
                }
            },
        },
    }
    if not team_ids:
        metrics.append(metric(RAG_SEARCH_METRIC))
        aggs["searches"] = {"filter": metric(RAG_SEARCH_METRIC)}
    return two_period_body(windows, team_ids, metrics, aggs, user_ids=user_ids)


def top_agents_body(
    since: datetime,
    until: datetime,
    team_ids: Sequence[str],
    user_ids: Sequence[str] | None = None,
    days: CountedDays = ALL_DAYS,
) -> dict[str, Any]:
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    time_range(since, until),
                    AGENT_TURNS,
                    *scope_filter(team_ids, user_ids),
                    *days.query_filter(since, until),
                ]
            }
        },
        "aggs": {
            "by_agent": {
                "terms": {
                    "field": "dims.agent_instance_id",
                    "size": TOP_N,
                    "order": [{"conversations": "desc"}, {"users": "desc"}],
                },
                "aggs": {
                    "users": distinct("dims.user_id"),
                    "conversations": distinct("dims.session_id"),
                    "latest_dims": LATEST_AGENT_DIMS,
                },
            }
        },
    }


LATEST_AGENT_DIMS: dict[str, Any] = {
    "top_hits": {
        "size": 1,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": {"includes": ["dims.agent_instance_name", "dims.team_id"]},
    }
}


async def agent_labels(
    buckets: Sequence[dict[str, Any]], request: Request, team_ids: Sequence[str]
) -> dict[str, str]:
    """Instance id -> display label, from each bucket's `latest_dims` hit."""
    id_to_name: dict[str, str] = {}
    id_to_team: dict[str, str] = {}
    for bucket in buckets:
        instance_id = str(bucket["key"])
        hits = bucket.get("latest_dims", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        id_to_name[instance_id] = dims.get("agent_instance_name") or instance_id
        team_id = str(dims.get("team_id") or "")
        if team_id and not is_personal_team_id(team_id):
            id_to_team[instance_id] = team_id
    team_names = (
        {}
        if len(team_ids) == 1
        else await resolve_team_names(request, sorted(set(id_to_team.values())))
    )
    return build_agent_labels(id_to_name, id_to_team, team_names)


async def _top_agents(
    response: dict[str, Any], request: Request, team_ids: Sequence[str]
) -> list[AnalyticsAgentRow]:
    buckets = response.get("aggregations", {}).get("by_agent", {}).get("buckets", [])
    labels = await agent_labels(buckets, request, team_ids)
    return [
        AnalyticsAgentRow(
            agent_instance_id=str(b["key"]),
            label=labels[str(b["key"])],
            users=int(b.get("users", {}).get("value") or 0),
            conversations=int(b.get("conversations", {}).get("value") or 0),
            messages=int(b["doc_count"]),
        )
        for b in buckets
    ]


def capability_usage_body(
    since: datetime,
    until: datetime,
    team_ids: Sequence[str],
    user_ids: Sequence[str] | None = None,
    days: CountedDays = ALL_DAYS,
) -> dict[str, Any]:
    """Tool calls per providing capability; a call paused for a human approval is
    timed again when it resumes, so only its final outcome counts."""
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    time_range(since, until),
                    metric(TOOL_LATENCY_METRIC),
                    {"exists": {"field": "dims.capability_id"}},
                    *scope_filter(team_ids, user_ids),
                    *days.query_filter(since, until),
                ],
                "must_not": [{"term": {"dims.status": "awaiting_human"}}],
            }
        },
        "aggs": {
            "by_capability": {
                "terms": {"field": "dims.capability_id", "size": MAX_CAPABILITIES},
                "aggs": {
                    "agents": distinct("dims.agent_instance_id"),
                    "users": distinct("dims.user_id"),
                    "failed": {"filter": {"term": {"dims.status": "error"}}},
                },
            }
        },
    }


def _capability_usage(response: dict[str, Any]) -> dict[str, AnalyticsCapabilityRow]:
    buckets = (
        response.get("aggregations", {}).get("by_capability", {}).get("buckets", [])
    )
    return {
        str(b["key"]): AnalyticsCapabilityRow(
            capability_id=str(b["key"]),
            agents_equipped=0,
            agents_used=int(b.get("agents", {}).get("value") or 0),
            calls=int(b["doc_count"]),
            users=int(b.get("users", {}).get("value") or 0),
            failed_calls=int(b.get("failed", {}).get("doc_count") or 0),
        )
        for b in buckets
    }


def capability_rows(
    equipped: Sequence[AnalyticsCapabilityRow], usage: dict[str, AnalyticsCapabilityRow]
) -> list[AnalyticsCapabilityRow]:
    """Equipped capabilities with their usage, then capabilities used but equipped
    nowhere today (deselected since), most equipped then most called first."""
    rows = {row.capability_id: row for row in equipped}
    for capability_id, used in usage.items():
        rows[capability_id] = used.model_copy(
            update={
                "agents_equipped": rows[capability_id].agents_equipped
                if capability_id in rows
                else 0
            }
        )
    return sorted(
        rows.values(), key=lambda r: (-r.agents_equipped, -r.calls, r.capability_id)
    )


async def equipped_capabilities(
    request: Request, team_ids: Sequence[TeamId]
) -> list[AnalyticsCapabilityRow]:
    """Agents that have each capability selected today, from their stored tuning."""
    # One query whatever the number of selected teams.
    instances = (
        await get_application_container(request).get_agent_instance_store().list_all()
    )
    if team_ids:
        selected = {str(t) for t in team_ids}
        instances = [i for i in instances if str(i.team_id) in selected]
    counts = Counter(
        capability_id
        for instance in instances
        for capability_id in set(instance.tuning.selected_capability_ids or [])
    )
    return [
        AnalyticsCapabilityRow(capability_id=capability_id, agents_equipped=n)
        for capability_id, n in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


async def query_analytics_agents(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
    days: CountedDays = ALL_DAYS,
) -> AnalyticsAgentsResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user
    windows = Windows.of(since, until, days)
    periods, top, usage, equipped, published, web = await asyncio.gather(
        search(store, agents_body(windows, team_ids, user_ids)),
        search(store, top_agents_body(since, until, team_ids, user_ids, days)),
        search(store, capability_usage_body(since, until, team_ids, user_ids, days)),
        # Configuration, not activity: not narrowed by a user filter.
        equipped_capabilities(request, team_ids),
        agents_created_published(request, windows, team_ids, user_ids),
        web_research_enabled(request),
    )
    capabilities = [
        row
        for row in capability_rows(equipped, _capability_usage(usage))
        if web or row.capability_id != WEB_RESEARCH_CAPABILITY_ID
    ]
    return AnalyticsAgentsResponse(
        agents_used=per_period(periods, sub_value("turns", "agents")),
        agents_created=per_period(periods, doc_count("created")),
        agents_created_published=published,
        documents_added=per_period(periods, doc_count("documents")),
        teams_feeding_corpus=per_period(
            periods,
            lambda b: float(
                b.get("documents", {})
                .get("team_space", {})
                .get("teams", {})
                .get("value")
                or 0
            ),
        ),
        corpus_searches=None
        if team_ids
        else per_period(periods, doc_count("searches")),
        top_agents=await _top_agents(top, request, team_ids),
        capabilities=capabilities,
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_AGENTS_PRESET = PresetDef(
    name="analytics_agents",
    response_model=AnalyticsAgentsResponse,
    handler=query_analytics_agents,
    summary="Agents used, created and published, top agents by conversations, capability equipment and usage, and corpus activity",
    team_scopable=True,
    user_filterable=True,
    day_filterable=True,
)
