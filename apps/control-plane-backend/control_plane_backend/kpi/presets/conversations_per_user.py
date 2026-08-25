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

logger = logging.getLogger(__name__)


async def query_conversations_per_user(
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

    # `dims.user_id` is injected by KPIWriter from the emitting actor, so every
    # session.created_total row carries it — no `exists` guard needed.
    body = distribution_body(
        metric_name="session.created_total",
        group_by="dims.user_id",
        since=since,
        until=until,
        team_id=None if team_id is None else str(team_id),
    )

    resp = store.client.search(index=store.index, body=body)
    return distribution_from_terms_agg(resp, since=since, until=until)


CONVERSATIONS_PER_USER_PRESET = PresetDef(
    name="conversations_per_user",
    response_model=DistributionResponse,
    handler=query_conversations_per_user,
    summary="Distribution of users by conversations created, plus the median per active user",
    team_scopable=True,  # session.created_total carries dims.team_id
)
