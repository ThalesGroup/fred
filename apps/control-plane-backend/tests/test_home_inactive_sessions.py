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

"""Unit tests for the home cleanup tool's session helpers (#2298).

`list_inactive_sessions` must: (a) sweep every space the user belongs to,
(b) keep only sessions whose last activity sits in the [now-period, now-cutoff]
window (inactive for >N days but touched within the look-back window), and
(c) resolve the agent display name. `bulk_delete_sessions` must run the governed
single-delete per item and split results into deleted/failed without aborting
the batch on one failure.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from control_plane_backend.product import service
from control_plane_backend.product.schemas import (
    BulkDeleteSessionRef,
    SessionListItem,
)
from control_plane_backend.product.service import ProductServiceDependencies
from fred_core import KeycloakUser
from fred_core.common import TeamId


class _FakeUser:
    uid = "user-1"


def _user() -> KeycloakUser:
    return cast(KeycloakUser, _FakeUser())


def _deps(
    agent_records: dict[str, list[Any]] | None = None,
) -> ProductServiceDependencies:
    records = agent_records or {}

    class _AgentStore:
        async def list_by_team(self, team_id: str) -> list[Any]:
            return records.get(team_id, [])

    fake = SimpleNamespace(
        team_dependencies=object(),
        get_agent_instance_store=lambda: _AgentStore(),
    )
    return cast(ProductServiceDependencies, fake)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _session(
    session_id: str, team_id: str, agent_id: str | None, days_ago: float
) -> SessionListItem:
    return SessionListItem(
        session_id=session_id,
        team_id=TeamId(team_id),
        agent_instance_id=agent_id,
        title=f"Conv {session_id}",
        updated_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def test_list_inactive_filters_by_cutoff_and_resolves_agent(monkeypatch) -> None:
    teams = [SimpleNamespace(id="personal-user-1"), SimpleNamespace(id="team-a")]

    sessions_by_team = {
        "personal-user-1": [
            _session("recent", "personal-user-1", "ag1", days_ago=1),  # too fresh (<5d)
            _session("stale", "personal-user-1", "ag1", days_ago=10),  # inactive
            # No period floor — even a very old conversation must surface.
            _session("ancient", "personal-user-1", "ag1", days_ago=400),  # inactive
        ],
        "team-a": [
            _session("team-stale", "team-a", "ag2", days_ago=8),  # inactive
            _session("no-agent", "team-a", None, days_ago=9),  # inactive, no agent
        ],
    }

    async def fake_list_teams(user: Any, team_deps: Any) -> list[Any]:
        return teams

    async def fake_list_sessions(
        team_id: str, deps: Any, user_id: str | None = None, limit: int = 50
    ) -> Any:
        return sessions_by_team[team_id]

    monkeypatch.setattr(service, "list_teams_from_service", fake_list_teams)
    monkeypatch.setattr(service, "list_sessions", fake_list_sessions)

    agents = {
        "personal-user-1": [
            SimpleNamespace(agent_instance_id="ag1", display_name="Rédacteur AO")
        ],
        "team-a": [SimpleNamespace(agent_instance_id="ag2", display_name="Analyste")],
    }

    result = _run(
        service.list_inactive_sessions(_user(), _deps(agents), inactive_days=5)
    )

    by_id = {s.session_id: s for s in result.sessions}
    # Everything older than the 5-day cutoff survives — only "recent" is dropped,
    # and "ancient" is kept despite being 400 days old (no period bound).
    assert set(by_id) == {"stale", "team-stale", "no-agent", "ancient"}
    assert by_id["stale"].agent_name == "Rédacteur AO"
    assert by_id["team-stale"].agent_name == "Analyste"
    assert by_id["no-agent"].agent_name is None
    # Newest-first ordering (8d, 9d, 10d, 400d).
    assert [s.session_id for s in result.sessions] == [
        "team-stale",
        "no-agent",
        "stale",
        "ancient",
    ]


def test_bulk_delete_splits_deleted_and_failed(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_delete(*, team_id, session_id, user_id, authorization, deps) -> None:
        calls.append(session_id)
        if session_id == "boom":
            raise RuntimeError("not owned")

    monkeypatch.setattr(service, "delete_or_defer_session", fake_delete)

    refs = [
        BulkDeleteSessionRef(session_id="ok1", team_id=TeamId("personal-user-1")),
        BulkDeleteSessionRef(session_id="boom", team_id=TeamId("team-a")),
        BulkDeleteSessionRef(session_id="ok2", team_id=TeamId("team-a")),
    ]

    result = _run(
        service.bulk_delete_sessions(
            _user(), refs, authorization="Bearer x", deps=_deps()
        )
    )

    assert set(result.deleted) == {"ok1", "ok2"}
    assert result.failed == ["boom"]
    assert set(calls) == {"ok1", "boom", "ok2"}
