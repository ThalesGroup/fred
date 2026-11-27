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

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi import estimate_green_cost, usd_to_eur
from fred_core.kpi.model_impact_factors import load_model_impact_factors
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.analytics_common import search, time_range
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    TOKEN_USAGE_FILTER,
    TimeSeriesPoint,
    TimeSeriesResponse,
)
from control_plane_backend.kpi.utils import Bucket, calendar_histogram, resolve_bucket

logger = logging.getLogger(__name__)

_UNMODELED = "__unmodeled__"  # sentinel for turns with no recorded model_name


async def query_user_token_usage_over_time(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    bucket: Bucket = "auto",
    tz: str = "Europe/Paris",
) -> TimeSeriesResponse:
    # Self-scoped: any authenticated user can see their own consumption.
    # No OpenFGA check needed (RFC KPI-ANALYTICS-RFC.md §2.4).
    histogram = calendar_histogram(
        since, until, resolve_bucket(bucket, since, until), tz
    )
    bounds = histogram["date_histogram"]["extended_bounds"]
    bounds["max"] = max(
        bounds["min"], int((until - timedelta(microseconds=1)).timestamp() * 1000)
    )
    interval = histogram["date_histogram"]["calendar_interval"]
    named_models = [name for name in load_model_impact_factors() if name != "default"]
    histogram["aggs"] = {
        "sum_input": {"sum": {"field": "quantities.input_tokens"}},
        "sum_output": {"sum": {"field": "quantities.output_tokens"}},
        "by_model": {
            "filters": {
                "filters": {
                    name: {"term": {"dims.model_name": name}} for name in named_models
                },
                "other_bucket": True,
                "other_bucket_key": _UNMODELED,
            },
            "aggs": {
                "sum_input": {"sum": {"field": "quantities.input_tokens"}},
                "sum_output": {"sum": {"field": "quantities.output_tokens"}},
            },
        },
    }

    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    time_range(since, until),
                    TOKEN_USAGE_FILTER,
                    {"term": {"dims.user_id": user.uid}},
                ]
            }
        },
        "aggs": {"by_time": histogram},
    }

    resp = await search(store, body)
    buckets = resp.get("aggregations", {}).get("by_time", {}).get("buckets", [])

    rows = []
    for time_bucket in buckets:
        co2e_grams = kwh = cost_usd = 0.0
        for model_name, model_bucket in time_bucket["by_model"]["buckets"].items():
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
                date=time_bucket["key_as_string"],
                value=time_bucket["sum_input"]["value"]
                + time_bucket["sum_output"]["value"],
                co2e_grams=co2e_grams,
                kwh=kwh,
                cost_eur=usd_to_eur(cost_usd),
            )
        )

    return TimeSeriesResponse(
        rows=rows,
        since=since,
        until=until,
        interval=interval,
    )


USER_TOKEN_USAGE_OVER_TIME_PRESET = PresetDef(
    name="user_token_usage_over_time",
    response_model=TimeSeriesResponse,
    handler=query_user_token_usage_over_time,
    summary="The requesting user's own LLM token consumption over time (input + output)",
    self_scoped=True,
    bucketable=True,
)
