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
Storage usage vs. quota, per team (OBSERV-02 v3, `KPI-ANALYTICS-RFC.md` §2.9).

Reads `TeamMetadata` directly — `current_resources_storage_size` and
`max_resources_storage_size` already exist and are already maintained
elsewhere (upload flow, migration import/export); this preset adds no new
state, it only exposes the existing fields through the same KPI preset
surface every other dashboard widget uses. Not an OpenSearch query — the
`store` parameter every preset handler receives is unused here (current-state
gauge, not an event aggregation), consistent with how `documents_total` and
`agents_total` already mix Postgres and OpenSearch sources behind the same
preset contract.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from fred_core.teams.metadata_store import TeamMetadata

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import TeamStorageResponse, TeamStorageRow


def _row(team: TeamMetadata, default_quota: int | None) -> TeamStorageRow:
    quota = (
        team.max_resources_storage_size
        if team.max_resources_storage_size is not None
        else default_quota
    )
    return TeamStorageRow(
        team_id=str(team.id),
        label=team.name,
        used_bytes=team.current_resources_storage_size or 0,
        quota_bytes=quota,
    )


async def query_storage_by_team(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> TeamStorageResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, store

    container = get_application_container(request)
    metadata_store = container.get_team_metadata_store()
    default_quota = container.configuration.app.default_team_max_resources_storage_size

    if team_id is not None:
        team = await metadata_store.get_by_team_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=f"team {team_id!r} not found")
        rows = [_row(team, default_quota)]
    else:
        teams = await metadata_store.list_all()
        rows = sorted(
            (_row(t, default_quota) for t in teams),
            key=lambda r: r.used_bytes,
            reverse=True,
        )

    return TeamStorageResponse(rows=rows, since=since, until=until)


STORAGE_BY_TEAM_PRESET = PresetDef(
    name="storage_by_team",
    response_model=TeamStorageResponse,
    handler=query_storage_by_team,
    summary="Current resource storage usage vs. quota, per team (ranked platform-wide, or one team when scoped)",
    team_scopable=True,
)
