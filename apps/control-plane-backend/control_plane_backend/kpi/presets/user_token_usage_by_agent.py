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
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)

TOP_N = 10


async def query_user_token_usage_by_agent(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> LabelValueResponse:
    # Self-scoped: any authenticated user can see their own consumption.
    # No OpenFGA check needed (RFC KPI-ANALYTICS-RFC.md §2.4).
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": since.isoformat(),
                                "lte": until.isoformat(),
                            }
                        }
                    },
                    {"term": {"metric.name": "agent.turn_completed"}},
                    {"term": {"dims.user_id": user.uid}},
                    {"exists": {"field": "dims.agent_instance_name"}},
                ]
            }
        },
        "aggs": {
            "by_agent": {
                # No ES-side order-by-total: OpenSearch rejects ordering a terms
                # aggregation by a bucket_script (pipeline aggregations cannot
                # sort buckets). Cardinality here is naturally small — a user
                # talks to a handful of agents, not thousands — so fetch all of
                # them unbounded and rank by combined tokens in Python instead
                # (same pattern agent_prompt_length_distribution.py uses).
                "terms": {"field": "dims.agent_instance_name", "size": 10000},
                "aggs": {
                    "sum_input": {"sum": {"field": "quantities.input_tokens"}},
                    "sum_output": {"sum": {"field": "quantities.output_tokens"}},
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_agent", {}).get("buckets", [])

    totals = [
        (
            str(bucket["key"]),
            int(bucket["sum_input"]["value"] + bucket["sum_output"]["value"]),
        )
        for bucket in buckets
    ]
    totals.sort(key=lambda row: row[1], reverse=True)

    rows = [
        LabelValuePoint(label=label, value=value) for label, value in totals[:TOP_N]
    ]

    return LabelValueResponse(rows=rows, since=since, until=until)


USER_TOKEN_USAGE_BY_AGENT_PRESET = PresetDef(
    name="user_token_usage_by_agent",
    response_model=LabelValueResponse,
    handler=query_user_token_usage_by_agent,
    summary=f"The requesting user's own token consumption broken down by the top {TOP_N} agents",
)
