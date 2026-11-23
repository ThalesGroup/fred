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

"""Offline tests for the KPI backfill command (fake OpenSearch, SQLite sessions)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import pytest
from control_plane_backend.kpi import backfill
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from fred_core import RebacEngine
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from sqlalchemy.ext.asyncio import AsyncEngine


class _FakeClient:
    """In-memory KPI docs; `update_by_query` mirrors TEAM_SCRIPT in Python (painless itself
    is not executed offline)."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.update_bodies: list[dict[str, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self._tasks: dict[str, dict[str, Any]] = {}
        self.tasks = self
        self.indices = self
        self.refreshed = 0

    def _missing(self, user_id: str | None = None) -> list[dict[str, Any]]:
        return [
            d
            for d in self.docs
            if d["metric"] == backfill.API_METRIC
            and d["dims"].get("actor_type") == "human"
            and "team_id" not in d["dims"]
            and (user_id is None or d["dims"]["user_id"] == user_id)
        ]

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.searches.append(body)
        counts: dict[str, int] = {}
        for doc in self._missing():
            counts[doc["dims"]["user_id"]] = counts.get(doc["dims"]["user_id"], 0) + 1
        buckets = [
            {"key": {"user": u}, "doc_count": n} for u, n in sorted(counts.items())
        ]
        return {"aggregations": {"users": {"buckets": buckets}}}

    def count(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "count": sum(1 for d in self.docs if d["metric"] == backfill.TURN_METRIC)
        }

    def update_by_query(
        self, *, index: str, body: dict[str, Any], params: dict[str, str]
    ) -> dict[str, Any]:
        self.update_bodies.append(body)
        updated = 0
        if "script" not in body:
            updated = sum(1 for d in self.docs if d["metric"] == backfill.TURN_METRIC)
        else:
            user_id = body["query"]["bool"]["filter"][-1]["term"]["dims.user_id"]
            script_params = body["script"]["params"]
            for doc in self._missing(user_id):
                team = script_params["days"].get(doc["@timestamp"][:10])
                if team is None:
                    team = script_params["fallback"]
                if team is not None:
                    doc["dims"]["team_id"] = team
                    updated += 1
        task_id = f"task-{len(self._tasks)}"
        self._tasks[task_id] = {"completed": True, "response": {"updated": updated}}
        return {"task": task_id}

    def get(self, *, task_id: str) -> dict[str, Any]:
        return self._tasks[task_id]

    def refresh(self, *, index: str) -> None:
        self.refreshed += 1


class _FakeStore:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.index = "kpi-index"
        self.client = _FakeClient(docs)


class _FakeRebac:
    def __init__(self, teams: dict[str, list[str]]) -> None:
        self._teams = teams

    async def lookup_resources(self, subject: Any, permission: Any, resource_type: Any):
        from fred_core import RebacReference, Resource

        return [
            RebacReference(Resource.TEAM, t) for t in self._teams.get(subject.id, [])
        ]


def _api_doc(user_id: str, ts: str, team: str | None = None) -> dict[str, Any]:
    dims = {"actor_type": "human", "user_id": user_id}
    if team:
        dims["team_id"] = team
    return {"metric": backfill.API_METRIC, "@timestamp": ts, "dims": dims}


async def _add_sessions(
    engine: AsyncEngine, rows: list[tuple[str, str, str, str]]
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(engine)() as session:
        for i, (user_id, team_id, created, updated) in enumerate(rows):
            session.add(
                SessionMetadataRow(
                    session_id=f"s{i}",
                    user_id=user_id,
                    team_id=team_id,
                    created_at=datetime.fromisoformat(created),
                    updated_at=datetime.fromisoformat(updated),
                )
            )
        await session.commit()


async def _attribute(
    store: _FakeStore, engine: AsyncEngine, rebac: _FakeRebac, *, dry_run: bool = False
):
    return await backfill.attribute_teams(
        cast(OpenSearchKPIStore, store),
        engine,
        cast(RebacEngine, rebac),
        None,
        dry_run=dry_run,
        poll_seconds=0,
    )


def test_best_team_prefers_most_sessions_then_smallest_id() -> None:
    sessions = backfill.UserSessions()
    sessions.per_day["2026-10-01"].update({"team-b": 2, "team-a": 1})
    sessions.per_day["2026-10-02"].update({"team-b": 1, "team-a": 1})
    assert backfill.day_to_team(sessions) == {
        "2026-10-01": "team-b",
        "2026-10-02": "team-a",
    }


def test_fallback_team_from_membership() -> None:
    sessions = backfill.UserSessions()
    sessions.overall.update({"team-c": 3, "team-b": 1})
    assert backfill.fallback_team(sessions, {"personal-u1", "team-x"}) == "team-x"
    assert backfill.fallback_team(sessions, {"team-b", "team-c"}) == "team-c"
    assert backfill.fallback_team(sessions, {"team-z", "team-y"}) == "team-y"
    assert backfill.fallback_team(sessions, {"personal-u1"}) is None


def test_team_script_never_overwrites_an_existing_team() -> None:
    assert "if (ctx._source.dims.team_id == null)" in backfill.TEAM_SCRIPT
    assert "ctx.op = 'noop'" in backfill.TEAM_SCRIPT


@pytest.mark.asyncio
async def test_day_map_ignores_personal_teams_and_falls_back_to_membership(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    await _add_sessions(
        control_plane_sql_engine,
        [
            ("u1", "team-a", "2026-10-01T09:00:00", "2026-10-01T10:00:00"),
            ("u1", "personal-u1", "2026-10-02T09:00:00", "2026-10-02T09:30:00"),
        ],
    )
    docs = [
        _api_doc("u1", "2026-10-01T09:05:00+00:00"),
        _api_doc("u1", "2026-10-02T09:05:00+00:00"),
        _api_doc("u1", "2026-10-03T09:05:00+00:00", team="team-kept"),
        _api_doc("u2", "2026-10-01T09:05:00+00:00"),
    ]
    store = _FakeStore(docs)
    rebac = _FakeRebac({"u1": ["team-m", "personal-u1"]})

    totals = await _attribute(store, control_plane_sql_engine, rebac)

    assert [d["dims"].get("team_id") for d in docs] == [
        "team-a",  # session that day
        "team-m",  # personal session ignored -> membership fallback
        "team-kept",  # already attributed
        None,  # no session, no membership: untouched
    ]
    assert totals == {"users": 2, "users_without_team": 1, "events": 2}
    assert store.client.refreshed == 1


@pytest.mark.asyncio
async def test_dry_run_sends_no_update(control_plane_sql_engine: AsyncEngine) -> None:
    docs = [_api_doc("u1", "2026-10-01T09:05:00+00:00")]
    store = _FakeStore(docs)

    totals = await _attribute(
        store, control_plane_sql_engine, _FakeRebac({"u1": ["team-m"]}), dry_run=True
    )

    assert totals["events"] == 1
    assert store.client.update_bodies == []
    assert "team_id" not in docs[0]["dims"]


@pytest.mark.asyncio
async def test_second_run_updates_nothing(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    docs = [
        _api_doc("u1", "2026-10-01T09:05:00+00:00"),
        _api_doc("u2", "2026-10-01T09:05:00+00:00"),
    ]
    store = _FakeStore(docs)
    rebac = _FakeRebac({"u1": ["team-m"]})

    first = await _attribute(store, control_plane_sql_engine, rebac)
    store.client.update_bodies.clear()
    second = await _attribute(store, control_plane_sql_engine, rebac)

    assert first["events"] == 1
    assert second["events"] == 0
    assert store.client.update_bodies == []  # u2 has no team: skipped, not rewritten


def test_reindex_turns_dry_run_counts_and_real_run_updates() -> None:
    docs = [{"metric": backfill.TURN_METRIC, "@timestamp": "2026-10-01", "dims": {}}]
    store = _FakeStore(docs)
    typed = cast(OpenSearchKPIStore, store)

    assert backfill.reindex_turns(typed, None, dry_run=True) == 1
    assert store.client.update_bodies == []
    assert backfill.reindex_turns(typed, None, dry_run=False, poll_seconds=0) == 1
    assert "script" not in store.client.update_bodies[0]


def test_failed_update_task_is_an_error_not_a_success() -> None:
    store = _FakeStore([])
    store.client.update_by_query = lambda **_: {"task": "t"}  # type: ignore[method-assign]
    store.client._tasks["t"] = {
        "completed": True,
        "response": {"updated": 3, "failures": [{"cause": "script"}]},
    }
    with pytest.raises(RuntimeError, match="failed"):
        backfill.run_update_by_query(
            cast(OpenSearchKPIStore, store), {"query": {}}, poll_seconds=0
        )
