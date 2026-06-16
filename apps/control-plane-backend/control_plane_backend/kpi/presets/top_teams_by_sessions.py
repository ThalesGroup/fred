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
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse
from control_plane_backend.teams.dependencies import get_team_service_dependencies

logger = logging.getLogger(__name__)

TOP_N = 20


async def _resolve_team_names(request: Request, team_ids: list[str]) -> dict[str, str]:
    """Return {team_id: display_name} for each id. Falls back to the id on any error."""
    if not team_ids:
        return {}
    try:
        deps = get_team_service_dependencies(request)
        admin = deps.create_keycloak_admin_client()
        names: dict[str, str] = {}
        for tid in team_ids:
            try:
                a_get_group = getattr(admin, "a_get_group")
                raw = await a_get_group(tid)
                names[tid] = str(raw.get("name") or tid)
            except Exception:
                names[tid] = tid
        return names
    except Exception:
        return {tid: tid for tid in team_ids}


async def query_top_teams_by_sessions(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> LabelValueResponse:
    require_admin(user)

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
                    {"term": {"metric.name": "session.created_total"}},
                    {"term": {"dims.scope_type": "team"}},
                ]
            }
        },
        "aggs": {
            "by_team": {
                "terms": {
                    "field": "dims.team_id",
                    "size": TOP_N,
                    "order": {"_count": "desc"},
                }
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_team", {}).get("buckets", [])

    team_ids = [b["key"] for b in buckets]
    names = await _resolve_team_names(request, team_ids)

    rows = [
        LabelValuePoint(
            label=names.get(str(bucket["key"])) or str(bucket["key"]),
            value=bucket["doc_count"],
        )
        for bucket in buckets
    ]

    return LabelValueResponse(rows=rows, since=since, until=until)


TOP_TEAMS_BY_SESSIONS_PRESET = PresetDef(
    name="top_teams_by_sessions",
    response_model=LabelValueResponse,
    handler=query_top_teams_by_sessions,
    summary=f"Top {TOP_N} teams by conversation count over the selected time range",
)
