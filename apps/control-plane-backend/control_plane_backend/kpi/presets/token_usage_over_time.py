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
Platform-wide or team-scoped token consumption over time (OBSERV-02 v3).

Same `agent.turn_completed` aggregation `user_token_usage_over_time.py`
already uses for the self-scoped personal dashboard — this is the same
underlying data at a different scope (platform when `team_id` is None, one
team otherwise), not a new metric. Green/carbon and $ cost equivalents
(`KPI-ANALYTICS-RFC.md` §2.7, B3/B4) are computed here from a per-bucket
model-name breakdown — one query, not a second preset call.
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
from control_plane_backend.kpi.presets.common import TimeSeriesPoint, TimeSeriesResponse
from control_plane_backend.kpi.utils import resolve_interval

_UNMODELED = "__unmodeled__"  # sentinel for turns with no recorded model_name

logger = logging.getLogger(__name__)


async def query_token_usage_over_time(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> TimeSeriesResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    interval, date_fmt = resolve_interval(since, until)

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
    ]
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": interval,
                    "min_doc_count": 0,
                    "extended_bounds": {
                        "min": since.isoformat(),
                        "max": until.isoformat(),
                    },
                },
                "aggs": {
                    "sum_input": {"sum": {"field": "quantities.input_tokens"}},
                    "sum_output": {"sum": {"field": "quantities.output_tokens"}},
                    "by_model": {
                        "terms": {
                            "field": "dims.model_name",
                            "size": 50,
                            "missing": _UNMODELED,
                        },
                        "aggs": {
                            "sum_input": {"sum": {"field": "quantities.input_tokens"}},
                            "sum_output": {
                                "sum": {"field": "quantities.output_tokens"}
                            },
                        },
                    },
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_time", {}).get("buckets", [])

    rows = []
    for bucket in buckets:
        co2e_grams = kwh = cost_usd = 0.0
        for model_bucket in bucket["by_model"]["buckets"]:
            model_name = model_bucket["key"]
            estimate = estimate_green_cost(
                None if model_name == _UNMODELED else str(model_name),
                input_tokens=model_bucket["sum_input"]["value"],
                output_tokens=model_bucket["sum_output"]["value"],
            )
            co2e_grams += estimate.co2e_grams
            kwh += estimate.kwh
            cost_usd += estimate.cost_usd

        rows.append(
            TimeSeriesPoint(
                date=datetime.fromisoformat(
                    bucket["key_as_string"].replace("Z", "+00:00")
                ).strftime(date_fmt),
                value=bucket["sum_input"]["value"] + bucket["sum_output"]["value"],
                co2e_grams=co2e_grams,
                kwh=kwh,
                cost_usd=cost_usd,
            )
        )

    return TimeSeriesResponse(
        rows=rows,
        since=since,
        until=until,
        interval=interval,
    )


TOKEN_USAGE_OVER_TIME_PRESET = PresetDef(
    name="token_usage_over_time",
    response_model=TimeSeriesResponse,
    handler=query_token_usage_over_time,
    summary="LLM token consumption over time (input + output), platform-wide or scoped to one team",
    team_scopable=True,  # agent.turn_completed carries dims.team_id
)
