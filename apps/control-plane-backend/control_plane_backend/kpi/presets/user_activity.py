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

"""Self-scoped "your activity" presets for the home dashboard (#2298).

Three scalar-with-delta metrics, each filtered to the requesting user's own
events (`dims.user_id`) — no team scoping, no OpenFGA check (the router's
`self_scoped` path handles authorization, same contract as the
`user_token_usage_*` presets):

  - user_sessions_total     — conversations the user created in the window
  - user_messages_total     — turns the user sent in the window
  - user_agents_used_total  — distinct agents the user talked to in the window

`value` is the count over the requested window [since, until]; `delta` is the
absolute change vs the immediately preceding equal-length window
[since - (until - since), since]. The frontend turns that into the ▲/▼ % chip
(prev = value - delta), which keeps every ScalarWithDeltaResponse preset on the
same "value + absolute net change" contract as agents_total / documents_total.

Both underlying events already carry `dims.user_id` (the KPI writer folds the
actor in — see kpi_writer.py), so these are pure reads: no emitter change, no
backfill. Caveat: right after KPI instrumentation is first deployed the
previous window can be empty for reasons other than genuine inactivity, briefly
inflating the delta — acceptable for a brand-new dashboard, revisit if it
misleads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import ScalarWithDeltaResponse

_SESSION_CREATED = "session.created_total"
_TURN_COMPLETED = "agent.turn_completed"


def _user_window_filter(
    metric_name: str, since: datetime, until: datetime, user_id: str
) -> list[dict[str, Any]]:
    return [
        {"range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}},
        {"term": {"metric.name": metric_name}},
        {"term": {"dims.user_id": user_id}},
    ]


def _count_user_events(
    store: OpenSearchKPIStore,
    metric_name: str,
    since: datetime,
    until: datetime,
    user_id: str,
) -> int:
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {"filter": _user_window_filter(metric_name, since, until, user_id)}
        },
        "aggs": {"total": {"value_count": {"field": "metric.name"}}},
    }
    resp = store.client.search(index=store.index, body=body)
    return int(resp.get("aggregations", {}).get("total", {}).get("value", 0))


def _distinct_user_agents(
    store: OpenSearchKPIStore, since: datetime, until: datetime, user_id: str
) -> int:
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": _user_window_filter(_TURN_COMPLETED, since, until, user_id)
            }
        },
        "aggs": {"distinct": {"cardinality": {"field": "dims.agent_instance_name"}}},
    }
    resp = store.client.search(index=store.index, body=body)
    return int(resp.get("aggregations", {}).get("distinct", {}).get("value", 0))


def _scalar_with_delta(
    current: int, previous: int, since: datetime, until: datetime
) -> ScalarWithDeltaResponse:
    return ScalarWithDeltaResponse(
        value=current, delta=current - previous, since=since, until=until
    )


async def query_user_sessions_total(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> ScalarWithDeltaResponse:
    prev_since = since - (until - since)
    current = _count_user_events(store, _SESSION_CREATED, since, until, user.uid)
    previous = _count_user_events(store, _SESSION_CREATED, prev_since, since, user.uid)
    return _scalar_with_delta(current, previous, since, until)


async def query_user_messages_total(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> ScalarWithDeltaResponse:
    prev_since = since - (until - since)
    current = _count_user_events(store, _TURN_COMPLETED, since, until, user.uid)
    previous = _count_user_events(store, _TURN_COMPLETED, prev_since, since, user.uid)
    return _scalar_with_delta(current, previous, since, until)


async def query_user_agents_used_total(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> ScalarWithDeltaResponse:
    prev_since = since - (until - since)
    current = _distinct_user_agents(store, since, until, user.uid)
    previous = _distinct_user_agents(store, prev_since, since, user.uid)
    return _scalar_with_delta(current, previous, since, until)


USER_SESSIONS_TOTAL_PRESET = PresetDef(
    name="user_sessions_total",
    response_model=ScalarWithDeltaResponse,
    handler=query_user_sessions_total,
    summary="Conversations the requesting user created in the range, and change vs the previous equal window",
    self_scoped=True,
)

USER_MESSAGES_TOTAL_PRESET = PresetDef(
    name="user_messages_total",
    response_model=ScalarWithDeltaResponse,
    handler=query_user_messages_total,
    summary="Messages the requesting user sent in the range, and change vs the previous equal window",
    self_scoped=True,
)

USER_AGENTS_USED_TOTAL_PRESET = PresetDef(
    name="user_agents_used_total",
    response_model=ScalarWithDeltaResponse,
    handler=query_user_agents_used_total,
    summary="Distinct agents the requesting user used in the range, and change vs the previous equal window",
    self_scoped=True,
)
