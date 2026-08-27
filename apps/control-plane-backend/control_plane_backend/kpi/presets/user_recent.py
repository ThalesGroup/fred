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

"""Self-scoped "recently used agents" for the home dashboard (#2298).

`user_recent_agents` is the agents the requesting user interacted with most
recently, ordered by their last turn — not by count (that's `user_top_agents`).
Same source and self-scoping as the other `user_*` presets, so the router skips
OpenFGA; the only difference from `user_top_agents` is the ranking: the terms
agg is ordered by a `max(@timestamp)` sub-agg instead of `_count`, and each row
carries that timestamp as `last_used`.

Reads `agent.turn_completed`, which carries `dims.agent_instance_id`,
`dims.agent_instance_name`, `dims.team_id` and (via the actor) `dims.user_id` —
a pure read, no emitter change.

Returns up to `RECENT_AGENTS_N` rows so the frontend can drop the ones no longer
usable (deleted / disabled / access lost) and still backfill its 5 tiles. The
section is period-independent on the frontend, which passes a wide window.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import AwareDatetime, BaseModel

from control_plane_backend.kpi.presets.base import PresetDef

logger = logging.getLogger(__name__)

# Deliberately wider than the 5 tiles the frontend shows, so it can skip agents
# that are no longer usable and still fill the row from the next-most-recent.
RECENT_AGENTS_N = 10


class UserRecentAgentRow(BaseModel):
    agent_instance_id: str
    agent_name: str
    # None only for legacy turns emitted before team_id was recorded.
    team_id: str | None = None
    last_used: AwareDatetime


class UserRecentAgentsResponse(BaseModel):
    rows: list[UserRecentAgentRow]
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


async def query_user_recent_agents(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> UserRecentAgentsResponse:
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
                    "size": RECENT_AGENTS_N,
                    # Rank by most-recent turn: order the terms agg by the
                    # max-timestamp sub-agg below (a single-value numeric
                    # metric, which terms ordering requires).
                    "order": {"last_used": "desc"},
                },
                "aggs": {
                    "last_used": {"max": {"field": "@timestamp"}},
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
                    },
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_agent", {}).get("buckets", [])

    rows: list[UserRecentAgentRow] = []
    for bucket in buckets:
        instance_id = str(bucket["key"])
        # `max` on a date field returns epoch millis in `value`; skip a bucket
        # with no usable timestamp rather than emit a bogus row.
        millis = bucket.get("last_used", {}).get("value")
        if millis is None:
            continue
        hits = bucket.get("latest", {}).get("hits", {}).get("hits", [])
        dims = hits[0]["_source"].get("dims", {}) if hits else {}
        rows.append(
            UserRecentAgentRow(
                agent_instance_id=instance_id,
                agent_name=dims.get("agent_instance_name") or instance_id,
                team_id=dims.get("team_id"),
                last_used=datetime.fromtimestamp(millis / 1000, tz=timezone.utc),
            )
        )

    return UserRecentAgentsResponse(rows=rows, since=since, until=until)


USER_RECENT_AGENTS_PRESET = PresetDef(
    name="user_recent_agents",
    response_model=UserRecentAgentsResponse,
    handler=query_user_recent_agents,
    summary=f"The requesting user's {RECENT_AGENTS_N} most recently used agents, newest first, with origin team",
    self_scoped=True,
)
