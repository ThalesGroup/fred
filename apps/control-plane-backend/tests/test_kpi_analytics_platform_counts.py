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

"""Analytics counts read outside KPI events: people with access, published agents."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.kpi.presets import analytics_platform_counts as counts
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.agent_marketplace_models import (
    AgentMarketplaceEntryRow,
)
from control_plane_backend.teams import service as team_service
from fastapi import HTTPException
from fred_core.common import PostgresStoreConfig, TeamId
from fred_core.sql import create_async_engine_from_config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
REQUEST = cast(Any, None)


# --- people with access ------------------------------------------------------


class _Access:
    def __init__(
        self,
        *,
        filtering: bool,
        revision: int = 1,
        allowed: int = 7,
        whitelist: tuple[str, ...] = (),
    ):
        self.filtering, self.revision, self.allowed = filtering, revision, allowed
        self.whitelist = whitelist

    async def state(self) -> Any:
        return SimpleNamespace(filtering_enabled=self.filtering, revision=self.revision)


@pytest.fixture
def platform(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    env: dict[str, Any] = {"access": _Access(filtering=False), "previews": 0}
    counts._admitted.clear()

    def _get_access() -> Any:
        if isinstance(env["access"], HTTPException):
            raise env["access"]
        return env["access"]

    async def _preview(access: Any) -> Any:
        env["previews"] += 1
        users = [
            SimpleNamespace(user_id=f"u{i}", outcome="allowed")
            for i in range(access.allowed)
        ] + [SimpleNamespace(user_id="blocked", outcome="blocked")]
        return SimpleNamespace(
            users=users, allowed=access.allowed, revision=access.revision
        )

    async def _whitelist(access: Any) -> set[str]:
        return set(access.whitelist)

    class _Users:
        async def count_identities(self) -> int:
            return 42

    monkeypatch.setattr(counts, "get_platform_access", _get_access)
    monkeypatch.setattr(counts, "activation_preview", _preview)
    monkeypatch.setattr(counts, "_whitelisted_ids", _whitelist)
    monkeypatch.setattr(counts, "get_user_store", lambda: _Users())
    return env


@pytest.mark.asyncio
async def test_filtering_off_counts_every_known_user(platform: dict[str, Any]) -> None:
    assert await counts.people_with_access(REQUEST, ()) == 42
    assert platform["previews"] == 0


@pytest.mark.asyncio
async def test_platform_access_not_installed_counts_every_known_user(
    platform: dict[str, Any],
) -> None:
    platform["access"] = HTTPException(404, "platform_access_disabled")
    assert await counts.people_with_access(REQUEST, ()) == 42


@pytest.mark.asyncio
async def test_platform_access_unavailable_is_unknown(platform: dict[str, Any]) -> None:
    platform["access"] = HTTPException(503, "platform_access_unavailable")
    assert await counts.people_with_access(REQUEST, ()) is None


@pytest.mark.asyncio
async def test_filtering_on_counts_admitted_users_cached_per_revision(
    platform: dict[str, Any],
) -> None:
    platform["access"] = _Access(filtering=True, revision=3, allowed=7)
    assert await counts.people_with_access(REQUEST, ()) == 7
    assert await counts.people_with_access(REQUEST, ()) == 7
    assert platform["previews"] == 1

    # A new policy revision is evaluated again, without waiting for the TTL.
    platform["access"] = _Access(filtering=True, revision=4, allowed=5)
    assert await counts.people_with_access(REQUEST, ()) == 5
    assert platform["previews"] == 2


@pytest.mark.asyncio
async def test_filtering_on_adds_whitelisted_users_once(
    platform: dict[str, Any],
) -> None:
    # u0..u2 match the rule; u1 is also whitelisted; "blocked" is only whitelisted.
    platform["access"] = _Access(filtering=True, allowed=3, whitelist=("u1", "blocked"))
    assert await counts.people_with_access(REQUEST, ()) == 4


@pytest.mark.asyncio
async def test_admitted_count_expires(
    platform: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    platform["access"] = _Access(filtering=True)
    now = [1000.0]
    monkeypatch.setattr(counts.time, "monotonic", lambda: now[0])
    await counts.people_with_access(REQUEST, ())
    now[0] += counts.ADMITTED_TTL_SECONDS + 1
    await counts.people_with_access(REQUEST, ())
    assert platform["previews"] == 2


@pytest.mark.asyncio
async def test_failed_preview_is_unknown_and_retried_after_a_short_delay(
    platform: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    platform["access"] = _Access(filtering=True)
    attempts = [0]
    now = [1000.0]
    monkeypatch.setattr(counts.time, "monotonic", lambda: now[0])

    async def _conflict(access: Any) -> Any:
        attempts[0] += 1
        raise HTTPException(409, "platform_access_policy_conflict")

    monkeypatch.setattr(counts, "activation_preview", _conflict)
    assert await counts.people_with_access(REQUEST, ()) is None
    # Repeated loads answer "unknown" at once instead of waiting on ReBAC again.
    assert await counts.people_with_access(REQUEST, ()) is None
    assert attempts[0] == 1
    now[0] += counts.ADMITTED_FAILURE_TTL_SECONDS + 1
    assert await counts.people_with_access(REQUEST, ()) is None
    assert attempts[0] == 2


@pytest.mark.asyncio
async def test_unexpected_preview_error_is_unknown_not_a_failed_page(
    platform: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    platform["access"] = _Access(filtering=True)

    async def _broken(access: Any) -> Any:
        raise RuntimeError("database gone")

    monkeypatch.setattr(counts, "activation_preview", _broken)
    assert await counts.people_with_access(REQUEST, ()) is None


@pytest.mark.asyncio
async def test_team_scope_counts_distinct_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = object()
    monkeypatch.setattr(
        counts,
        "get_application_container",
        lambda _r: SimpleNamespace(get_rebac_engine=lambda: rebac),
    )
    calls: list[list[TeamId]] = []

    async def _bulk(engine: Any, team_ids: list[TeamId], user_id: str):
        assert engine is rebac
        calls.append(team_ids)
        members = {TeamId("a"): {"u1", "u2"}, TeamId("b"): {"u2", "u3"}}
        return {}, {t: members.get(t, set()) for t in team_ids}, {}, {}

    monkeypatch.setattr(team_service, "_bulk_team_membership", _bulk)
    # A member of both teams counts once.
    assert await counts.people_with_access(REQUEST, (TeamId("a"), TeamId("b"))) == 3
    assert await counts.people_with_access(REQUEST, (TeamId("c"),)) == 0
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_user_filter_keeps_matching_people_only(
    platform: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Filtering off: the matches are known users already.
    assert await counts.people_with_access(REQUEST, (), ("x", "y")) == 2
    platform["access"] = HTTPException(404, "platform_access_disabled")
    assert await counts.people_with_access(REQUEST, (), ("x",)) == 1
    # Filtering on: admitted (u0..u2) plus whitelisted, intersected with the matches.
    platform["access"] = _Access(filtering=True, allowed=3, whitelist=("w",))
    assert await counts.people_with_access(REQUEST, (), ("u1", "w", "out")) == 2
    assert await counts.people_with_access(REQUEST, (), ()) == 0

    async def _bulk(engine: Any, team_ids: list[TeamId], user_id: str):
        members = {TeamId("a"): {"u1", "u2"}, TeamId("b"): {"u2", "u3"}}
        return {}, {t: members.get(t, set()) for t in team_ids}, {}, {}

    monkeypatch.setattr(
        counts,
        "get_application_container",
        lambda _r: SimpleNamespace(get_rebac_engine=lambda: object()),
    )
    monkeypatch.setattr(team_service, "_bulk_team_membership", _bulk)
    teams = (TeamId("a"), TeamId("b"))
    assert await counts.people_with_access(REQUEST, teams, ("u2", "u9")) == 1


# --- agents created and published --------------------------------------------


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    from control_plane_backend.models.base import Base as CPBase
    from fred_core.models.base import Base as FredCoreBase

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "counts.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(FredCoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    yield engine
    await engine.dispose()


def _agent(
    agent_id: str, team: str, created: datetime, creator: str | None = None
) -> AgentInstanceRow:
    return AgentInstanceRow(
        agent_instance_id=agent_id,
        team_id=team,
        created_by=creator,
        template_id="tpl",
        source_runtime_id="rt",
        source_agent_id="src",
        display_name=agent_id,
        created_at=created,
        updated_at=created,
    )


def _entry(agent_id: str, team: str, state: str = "published") -> Any:
    return AgentMarketplaceEntryRow(
        entry_id=f"e-{agent_id}",
        agent_instance_id=agent_id,
        team_id=team,
        state=state,
        template_id="tpl",
        source_runtime_id="rt",
        source_agent_id="src",
        display_name=agent_id,
        tuning_json="{}",
        capabilities_json="[]",
        version=1,
        snapshot_source_updated_at=T0,
    )


@pytest.mark.asyncio
async def test_published_agents_by_creation_window(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine)() as session, session.begin():
        session.add_all(
            [
                _agent("current-published", "a", T0 + timedelta(days=2)),
                _agent("current-removed", "b", T0 + timedelta(days=3)),
                _agent("current-private", "a", T0 + timedelta(days=4)),
                _agent("previous-published", "a", T0 - timedelta(days=2)),
                _agent("older-published", "a", T0 - timedelta(days=40)),
                _agent("other-team", "c", T0 + timedelta(days=1)),
            ]
        )
        await session.flush()
        session.add_all(
            [
                _entry("current-published", "a"),
                # A removed entry still proves the agent was published.
                _entry("current-removed", "b", state="removed"),
                _entry("previous-published", "a"),
                _entry("older-published", "a"),
                _entry("other-team", "c"),
            ]
        )
    store = AgentInstanceStore(engine)
    windows = [(T0, T0 + timedelta(days=7)), (T0 - timedelta(days=7), T0)]

    statements: list[str] = []
    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda *args: statements.append(args[2]),
    )
    assert await store.count_published_created(windows) == [3, 1]
    assert await store.count_published_created(windows, ["a", "b"]) == [2, 1]
    many = ["a", "b", *(f"t{i}" for i in range(50))]
    assert await store.count_published_created(windows, many) == [2, 1]
    # One statement per call, whatever the number of teams.
    assert len(statements) == 3
    assert await store.count_published_created(windows, ["empty"]) == [0, 0]
    assert await store.count_published_created([]) == []


@pytest.mark.asyncio
async def test_published_agents_of_filtered_creators(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine)() as session, session.begin():
        session.add_all(
            [
                _agent("mine-now", "a", T0 + timedelta(days=2), "u1"),
                _agent("mine-before", "b", T0 - timedelta(days=2), "u1"),
                _agent("mine-private", "a", T0 + timedelta(days=3), "u1"),
                _agent("theirs-now", "a", T0 + timedelta(days=1), "u2"),
                _agent("unknown-creator", "a", T0 + timedelta(days=1)),
            ]
        )
        await session.flush()
        session.add_all(
            [
                _entry("mine-now", "a"),
                _entry("mine-before", "b"),
                _entry("theirs-now", "a"),
                _entry("unknown-creator", "a"),
            ]
        )
    store = AgentInstanceStore(engine)
    windows = [(T0, T0 + timedelta(days=7)), (T0 - timedelta(days=7), T0)]
    assert await store.count_published_created(windows, created_by=["u1"]) == [1, 1]
    assert await store.count_published_created(
        windows, ["a"], created_by=["u1", "u2"]
    ) == [2, 0]
    assert await store.count_published_created(windows, created_by=[]) == [0, 0]
    # Agents created on an excluded day are left out, with or without creators.
    excluded = [(T0 + timedelta(days=2), T0 + timedelta(days=3))]
    assert await store.count_published_created(windows, excluded=excluded) == [2, 1]
    assert await store.count_published_created(
        windows, created_by=["u1"], excluded=excluded
    ) == [0, 1]


@pytest.mark.asyncio
async def test_whitelisted_ids_reads_the_individual_exceptions(
    engine: AsyncEngine,
) -> None:
    from contextlib import asynccontextmanager
    from uuid import uuid4

    from fred_core.security.platform_access.models import PlatformAccessUserRow
    from fred_core.users.user_models import UserRow

    listed, other = uuid4(), uuid4()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add_all(
            [UserRow(id=listed, username="a"), UserRow(id=other, username="b")]
        )
        await session.flush()
        session.add(
            PlatformAccessUserRow(
                user_id=listed, source="manual", granted_by="admin", granted_at=T0
            )
        )

    @asynccontextmanager
    async def _read() -> AsyncIterator[Any]:
        async with sessions() as session:
            yield session

    access = cast(Any, SimpleNamespace(store=SimpleNamespace(read=_read)))
    assert await counts._whitelisted_ids(access) == {str(listed)}
