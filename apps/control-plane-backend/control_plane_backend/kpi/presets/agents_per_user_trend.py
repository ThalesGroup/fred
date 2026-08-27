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
from control_plane_backend.kpi.presets.common import TimeSeriesResponse
from control_plane_backend.kpi.presets.trend_utils import (
    distinct_slices,
    pool_distinct,
    trend_body,
    trend_response,
)
from control_plane_backend.kpi.utils import resolve_trend_interval


async def query_agents_per_user_trend(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> TimeSeriesResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope) —
    # this handler only ever reads `team_id` to decide the query filter.
    del user, request

    # `distinct_of` rather than the histogram sibling's `cardinality_of`: a
    # cardinality is a per-bucket number, and per-bucket distinct counts cannot
    # be added up over a window (the same agent on Monday and Tuesday is one
    # agent, not two). Breaking each user down by agent *before* bucketing keeps
    # the identities, which is what the union in `pool_distinct` needs.
    #
    # The `exists` filter it adds matters for the same reason as in the
    # histogram: `dims.agent_instance_id` is nullable on session.created_total,
    # and a user whose sessions all lack it would otherwise pool to 0 and drag
    # the median down as a phantom active user.
    resolved = resolve_trend_interval(since, until)
    body = trend_body(
        metric_name="session.created_total",
        group_by="dims.user_id",
        interval=resolved.interval,
        since=since - resolved.lookback,
        until=until,
        team_id=team_id,
        distinct_of="dims.agent_instance_id",
    )

    resp = store.client.search(index=store.index, body=body)
    return trend_response(
        distinct_slices(resp, bucket=resolved.bucket),
        pool=pool_distinct,
        resolved=resolved,
        since=since,
        until=until,
    )


AGENTS_PER_USER_TREND_PRESET = PresetDef(
    name="agents_per_user_trend",
    response_model=TimeSeriesResponse,
    handler=query_agents_per_user_trend,
    summary="Median distinct agents per active user over a trailing window, bucketed over time",
    team_scopable=True,  # session.created_total carries dims.team_id
)
