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
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    MultiSeriesPoint,
    MultiSeriesTimeSeriesResponse,
)
from control_plane_backend.kpi.utils import resolve_interval

logger = logging.getLogger(__name__)

TOP_N = 10

# Base filter applied to both queries: only managed-instance turns that have
# an agent_instance_id. Direct-template-mode turns are excluded — they carry no
# meaningful instance identity and would pollute the chart.
_BASE_FILTERS: list[dict[str, Any]] = [
    {"term": {"metric.name": "agent.turn_completed"}},
    {"exists": {"field": "dims.agent_instance_id"}},
]


def _filters(team_id: TeamId | None) -> list[dict[str, Any]]:
    """A fresh copy of `_BASE_FILTERS`, optionally narrowed to one team.

    Never mutate `_BASE_FILTERS` in place — it is a module-level constant
    shared across every request.
    """
    filters = list(_BASE_FILTERS)
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})
    return filters


async def query_top_agents_by_conversations(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> MultiSeriesTimeSeriesResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    interval, date_fmt = resolve_interval(since, until)

    time_filter: dict[str, Any] = {
        "range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}
    }

    # Phase 1: top N agent instances by turn count.
    # A top_hits sub-agg reads agent_instance_name from the most-recent event —
    # this is the deleted-instance safety net: the name was persisted at emit time.
    top_body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": [time_filter, *_filters(team_id)]}},
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

    # agent_instance_id → name (agent_instance_name if stored, else the id).
    id_to_name: dict[str, str] = {}
    for bucket in top_buckets:
        instance_id = str(bucket["key"])
        hits = bucket.get("latest_name", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        id_to_name[instance_id] = dims.get("agent_instance_name") or instance_id

    # Instance names are not unique — two live instances may share one. Keying
    # the series by name would merge them into a single line whose counts are
    # the sum of both, so the id stays the accumulation key throughout and the
    # name is only ever a display label. Colliding names get a short id suffix
    # so the chart still shows two distinguishable lines.
    name_counts = Counter(id_to_name.values())
    id_to_label: dict[str, str] = {
        instance_id: f"{name} ({instance_id[:8]})" if name_counts[name] > 1 else name
        for instance_id, name in id_to_name.items()
    }

    # Phase 2: time-series breakdown per instance.
    series_body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": [time_filter, *_filters(team_id)]}},
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
                    # `include` pins this sub-agg to the instances phase 1
                    # picked. Without it each date bucket independently returns
                    # *its own* top N, so a globally-top agent that lost a
                    # single bucket to N busier ones silently drops that
                    # bucket's turns from its running total.
                    "by_agent": {
                        "terms": {
                            "field": "dims.agent_instance_id",
                            "size": TOP_N,
                            "include": list(id_to_label),
                        }
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
    # the total number of turns for that agent up to that point in time.
    running: dict[str, float] = {instance_id: 0.0 for instance_id in id_to_label}
    rows: list[MultiSeriesPoint] = []
    for bucket in time_buckets:
        date_label = datetime.fromisoformat(
            bucket["key_as_string"].replace("Z", "+00:00")
        ).strftime(date_fmt)
        for agent_bucket in bucket.get("by_agent", {}).get("buckets", []):
            instance_id = str(agent_bucket["key"])
            if instance_id in running:
                running[instance_id] += float(agent_bucket["doc_count"])
        rows.append(
            MultiSeriesPoint(
                date=date_label,
                values={
                    id_to_label[instance_id]: total
                    for instance_id, total in running.items()
                },
            )
        )

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
    team_scopable=True,  # agent.turn_completed carries dims.team_id
)
