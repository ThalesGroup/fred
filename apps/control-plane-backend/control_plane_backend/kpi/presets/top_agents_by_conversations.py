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
from fred_core.common import TeamId, is_personal_team_id
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    MultiSeriesPoint,
    MultiSeriesTimeSeriesResponse,
)
from control_plane_backend.kpi.presets.team_names import resolve_team_names
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


def _build_labels(
    id_to_name: dict[str, str],
    id_to_team_id: dict[str, str],
    team_names: dict[str, str],
) -> dict[str, str]:
    """agent_instance_id -> the label its series is drawn under.

    Instance names are not unique across teams, so a cross-team chart qualifies
    each one with its owning team. Pass an empty `team_names` to keep bare
    names, which is what a team-scoped request does.
    """
    qualified: dict[str, str] = {}
    for instance_id, name in id_to_name.items():
        team_name = team_names.get(id_to_team_id.get(instance_id, ""))
        qualified[instance_id] = f"{name} - {team_name}" if team_name else name

    # Two instances can still land on one label. The id stays the accumulation
    # key throughout, so only the display label needs breaking apart.
    label_counts = Counter(qualified.values())
    return {
        instance_id: f"{label} ({instance_id[:8]})"
        if label_counts[label] > 1
        else label
        for instance_id, label in qualified.items()
    }


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
    del user

    interval, date_fmt = resolve_interval(since, until)

    time_filter: dict[str, Any] = {
        "range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}
    }

    # Phase 1: top N agent instances by turn count.
    # A top_hits sub-agg reads the instance's name and owning team from its
    # most-recent event: both were persisted at emit time, so a since-deleted
    # instance still labels its own line.
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
                    "latest_dims": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": {
                                "includes": [
                                    "dims.agent_instance_name",
                                    "dims.team_id",
                                ]
                            },
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

    # agent_instance_id → name / owning team, both read from that instance's
    # most recent event (the deleted-instance safety net: they were persisted
    # at emit time).
    id_to_name: dict[str, str] = {}
    id_to_team_id: dict[str, str] = {}
    for bucket in top_buckets:
        instance_id = str(bucket["key"])
        hits = bucket.get("latest_dims", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        id_to_name[instance_id] = dims.get("agent_instance_name") or instance_id
        # A personal space has no registry row, so its id would resolve to
        # itself - and that id embeds the owner's uid. Never label with it.
        event_team_id = str(dims.get("team_id") or "")
        if event_team_id and not is_personal_team_id(event_team_id):
            id_to_team_id[instance_id] = event_team_id

    # Empty when the caller already scoped to one team: every series would
    # otherwise repeat the filter it set.
    team_names = (
        {}
        if team_id is not None
        else await resolve_team_names(request, sorted(set(id_to_team_id.values())))
    )
    id_to_label = _build_labels(id_to_name, id_to_team_id, team_names)

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
