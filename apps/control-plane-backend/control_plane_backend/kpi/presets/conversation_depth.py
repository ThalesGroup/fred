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
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import DistributionResponse
from control_plane_backend.kpi.presets.distribution_utils import (
    TERMS_SIZE,
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

    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": since.isoformat(),
                    "lte": until.isoformat(),
                }
            }
        },
        {"term": {"metric.name": "agent.turn_completed"}},
        # agent.turn_completed only started carrying dims.session_id with issue
        # #2426 (RUNTIME-EXECUTION-CONTRACT.md §8.57). Older rows have no
        # conversation key at all, so they must be excluded — without this
        # filter the terms agg would drop them silently while they still
        # skewed nothing, but an `exists` makes the exclusion explicit and
        # guards against a future null-valued dim collapsing into one giant
        # bucket.
        {"exists": {"field": "dims.session_id"}},
    ]
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})

    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            # One bucket per conversation; doc_count is that conversation's
            # completed-turn count, i.e. its message depth.
            "by_session": {"terms": {"field": "dims.session_id", "size": TERMS_SIZE}},
        },
    }

    resp = store.client.search(index=store.index, body=body)
    return distribution_from_terms_agg(
        resp, agg_name="by_session", since=since, until=until
    )


CONVERSATION_DEPTH_PRESET = PresetDef(
    name="conversation_depth",
    response_model=DistributionResponse,
    handler=query_conversation_depth,
    summary="Distribution of conversations by message count, plus the median messages per conversation",
    team_scopable=True,  # agent.turn_completed carries dims.team_id
)
