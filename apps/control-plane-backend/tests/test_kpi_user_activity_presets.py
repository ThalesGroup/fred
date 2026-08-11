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

"""Guards for the home-dashboard "your activity" presets (#2298).

Same contract as the `user_token_usage_*` presets: these are personal metrics,
so each must be `self_scoped` (the router's authorization chokepoint then skips
OpenFGA — see `test_kpi_scope.py`) and must NOT be `team_scopable` (a
personal-activity preset that accepted a `team_id` would leak past the "my own
data" boundary). Also pins the delta contract: value = count in the window,
delta = count(window) - count(previous equal window), so a fabricated
OpenSearch response yields a predictable scalar+delta the frontend can turn
into its ▲/▼ chip.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.user_activity import (
    USER_AGENTS_USED_TOTAL_PRESET,
    USER_MESSAGES_TOTAL_PRESET,
    USER_SESSIONS_TOTAL_PRESET,
    query_user_agents_used_total,
    query_user_messages_total,
    query_user_sessions_total,
)

_PRESETS = [
    USER_SESSIONS_TOTAL_PRESET,
    USER_MESSAGES_TOTAL_PRESET,
    USER_AGENTS_USED_TOTAL_PRESET,
]


def test_user_activity_presets_are_self_scoped() -> None:
    for preset in _PRESETS:
        assert preset.self_scoped is True, preset.name


def test_user_activity_presets_are_not_team_scopable() -> None:
    for preset in _PRESETS:
        assert preset.team_scopable is False, preset.name


def test_user_activity_preset_names_are_stable() -> None:
    # These names are the public route path (/kpi/presets/<name>) and the
    # generated frontend hook — renaming one silently breaks the home page.
    assert {p.name for p in _PRESETS} == {
        "user_sessions_total",
        "user_messages_total",
        "user_agents_used_total",
    }


class _FakeUser:
    uid = "user-123"


def _user() -> KeycloakUser:
    return cast(KeycloakUser, _FakeUser())


def _no_request() -> Request:
    # The activity handlers accept `request` for router-call symmetry but never
    # touch it, so a placeholder is safe here.
    return cast(Request, None)


class _RecordingClient:
    """Returns a scripted count per call and records every query body, so we can
    assert the window/user filter and the current-vs-previous delta math."""

    def __init__(self, counts: list[int], agg_key: str) -> None:
        self._counts = counts
        self._agg_key = agg_key
        self.bodies: list[dict[str, Any]] = []
        self._i = 0

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(body)
        value = self._counts[self._i]
        self._i += 1
        return {"aggregations": {self._agg_key: {"value": value}}}


class _FakeStore:
    def __init__(self, client: _RecordingClient) -> None:
        self.client = client
        self.index = "kpi-index"


def _store(client: _RecordingClient) -> OpenSearchKPIStore:
    return cast(OpenSearchKPIStore, _FakeStore(client))


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_count_presets_return_value_and_absolute_delta() -> None:
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = since + timedelta(days=7)

    for handler, agg_key in (
        (query_user_sessions_total, "total"),
        (query_user_messages_total, "total"),
    ):
        # First call = current window (12), second = previous window (5).
        client = _RecordingClient(counts=[12, 5], agg_key=agg_key)
        store = _store(client)
        result = _run(
            handler(
                store, user=_user(), since=since, until=until, request=_no_request()
            )
        )
        assert result.value == 12
        assert result.delta == 7  # 12 - 5

        # Previous window is the equal-length span ending at `since`.
        current_body, previous_body = client.bodies
        cur_range = current_body["query"]["bool"]["filter"][0]["range"]["@timestamp"]
        prev_range = previous_body["query"]["bool"]["filter"][0]["range"]["@timestamp"]
        assert cur_range["gte"] == since.isoformat()
        assert prev_range["gte"] == (since - timedelta(days=7)).isoformat()
        assert prev_range["lte"] == since.isoformat()
        # Every query is scoped to the requesting user.
        assert current_body["query"]["bool"]["filter"][2] == {
            "term": {"dims.user_id": "user-123"}
        }


def test_agents_used_preset_uses_distinct_cardinality() -> None:
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = since + timedelta(days=30)
    client = _RecordingClient(counts=[9, 4], agg_key="distinct")
    store = _store(client)
    result = _run(
        query_user_agents_used_total(
            store, user=_user(), since=since, until=until, request=_no_request()
        )
    )
    assert result.value == 9
    assert result.delta == 5  # 9 - 4
    # Distinct agents = cardinality over the agent-name dimension.
    agg = client.bodies[0]["aggs"]
    assert agg == {"distinct": {"cardinality": {"field": "dims.agent_instance_name"}}}
