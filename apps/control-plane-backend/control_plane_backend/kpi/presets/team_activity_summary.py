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
One team's activity/inactivity trend — `team_admin`'s governance-focused
Activités content (OBSERV-02 v3, `KPI-ANALYTICS-RFC.md` §2.5). Derived from
`session.created_total`, the same event `sessions_over_time`/`top_teams_by_sessions`
already aggregate — no new instrumentation.

Unlike every other preset in this package, `team_id` is REQUIRED, not
optional: "is the platform active" is not a meaningful single scalar the way
"is this one team active" is. The router still treats `team_id` as an
optional query param uniformly (KpiScope authorization doesn't change), so
this handler rejects a missing `team_id` itself with a 400, the same way a
non-`team_scopable` preset rejects an unwanted one — just the inverse case.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import TeamActivitySummaryResponse

logger = logging.getLogger(__name__)


async def query_team_activity_summary(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> TeamActivitySummaryResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    if team_id is None:
        raise HTTPException(
            status_code=400,
            detail="team_activity_summary requires team_id — there is no platform-wide equivalent",
        )

    team_filter = {"term": {"dims.team_id": str(team_id)}}

    range_body: dict[str, Any] = {
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
                    team_filter,
                ]
            }
        },
    }
    range_resp = store.client.search(index=store.index, body=range_body)
    sessions_in_range = int(range_resp.get("hits", {}).get("total", {}).get("value", 0))

    last_active_body: dict[str, Any] = {
        "size": 1,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"metric.name": "session.created_total"}},
                    team_filter,
                ]
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": ["@timestamp"],
    }
    last_active_resp = store.client.search(index=store.index, body=last_active_body)
    hits = last_active_resp.get("hits", {}).get("hits", [])
    last_active_at = (
        datetime.fromisoformat(hits[0]["_source"]["@timestamp"].replace("Z", "+00:00"))
        if hits
        else None
    )

    return TeamActivitySummaryResponse(
        last_active_at=last_active_at,
        sessions_in_range=sessions_in_range,
        trend="active" if sessions_in_range > 0 else "quiet",
        since=since,
        until=until,
    )


TEAM_ACTIVITY_SUMMARY_PRESET = PresetDef(
    name="team_activity_summary",
    response_model=TeamActivitySummaryResponse,
    handler=query_team_activity_summary,
    summary="One team's activity/inactivity trend — last active timestamp and session count over the range",
    team_scopable=True,
)
