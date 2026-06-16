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
from fred_core import KeycloakUser, require_admin
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    MultiSeriesPoint,
    MultiSeriesTimeSeriesResponse,
)
from control_plane_backend.kpi.utils import resolve_interval

logger = logging.getLogger(__name__)

TOP_N = 10

# Shared filter applied to both queries: only managed-instance turns that have
# an agent_instance_id. Direct-template-mode turns are excluded — they carry no
# meaningful instance identity and would pollute the chart.
_BASE_FILTERS: list[dict[str, Any]] = [
    {"term": {"metric.name": "agent.turn_completed"}},
    {"exists": {"field": "dims.agent_instance_id"}},
]


async def query_top_agents_by_conversations(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> MultiSeriesTimeSeriesResponse:
    require_admin(user)

    interval, date_fmt = resolve_interval(since, until)

    time_filter: dict[str, Any] = {
        "range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}
    }

    # Phase 1: top N agent instances by turn count.
    # A top_hits sub-agg reads agent_instance_name from the most-recent event —
    # this is the deleted-instance safety net: the name was persisted at emit time.
    top_body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": [time_filter, *_BASE_FILTERS]}},
        "aggs": {
            "by_agent": {
                "terms": {
                    "field": "dims.agent_instance_id",
                    "size": TOP_N,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    "latest_name": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": {"includes": ["dims.agent_instance_name"]},
                        }
                    }
                },
            }
        },
    }

    top_resp = store.client.search(index=store.index, body=top_body)
    top_buckets = (
        top_resp.get("aggregations", {}).get("by_agent", {}).get("buckets", [])
    )

    if not top_buckets:
        return MultiSeriesTimeSeriesResponse(
            rows=[],
            series=[],
            since=since,
            until=until,
            interval=interval,
        )

    # agent_instance_id → display label (agent_instance_name if stored, else the id).
    id_to_label: dict[str, str] = {}
    for bucket in top_buckets:
        instance_id = str(bucket["key"])
        hits = bucket.get("latest_name", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        id_to_label[instance_id] = dims.get("agent_instance_name") or instance_id

    # Phase 2: time-series breakdown per instance.
    series_body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": [time_filter, *_BASE_FILTERS]}},
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
                    "by_agent": {
                        "terms": {"field": "dims.agent_instance_id", "size": TOP_N}
                    }
                },
            }
        },
    }

    series_resp = store.client.search(index=store.index, body=series_body)
    time_buckets = (
        series_resp.get("aggregations", {}).get("by_time", {}).get("buckets", [])
    )

    series_labels = list(id_to_label.values())

    # Accumulate per-bucket counts into running totals so each point represents
    # the total number of conversations for that agent up to that point in time.
    running: dict[str, float] = {label: 0.0 for label in series_labels}
    rows: list[MultiSeriesPoint] = []
    for bucket in time_buckets:
        date_label = datetime.fromisoformat(
            bucket["key_as_string"].replace("Z", "+00:00")
        ).strftime(date_fmt)
        for agent_bucket in bucket.get("by_agent", {}).get("buckets", []):
            label = id_to_label.get(str(agent_bucket["key"]))
            if label is not None:
                running[label] += float(agent_bucket["doc_count"])
        rows.append(MultiSeriesPoint(date=date_label, values=dict(running)))

    return MultiSeriesTimeSeriesResponse(
        rows=rows,
        series=series_labels,
        since=since,
        until=until,
        interval=interval,
    )


TOP_AGENTS_BY_CONVERSATIONS_PRESET = PresetDef(
    name="top_agents_by_conversations",
    response_model=MultiSeriesTimeSeriesResponse,
    handler=query_top_agents_by_conversations,
    summary=f"Top {TOP_N} agents by conversation turn count, with per-bucket time series",
)
