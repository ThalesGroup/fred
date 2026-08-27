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

"""Guards for the home-dashboard "recently used agents" preset (#2298).

`user_recent_agents` is a personal ranking, so it must be `self_scoped` (router
skips OpenFGA) and never `team_scopable`. The query test pins what the frontend
relies on: rows are ordered by most-recent turn (the terms agg is ordered by a
`max(@timestamp)` sub-agg, not by count), each row resolves name/team from the
latest event's top_hits (falling back to the id) and carries that timestamp as
`last_used`, and the whole thing is filtered to the requesting user.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from control_plane_backend.kpi.presets.user_recent import (
    RECENT_AGENTS_N,
    USER_RECENT_AGENTS_PRESET,
    query_user_recent_agents,
)
from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore


def test_user_recent_preset_is_self_scoped() -> None:
    assert USER_RECENT_AGENTS_PRESET.self_scoped is True


def test_user_recent_preset_is_not_team_scopable() -> None:
    assert USER_RECENT_AGENTS_PRESET.team_scopable is False


def test_user_recent_preset_name_is_stable() -> None:
    assert USER_RECENT_AGENTS_PRESET.name == "user_recent_agents"


class _FakeUser:
    uid = "user-123"


class _CannedClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.bodies: list[dict[str, Any]] = []

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(body)
        return self._response


class _FakeStore:
    def __init__(self, client: _CannedClient) -> None:
        self.client = client
        self.index = "kpi-index"


def _user() -> KeycloakUser:
    return cast(KeycloakUser, _FakeUser())


def _store(client: _CannedClient) -> OpenSearchKPIStore:
    return cast(OpenSearchKPIStore, _FakeStore(client))


def _no_request() -> Request:
    return cast(Request, None)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


_SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)
_UNTIL = _SINCE + timedelta(days=365)


def _agent_bucket(
    key: str, last_used_ms: float, name: str | None, team: str | None
) -> dict[str, Any]:
    dims: dict[str, Any] = {}
    if name is not None:
        dims["agent_instance_name"] = name
    if team is not None:
        dims["team_id"] = team
    return {
        "key": key,
        "doc_count": 1,
        "last_used": {"value": last_used_ms},
        "latest": {"hits": {"hits": [{"_source": {"dims": dims}}]}},
    }


def test_recent_agents_orders_by_last_used_and_resolves_name_team() -> None:
    newer = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
    older = datetime(2026, 8, 2, 9, tzinfo=timezone.utc)
    client = _CannedClient(
        {
            "aggregations": {
                "by_agent": {
                    "buckets": [
                        _agent_bucket(
                            "a1", newer.timestamp() * 1000, "Rédacteur AO", "team-bid"
                        ),
                        # Name/team missing (legacy event) → falls back to the id.
                        _agent_bucket("a2", older.timestamp() * 1000, None, None),
                    ]
                }
            }
        }
    )
    result = _run(
        query_user_recent_agents(
            _store(client),
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=_no_request(),
        )
    )
    assert [
        (r.agent_instance_id, r.agent_name, r.team_id, r.last_used) for r in result.rows
    ] == [
        ("a1", "Rédacteur AO", "team-bid", newer),
        ("a2", "a2", None, older),
    ]
    # Filtered to the requesting user, ordered by the max-timestamp sub-agg,
    # and fetched wider than the frontend's 5 tiles for backfill.
    body = client.bodies[0]
    assert {"term": {"dims.user_id": "user-123"}} in body["query"]["bool"]["filter"]
    assert body["aggs"]["by_agent"]["terms"]["order"] == {"last_used": "desc"}
    assert body["aggs"]["by_agent"]["terms"]["size"] == RECENT_AGENTS_N
    assert body["aggs"]["by_agent"]["aggs"]["last_used"] == {
        "max": {"field": "@timestamp"}
    }


def test_recent_agents_skips_bucket_without_timestamp() -> None:
    client = _CannedClient(
        {
            "aggregations": {
                "by_agent": {
                    "buckets": [
                        {
                            "key": "a1",
                            "doc_count": 1,
                            "last_used": {"value": None},
                            "latest": {"hits": {"hits": []}},
                        }
                    ]
                }
            }
        }
    )
    result = _run(
        query_user_recent_agents(
            _store(client),
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=_no_request(),
        )
    )
    assert result.rows == []
