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
Web research volume, estimated provider cost and refusals, from the
content-free `web_research.request` event emitted by Fred Agents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint

# Policy refusals: Fred decided not to read the destination.
BLOCKED_CODES = frozenset(
    {
        "unsafe_destination",
        "too_many_redirects",
        "unsupported_content",
        "response_too_large",
    }
)


class WebResearchSummaryResponse(BaseModel):
    requests: int
    billable_searches: int
    estimated_cost_usd: float
    blocked: int
    saturated: int
    failed: int
    unique_users: int
    p95_ms: float | None
    by_reason: list[LabelValuePoint]
    since: AwareDatetime
    until: AwareDatetime


async def query_web_research_summary(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> WebResearchSummaryResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    filters: list[dict[str, Any]] = [
        {"range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}},
        {"term": {"metric.name": "web_research.request"}},
    ]
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})

    body: dict[str, Any] = {
        "size": 0,
        "track_total_hits": True,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "unique_users": {"cardinality": {"field": "dims.user_id"}},
            "p95": {"percentiles": {"field": "metric.value", "percents": [95]}},
            "billable": {
                "filter": {"exists": {"field": "cost.usd"}},
                "aggs": {"usd": {"sum": {"field": "cost.usd"}}},
            },
            "errors": {"filter": {"term": {"dims.status": "error"}}},
            "by_reason": {"terms": {"field": "dims.error_code", "size": 20}},
        },
    }
    resp = store.client.search(index=store.index, body=body)
    aggs = resp.get("aggregations", {})
    reasons = [
        LabelValuePoint(label=b["key"], value=b["doc_count"])
        for b in aggs.get("by_reason", {}).get("buckets", [])
    ]
    blocked = sum(r.value for r in reasons if r.label in BLOCKED_CODES)
    saturated = sum(r.value for r in reasons if r.label == "busy")
    p95 = aggs.get("p95", {}).get("values", {}).get("95.0")
    billable = aggs.get("billable", {})
    return WebResearchSummaryResponse(
        requests=resp.get("hits", {}).get("total", {}).get("value", 0),
        billable_searches=billable.get("doc_count", 0),
        estimated_cost_usd=round(billable.get("usd", {}).get("value") or 0.0, 4),
        blocked=blocked,
        saturated=saturated,
        failed=aggs.get("errors", {}).get("doc_count", 0) - blocked - saturated,
        unique_users=aggs.get("unique_users", {}).get("value", 0),
        p95_ms=round(p95) if p95 is not None else None,
        by_reason=reasons,
        since=since,
        until=until,
    )


WEB_RESEARCH_SUMMARY_PRESET = PresetDef(
    name="web_research_summary",
    response_model=WebResearchSummaryResponse,
    handler=query_web_research_summary,
    summary="Web research volume, estimated provider cost, refusals and latency",
    team_scopable=True,
    platform_admin_only=True,
)
