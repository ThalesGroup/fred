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

from datetime import datetime

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import DistributionResponse
from control_plane_backend.kpi.presets.distribution_utils import (
    distribution_body,
    distribution_from_terms_agg,
)


async def query_agents_per_user(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> DistributionResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope) —
    # this handler only ever reads `team_id` to decide the query filter.
    del user, request

    # `dims.agent_instance_id` is nullable on session.created_total (a session
    # can be created without one). A cardinality agg already ignores such rows;
    # the `exists` filter `cardinality_of` adds is for users whose sessions all
    # lack it — kept, they would land at cardinality 0, dropped by the histogram
    # but counted by the median, splitting the two populations.
    body = distribution_body(
        metric_name="session.created_total",
        group_by="dims.user_id",
        since=since,
        until=until,
        team_id=team_id,
        cardinality_of="dims.agent_instance_id",
    )

    resp = store.client.search(index=store.index, body=body)
    return distribution_from_terms_agg(resp, since=since, until=until)


AGENTS_PER_USER_PRESET = PresetDef(
    name="agents_per_user",
    response_model=DistributionResponse,
    handler=query_agents_per_user,
    summary="Distribution of users by distinct agents talked to, plus the median per active user",
    team_scopable=True,  # session.created_total carries dims.team_id
)
