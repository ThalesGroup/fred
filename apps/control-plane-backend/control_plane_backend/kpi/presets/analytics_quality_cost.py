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

"""Quality and cost tab: failed answers, cost in euros, tokens, footprint, by model and by agent.

An error turn also emits `agent.turn_completed`, so the failure rate divides by turns only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.counted_days import ALL_DAYS, CountedDays
from control_plane_backend.kpi.presets.analytics_agents import (
    LATEST_AGENT_DIMS,
    agent_labels,
)
from control_plane_backend.kpi.presets.analytics_common import (
    TURN_ERRORS,
    TURNS,
    PeriodValue,
    TokenTotals,
    Windows,
    distinct,
    doc_count,
    model_totals,
    per_period,
    period_buckets,
    ratio,
    search,
    sub_value,
    time_range,
    token_aggs,
    token_totals,
    two_period_body,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    BY_AGENT_SCOPE_FILTER,
    CREATION_ASSISTANT_LABEL,
    TOKEN_USAGE_FILTER,
    scope_filter,
)

TOP_N = 10
# Agents fetched by input tokens (the bulk of the cost) before ranking by cost.
AGENT_FETCH = 50


class AnalyticsModelRow(BaseModel):
    model: str
    message_share: float | None = None
    input_tokens: int
    output_tokens: int
    cost_eur: float
    co2e_grams: float


class AnalyticsAgentCostRow(BaseModel):
    # Agent name, or the creation assistant label translated by the page.
    label: str
    tokens: int
    cost_eur: float
    users: int
    cost_eur_per_user: float | None = None


class AnalyticsQualityCostResponse(BaseModel):
    failed_turn_rate: PeriodValue
    cost_eur: PeriodValue
    cost_eur_per_active_user: PeriodValue
    input_tokens: PeriodValue
    output_tokens: PeriodValue
    cached_input_tokens: PeriodValue
    co2e_grams: PeriodValue
    kwh: PeriodValue
    models: list[AnalyticsModelRow]
    agents: list[AnalyticsAgentCostRow]
    since: AwareDatetime
    until: AwareDatetime
    previous_since: AwareDatetime


def quality_body(
    windows: Windows, team_ids: Sequence[str], user_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    tokens = token_aggs()
    tokens["aggs"]["by_model"]["aggs"]["turns"] = {"filter": TURNS}
    return two_period_body(
        windows,
        team_ids,
        [TURNS, TURN_ERRORS, TOKEN_USAGE_FILTER],
        {
            "turns": {"filter": TURNS, "aggs": {"users": distinct("dims.user_id")}},
            "errors": {"filter": TURN_ERRORS},
            "tokens": tokens,
        },
        user_ids=user_ids,
    )


def agent_cost_body(
    since: datetime,
    until: datetime,
    team_ids: Sequence[str],
    user_ids: Sequence[str] | None = None,
    days: CountedDays = ALL_DAYS,
) -> dict[str, Any]:
    by_model = token_aggs()["aggs"]["by_model"]
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    time_range(since, until),
                    TOKEN_USAGE_FILTER,
                    BY_AGENT_SCOPE_FILTER,
                    *scope_filter(team_ids, user_ids),
                    *days.query_filter(since, until),
                ]
            }
        },
        "aggs": {
            "by_agent": {
                # By id: names are unique per team only. Creation assistant events carry no agent.
                "terms": {
                    "field": "dims.agent_instance_id",
                    "size": AGENT_FETCH,
                    "missing": CREATION_ASSISTANT_LABEL,
                    "order": {"input": "desc"},
                },
                "aggs": {
                    "latest_dims": LATEST_AGENT_DIMS,
                    "input": {"sum": {"field": "quantities.input_tokens"}},
                    "users": distinct("dims.user_id"),
                    "by_model": by_model,
                },
            }
        },
    }


def _models(current: dict[str, Any]) -> list[AnalyticsModelRow]:
    buckets = current.get("tokens", {}).get("by_model", {}).get("buckets", [])
    turns = sum(int(b.get("turns", {}).get("doc_count", 0)) for b in buckets)
    rows = []
    for bucket in buckets:
        totals = model_totals(bucket)
        model_turns = int(bucket.get("turns", {}).get("doc_count", 0))
        rows.append(
            AnalyticsModelRow(
                model=str(bucket["key"]),
                message_share=model_turns / turns if turns else None,
                input_tokens=int(totals.input_tokens),
                output_tokens=int(totals.output_tokens),
                cost_eur=totals.cost_eur,
                co2e_grams=totals.co2e_grams,
            )
        )
    rows.sort(key=lambda r: r.input_tokens + r.output_tokens, reverse=True)
    return rows


async def _agents(
    response: dict[str, Any], request: Request, team_ids: Sequence[str]
) -> list[AnalyticsAgentCostRow]:
    buckets = response.get("aggregations", {}).get("by_agent", {}).get("buckets", [])
    labels = await agent_labels(
        [b for b in buckets if b["key"] != CREATION_ASSISTANT_LABEL], request, team_ids
    )
    rows = []
    for bucket in buckets:
        totals = TokenTotals()
        for model_bucket in bucket.get("by_model", {}).get("buckets", []):
            totals.add(model_totals(model_bucket))
        users = int(bucket.get("users", {}).get("value") or 0)
        rows.append(
            AnalyticsAgentCostRow(
                label=labels.get(str(bucket["key"]), CREATION_ASSISTANT_LABEL),
                tokens=int(totals.input_tokens + totals.output_tokens),
                cost_eur=totals.cost_eur,
                users=users,
                cost_eur_per_user=totals.cost_eur / users if users else None,
            )
        )
    rows.sort(key=lambda r: (r.cost_eur, r.tokens), reverse=True)
    return rows[:TOP_N]


async def query_analytics_quality_cost(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_ids: Sequence[TeamId] = (),
    user_ids: Sequence[str] | None = None,
    days: CountedDays = ALL_DAYS,
) -> AnalyticsQualityCostResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user
    windows = Windows.of(since, until, days)
    periods, by_agent = await asyncio.gather(
        search(store, quality_body(windows, team_ids, user_ids)),
        search(store, agent_cost_body(since, until, team_ids, user_ids, days)),
    )

    current, previous = period_buckets(periods)
    tokens_now = token_totals(current.get("tokens", {})) if current else None
    tokens_before = token_totals(previous.get("tokens", {})) if previous else None

    def totals(field: str) -> PeriodValue:
        return PeriodValue(
            current=getattr(tokens_now, field) if tokens_now else None,
            previous=getattr(tokens_before, field) if tokens_before else None,
        )

    cost = totals("cost_eur")
    return AnalyticsQualityCostResponse(
        failed_turn_rate=ratio(
            per_period(periods, doc_count("errors")),
            per_period(periods, doc_count("turns")),
        ),
        cost_eur=cost,
        cost_eur_per_active_user=ratio(
            cost, per_period(periods, sub_value("turns", "users"))
        ),
        input_tokens=totals("input_tokens"),
        output_tokens=totals("output_tokens"),
        cached_input_tokens=totals("cached_input_tokens"),
        co2e_grams=totals("co2e_grams"),
        kwh=totals("kwh"),
        models=_models(current),
        agents=await _agents(by_agent, request, team_ids),
        since=since,
        until=until,
        previous_since=windows.previous_since,
    )


ANALYTICS_QUALITY_COST_PRESET = PresetDef(
    name="analytics_quality_cost",
    response_model=AnalyticsQualityCostResponse,
    handler=query_analytics_quality_cost,
    summary="Failed answers, cost in EUR, tokens and footprint, by model and by agent, with the previous period",
    team_scopable=True,
    user_filterable=True,
    day_filterable=True,
)
