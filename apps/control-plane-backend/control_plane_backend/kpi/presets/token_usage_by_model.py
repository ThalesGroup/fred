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

"""
Platform-wide or team-scoped token consumption broken down by model
(OBSERV-02 v3). Same shape as `user_token_usage_by_model.py`, different scope.

Unlike `token_usage_by_agent.py`, `dims.model_name` cardinality is bounded by
the platform's model catalog (a handful of distinct models, not one per agent
instance) — the fetch-unbounded-then-rank-in-Python pattern carries no
platform-scale caveat here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi import estimate_green_cost
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)

TOP_N = 10


async def query_token_usage_by_model(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> LabelValueResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": since.isoformat(),
                    "lte": until.isoformat(),
                }
            }
        },
        {"term": {"metric.name": "agent.turn_completed"}},
        {"exists": {"field": "dims.model_name"}},
    ]
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_model": {
                "terms": {"field": "dims.model_name", "size": 10000},
                "aggs": {
                    "sum_input": {"sum": {"field": "quantities.input_tokens"}},
                    "sum_output": {"sum": {"field": "quantities.output_tokens"}},
                    "sum_cache_read": {
                        "sum": {"field": "quantities.cache_read_tokens"}
                    },
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_model", {}).get("buckets", [])

    totals = []
    for bucket in buckets:
        model_name = str(bucket["key"])
        input_tokens = bucket["sum_input"]["value"]
        output_tokens = bucket["sum_output"]["value"]
        cache_read_tokens = bucket["sum_cache_read"]["value"]
        estimate = estimate_green_cost(
            model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        totals.append(
            (
                model_name,
                int(input_tokens + output_tokens),
                estimate.co2e_grams,
                estimate.kwh,
                estimate.cost_usd,
            )
        )
    totals.sort(key=lambda row: row[1], reverse=True)

    rows = [
        LabelValuePoint(
            label=label, value=value, co2e_grams=co2e_grams, kwh=kwh, cost_usd=cost_usd
        )
        for label, value, co2e_grams, kwh, cost_usd in totals[:TOP_N]
    ]

    return LabelValueResponse(rows=rows, since=since, until=until)


TOKEN_USAGE_BY_MODEL_PRESET = PresetDef(
    name="token_usage_by_model",
    response_model=LabelValueResponse,
    handler=query_token_usage_by_model,
    summary=f"Token consumption broken down by the top {TOP_N} models, platform-wide or scoped to one team",
    team_scopable=True,
)
