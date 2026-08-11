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

"""Guards for the home-dashboard leaderboard presets (#2298).

`user_top_agents` / `user_top_teams` are personal rankings, so both must be
`self_scoped` (router skips OpenFGA) and never `team_scopable`. The query tests
pin the two things the frontend relies on: top_agents resolves the display name
and origin team from the latest event's top_hits (falling back to the id), and
both rank by turn count filtered to the requesting user.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.user_top import (
    USER_TOP_AGENTS_PRESET,
    USER_TOP_TEAMS_PRESET,
    query_user_top_agents,
    query_user_top_teams,
)

_PRESETS = [USER_TOP_AGENTS_PRESET, USER_TOP_TEAMS_PRESET]


def test_user_top_presets_are_self_scoped() -> None:
    for preset in _PRESETS:
        assert preset.self_scoped is True, preset.name


def test_user_top_presets_are_not_team_scopable() -> None:
    for preset in _PRESETS:
        assert preset.team_scopable is False, preset.name


def test_user_top_preset_names_are_stable() -> None:
    assert {p.name for p in _PRESETS} == {"user_top_agents", "user_top_teams"}


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
_UNTIL = _SINCE + timedelta(days=7)


def _agent_bucket(
    key: str, count: int, name: str | None, team: str | None
) -> dict[str, Any]:
    dims: dict[str, Any] = {}
    if name is not None:
        dims["agent_instance_name"] = name
    if team is not None:
        dims["team_id"] = team
    return {
        "key": key,
        "doc_count": count,
        "latest": {"hits": {"hits": [{"_source": {"dims": dims}}]}},
    }


def test_top_agents_resolves_name_and_team_from_latest_event() -> None:
    client = _CannedClient(
        {
            "aggregations": {
                "by_agent": {
                    "buckets": [
                        _agent_bucket("a1", 12, "Rédacteur AO", "team-bid"),
                        # Name/team missing (legacy event) → falls back to the id.
                        _agent_bucket("a2", 4, None, None),
                    ]
                }
            }
        }
    )
    result = _run(
        query_user_top_agents(
            _store(client),
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=_no_request(),
        )
    )
    assert [
        (r.agent_instance_id, r.agent_name, r.team_id, r.value) for r in result.rows
    ] == [
        ("a1", "Rédacteur AO", "team-bid", 12),
        ("a2", "a2", None, 4),
    ]
    # Ranked by turn count, filtered to the requesting user.
    body = client.bodies[0]
    assert {"term": {"dims.user_id": "user-123"}} in body["query"]["bool"]["filter"]
    assert body["aggs"]["by_agent"]["terms"]["order"] == {"_count": "desc"}


def test_top_teams_returns_team_id_to_count() -> None:
    client = _CannedClient(
        {
            "aggregations": {
                "by_team": {
                    "buckets": [
                        {"key": "team-bid", "doc_count": 30},
                        {"key": "team-mkt", "doc_count": 11},
                    ]
                }
            }
        }
    )
    result = _run(
        query_user_top_teams(
            _store(client),
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=_no_request(),
        )
    )
    assert [(r.label, r.value) for r in result.rows] == [
        ("team-bid", 30),
        ("team-mkt", 11),
    ]
    body = client.bodies[0]
    assert {"term": {"dims.user_id": "user-123"}} in body["query"]["bool"]["filter"]
