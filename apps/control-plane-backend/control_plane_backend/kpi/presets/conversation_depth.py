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


async def query_conversation_depth(
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

    # One bucket per conversation; doc_count is that conversation's
    # completed-turn count. The dashboard calls a turn a "message", following
    # `messages_over_time` ("Agent turn completions (messages)") and the Overview
    # tile above this section — one turn is one user message plus its answer, so
    # the two labels must not diverge inside the same page.
    #
    # `require_group_by` matters here: agent.turn_completed only started carrying
    # dims.session_id with issue #2426 (RUNTIME-EXECUTION-CONTRACT.md §8.57), so
    # this metric is forward-only — rows written before that deployment have no
    # conversation key and cannot be attributed to one. Excluding them explicitly
    # states that intent rather than leaving the terms agg to skip them as a side
    # effect. Rows whose session_id was nulled by
    # `OpenSearchKPIStore.anonymise_for_session` (RGPD erasure) drop out here too,
    # which is correct — an erased conversation must not reappear as a data point.
    body = distribution_body(
        metric_name="agent.turn_completed",
        group_by="dims.session_id",
        since=since,
        until=until,
        team_id=None if team_id is None else str(team_id),
        require_group_by=True,
    )

    resp = store.client.search(index=store.index, body=body)
    return distribution_from_terms_agg(resp, since=since, until=until)


CONVERSATION_DEPTH_PRESET = PresetDef(
    name="conversation_depth",
    response_model=DistributionResponse,
    handler=query_conversation_depth,
    summary="Distribution of conversations by message count, plus the median messages per conversation",
    team_scopable=True,  # agent.turn_completed carries dims.team_id
)
