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
    count_slices,
    pool_counts,
    trend_body,
    trend_response,
)
from control_plane_backend.kpi.utils import resolve_trend_interval


async def query_conversation_depth_trend(
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

    # Pooling turns count over the window: a conversation spanning several
    # buckets is one entity with the sum of its turns, not one shallow
    # conversation per bucket.
    #
    # `require_group_by` carries the same caveat as the histogram sibling:
    # agent.turn_completed only started carrying dims.session_id with issue
    # #2426 (RUNTIME-EXECUTION-CONTRACT.md §8.57), so a range reaching back
    # before that deployment shows nothing there rather than a wrong number —
    # and rows nulled by `OpenSearchKPIStore.anonymise_for_session` (RGPD
    # erasure) stay out, as they must.
    resolved = resolve_trend_interval(since, until)
    body = trend_body(
        metric_name="agent.turn_completed",
        group_by="dims.session_id",
        interval=resolved.interval,
        since=since - resolved.lookback,
        until=until,
        team_id=team_id,
        require_group_by=True,
    )

    resp = store.client.search(index=store.index, body=body)
    return trend_response(
        count_slices(resp, bucket=resolved.bucket),
        pool=pool_counts,
        resolved=resolved,
        since=since,
        until=until,
    )


CONVERSATION_DEPTH_TREND_PRESET = PresetDef(
    name="conversation_depth_trend",
    response_model=TimeSeriesResponse,
    handler=query_conversation_depth_trend,
    summary="Median messages per conversation over a trailing window, bucketed over time",
    team_scopable=True,  # agent.turn_completed carries dims.team_id
)
