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
from fred_core import ORGANIZATION_ID, KeycloakUser, OrganizationPermission
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)

BUCKET_SIZE = 500
OVERFLOW_THRESHOLD = 20_000
OVERFLOW_LABEL = "20000+"


async def query_agent_prompt_length_distribution(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> LabelValueResponse:
    await (
        get_application_container(request)
        .get_rebac_engine()
        .check_user_permission_or_raise(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
    )

    # Pass 1 — agents created on or before `until`.
    # We use a large `size` on the terms agg to capture all known agents.
    created_body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"lte": until.isoformat()}}},
                    {"term": {"metric.name": "agent.created_total"}},
                    {"exists": {"field": "dims.agent_instance_id"}},
                ]
            }
        },
        "aggs": {
            "by_agent": {
                "terms": {"field": "dims.agent_instance_id", "size": 10000},
            }
        },
    }
    created_resp = store.client.search(index=store.index, body=created_body)
    created_ids: set[str] = {
        str(b["key"])
        for b in created_resp.get("aggregations", {})
        .get("by_agent", {})
        .get("buckets", [])
    }

    if not created_ids:
        return LabelValueResponse(rows=[], since=since, until=until)

    # Pass 1b — agents deleted strictly before `since` (they were gone before the window).
    deleted_body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"lt": since.isoformat()}}},
                    {"term": {"metric.name": "agent.deleted_total"}},
                    {"exists": {"field": "dims.agent_instance_id"}},
                ]
            }
        },
        "aggs": {
            "by_agent": {
                "terms": {"field": "dims.agent_instance_id", "size": 10000},
            }
        },
    }
    deleted_resp = store.client.search(index=store.index, body=deleted_body)
    deleted_before_window: set[str] = {
        str(b["key"])
        for b in deleted_resp.get("aggregations", {})
        .get("by_agent", {})
        .get("buckets", [])
    }

    alive_ids = created_ids - deleted_before_window
    if not alive_ids:
        return LabelValueResponse(rows=[], since=since, until=until)

    # Pass 2 — for each alive agent, find the latest lifecycle event (created or
    # updated) with @timestamp ≤ until and read system_prompt_chars from its dims.
    latest_body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"lte": until.isoformat()}}},
                    {
                        "terms": {
                            "metric.name": ["agent.created_total", "agent.updated"]
                        }
                    },
                    {"terms": {"dims.agent_instance_id": list(alive_ids)}},
                    {"exists": {"field": "dims.system_prompt_chars"}},
                ]
            }
        },
        "aggs": {
            "by_agent": {
                "terms": {"field": "dims.agent_instance_id", "size": 10000},
                "aggs": {
                    "latest_event": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": {"includes": ["dims.system_prompt_chars"]},
                        }
                    }
                },
            }
        },
    }
    latest_resp = store.client.search(index=store.index, body=latest_body)

    # Collect prompt lengths and bucket them.
    bucket_counts: dict[
        int, int
    ] = {}  # keyed by lower bound (int) for easy gap-filling
    for agent_bucket in (
        latest_resp.get("aggregations", {}).get("by_agent", {}).get("buckets", [])
    ):
        hits = agent_bucket.get("latest_event", {}).get("hits", {}).get("hits", [])
        if not hits:
            continue
        raw = hits[0]["_source"].get("dims", {}).get("system_prompt_chars", 0)
        try:
            chars = int(raw)
        except (TypeError, ValueError):
            chars = 0
        if chars >= OVERFLOW_THRESHOLD:
            bucket_counts[-1] = bucket_counts.get(-1, 0) + 1
        else:
            low = (chars // BUCKET_SIZE) * BUCKET_SIZE
            bucket_counts[low] = bucket_counts.get(low, 0) + 1

    if not bucket_counts:
        return LabelValueResponse(rows=[], since=since, until=until)

    # Fill every empty 500-char slot from 0 up to OVERFLOW_THRESHOLD,
    # then append the overflow bucket so the chart has no gaps.
    regular_max = max((k for k in bucket_counts if k >= 0), default=-1)
    cap = min(regular_max, OVERFLOW_THRESHOLD - BUCKET_SIZE)
    rows = [
        LabelValuePoint(
            label=f"{low}-{low + BUCKET_SIZE}", value=bucket_counts.get(low, 0)
        )
        for low in range(0, cap + BUCKET_SIZE, BUCKET_SIZE)
    ]
    rows.append(LabelValuePoint(label=OVERFLOW_LABEL, value=bucket_counts.get(-1, 0)))

    return LabelValueResponse(rows=rows, since=since, until=until)


AGENT_PROMPT_LENGTH_DISTRIBUTION_PRESET = PresetDef(
    name="agent_prompt_length_distribution",
    response_model=LabelValueResponse,
    handler=query_agent_prompt_length_distribution,
    summary="Distribution of agent system prompt lengths (chars) bucketed in 500-char ranges",
)
