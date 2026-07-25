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
Platform-wide or team-scoped token consumption broken down by agent
(OBSERV-02 v3). Same shape as `user_token_usage_by_agent.py`, different scope.

Known scaling caveat (flagged, not fixed here): OpenSearch cannot order a
terms aggregation by the sum of two sibling metrics (input+output tokens)
without a bucket_script, which it also refuses to sort by — the same
limitation `user_token_usage_by_agent.py` already documents. The accepted
workaround there (fetch up to 10000 buckets unbounded, rank in Python) is
fine for one user's handful of agents. At PLATFORM scope, on a large
deployment with many concurrent fred-agents replicas and thousands of agent
instances, this becomes a real per-request cost — every dashboard view
re-runs an unbounded terms aggregation. Not addressed in this pass; a
follow-up could emit a combined `quantities.total_tokens` field at write time
(agent_app.py) so OpenSearch can order server-side, or cache this preset's
result more aggressively than the generic client-side TTL (§2.6).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)

TOP_N = 10
_BUCKET_FETCH_LIMIT = 10_000


async def query_token_usage_by_agent(
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
        {"exists": {"field": "dims.agent_instance_name"}},
    ]
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_agent": {
                "terms": {
                    "field": "dims.agent_instance_name",
                    "size": _BUCKET_FETCH_LIMIT,
                },
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


TOKEN_USAGE_BY_AGENT_PRESET = PresetDef(
    name="token_usage_by_agent",
    response_model=LabelValueResponse,
    handler=query_token_usage_by_agent,
    summary=f"Token consumption broken down by the top {TOP_N} agents, platform-wide or scoped to one team",
    team_scopable=True,
)
