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

"""Self-scoped "top lists" for the home dashboard leaderboard (#2298).

Two personal rankings over the selected window, each filtered to the requesting
user's own turns (`dims.user_id`) — self_scoped, so the router skips OpenFGA
(same contract as the other `user_*` presets):

  - user_top_agents — the agents the user used most (ranked by turn count, the
    same proxy the platform `top_agents_by_conversations` preset uses). Each row
    carries the agent's display name and origin team, both read from the latest
    matching event via a top_hits sub-agg (deleted-instance safety net — the
    name/team were persisted at emit time), so no agent-store lookup is needed.

  - user_top_teams — the teams the user has been most active in (ranked by turn
    count), returned as team_id → count. The frontend already has the team
    display data (name, avatar, roles) from bootstrap, so it maps team_id back
    itself and filters out the personal space.

Both read `agent.turn_completed`, which carries `dims.agent_instance_id`,
`dims.agent_instance_name`, `dims.team_id` and (via the actor) `dims.user_id` —
so these are pure reads, no emitter change.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)

TOP_AGENTS_N = 5
TOP_TEAMS_N = 50  # small per-user cardinality; the frontend filters + slices to 5


class UserTopAgentRow(BaseModel):
    agent_instance_id: str
    agent_name: str
    # None only for legacy turns emitted before team_id was recorded.
    team_id: str | None = None
    value: int


class UserTopAgentsResponse(BaseModel):
    rows: list[UserTopAgentRow]
    since: AwareDatetime
    until: AwareDatetime


def _user_turn_filters(
    since: datetime, until: datetime, user_id: str
) -> list[dict[str, Any]]:
    return [
        {"range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}},
        {"term": {"metric.name": "agent.turn_completed"}},
        {"term": {"dims.user_id": user_id}},
    ]


async def query_user_top_agents(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> UserTopAgentsResponse:
    filters = _user_turn_filters(since, until, user.uid)
    # Only managed-instance turns carry a meaningful agent identity.
    filters.append({"exists": {"field": "dims.agent_instance_id"}})
    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_agent": {
                "terms": {
                    "field": "dims.agent_instance_id",
                    "size": TOP_AGENTS_N,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    # Latest event → display name + origin team, persisted at emit
                    # time so a since-deleted instance still resolves.
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": {
                                "includes": ["dims.agent_instance_name", "dims.team_id"]
                            },
                        }
                    }
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_agent", {}).get("buckets", [])

    rows: list[UserTopAgentRow] = []
    for bucket in buckets:
        instance_id = str(bucket["key"])
        hits = bucket.get("latest", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        rows.append(
            UserTopAgentRow(
                agent_instance_id=instance_id,
                agent_name=dims.get("agent_instance_name") or instance_id,
                team_id=dims.get("team_id"),
                value=int(bucket["doc_count"]),
            )
        )

    return UserTopAgentsResponse(rows=rows, since=since, until=until)


async def query_user_top_teams(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> LabelValueResponse:
    filters = _user_turn_filters(since, until, user.uid)
    filters.append({"exists": {"field": "dims.team_id"}})
    body: dict[str, Any] = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_team": {
                "terms": {
                    "field": "dims.team_id",
                    "size": TOP_TEAMS_N,
                    "order": {"_count": "desc"},
                }
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_team", {}).get("buckets", [])

    # label = team_id; the frontend maps it to the team's display data and drops
    # the personal space itself.
    rows = [
        LabelValuePoint(label=str(bucket["key"]), value=int(bucket["doc_count"]))
        for bucket in buckets
    ]
    return LabelValueResponse(rows=rows, since=since, until=until)


USER_TOP_AGENTS_PRESET = PresetDef(
    name="user_top_agents",
    response_model=UserTopAgentsResponse,
    handler=query_user_top_agents,
    summary=f"The requesting user's top {TOP_AGENTS_N} agents by turn count, with origin team",
    self_scoped=True,
)

USER_TOP_TEAMS_PRESET = PresetDef(
    name="user_top_teams",
    response_model=LabelValueResponse,
    handler=query_user_top_teams,
    summary="Teams the requesting user has been most active in, by turn count (team_id → count)",
    self_scoped=True,
)
