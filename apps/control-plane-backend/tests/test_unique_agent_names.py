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

"""Agent names are unique within a team, ignoring case and surrounding spaces:
the comparison, the store's typed conflict, the API's 409 code, and the
migration that renames existing duplicates. Names are ASCII here: SQLite's
`lower` folds ASCII only, PostgreSQL folds Unicode."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from control_plane_backend.agent_instances.names import (
    free_imported_name,
    normalize_agent_name,
)
from control_plane_backend.agent_instances.store import (
    AgentInstanceStore,
    AgentNameAlreadyExistsError,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from test_capability_selection_1974 import _fake_pod_validate, _setup
from test_main import _make_record

_USAGE = "Test usage statement covering purpose, users, data, and error impact."


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


# --- comparison -------------------------------------------------------------


def test_names_compare_without_case_or_surrounding_spaces() -> None:
    assert normalize_agent_name("  Assistant RH ") == normalize_agent_name(
        "assistant rh"
    )
    assert normalize_agent_name("Assistant  RH") != normalize_agent_name("Assistant RH")


def test_free_imported_name_skips_taken_suffixes() -> None:
    taken = {"analyst", "analyst_imported-1"}
    assert free_imported_name("Free", taken) == "Free"
    assert free_imported_name("ANALYST", taken) == "ANALYST_imported-2"


# --- store ------------------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agents.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(cast(sa.Table, AgentInstanceRow.__table__).create)
    yield AgentInstanceStore(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_store_refuses_a_taken_name_in_the_same_team(store) -> None:
    await store.create(_make_record(agent_instance_id="a", team_id="team-a"))

    with pytest.raises(AgentNameAlreadyExistsError):
        await store.create(
            _make_record(
                agent_instance_id="b",
                team_id="team-a",
                display_name="ECHO team agent",
            )
        )
    # The same name stays free in another team.
    await store.create(_make_record(agent_instance_id="c", team_id="team-b"))


@pytest.mark.asyncio
async def test_store_refuses_a_rename_to_a_taken_name(store) -> None:
    await store.create(_make_record(agent_instance_id="a", display_name="Analyst"))
    await store.create(_make_record(agent_instance_id="b", display_name="Writer"))

    with pytest.raises(AgentNameAlreadyExistsError):
        await store.update("b", "personal", display_name="analyst")
    renamed = await store.update("a", "personal", display_name="ANALYST")

    assert renamed is not None and renamed.display_name == "ANALYST"
    assert (await store.get("b")).display_name == "Writer"  # type: ignore[union-attr]


# --- API --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_under_a_taken_name_is_a_coded_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_make_record()])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "usage_statement": _USAGE,
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "  echo TEAM agent ",
                "capability_ids": ["demo_echo"],
            },
        )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "agent_name_conflict"
    assert len(store._records) == 1
    assert calls == []  # refused before the pod validated anything


@pytest.mark.asyncio
async def test_create_stores_the_name_without_surrounding_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch)
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "usage_statement": _USAGE,
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "  Analyst  ",
            },
        )

    assert resp.status_code == 201
    assert store._records[0].display_name == "Analyst"


@pytest.mark.asyncio
async def test_rename_to_a_taken_name_is_refused_but_a_case_change_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = _make_record(agent_instance_id="instance-1", display_name="Analyst")
    writer = _make_record(agent_instance_id="instance-2", display_name="Writer")
    app, store = _setup(monkeypatch, records=[analyst, writer])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        taken = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-2",
            json={"display_name": "analyst"},
        )
        own = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"display_name": "ANALYST"},
        )

    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "agent_name_conflict"
    assert writer.display_name == "Writer"
    assert own.status_code == 200
    assert own.json()["display_name"] == "ANALYST"


# --- migration --------------------------------------------------------------


def _load_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/a4d85307ea0e_unique_agent_names_per_team.py"
    )
    spec = importlib.util.spec_from_file_location("unique_agent_names", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_renames_duplicates_by_creation_order_then_indexes() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    agents = sa.Table(
        "agent_instance",
        metadata,
        sa.Column("agent_instance_id", sa.String, primary_key=True),
        sa.Column("team_id", sa.String, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    day = datetime(2026, 10, 1, tzinfo=timezone.utc)
    long_name = "x" * 255
    seed = [
        ("a1", "team-a", "Analyst", day),
        ("a2", "team-a", "analyst ", day + timedelta(days=1)),
        ("a3", "team-a", "Analyst (2)", day + timedelta(days=2)),
        ("a4", "team-a", "ANALYST", day + timedelta(days=3)),
        ("a5", "team-a", f"{long_name}", day + timedelta(days=4)),
        ("a6", "team-a", f"{long_name.upper()}", day + timedelta(days=5)),
        ("b1", "team-b", "Analyst", day + timedelta(days=6)),
        ("b2", "team-b", " Writer ", day + timedelta(days=7)),
    ]
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            agents.insert(),
            [
                dict(agent_instance_id=i, team_id=t, display_name=n, created_at=c)
                for i, t, n, c in seed
            ],
        )

    migration = _load_migration()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(agents.c.agent_instance_id, agents.c.display_name)
        )
        names: dict[str, str] = {agent_id: name for agent_id, name in rows}
    assert names["a1"] == "Analyst"
    assert names["a2"] == "analyst (3)"  # "(2)" is already another agent's name
    assert names["a3"] == "Analyst (2)"
    assert names["a4"] == "ANALYST (4)"
    assert names["a5"] == long_name
    assert names["a6"] == f"{long_name.upper()[:251]} (2)"
    assert len(names["a6"]) == 255
    assert names["b1"] == "Analyst"
    assert names["b2"] == "Writer"

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                agents.insert().values(
                    agent_instance_id="a7",
                    team_id="team-a",
                    display_name="writer",
                    created_at=day,
                ),
            )
            connection.execute(
                agents.insert().values(
                    agent_instance_id="a8",
                    team_id="team-a",
                    display_name="WRITER",
                    created_at=day,
                ),
            )

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
    engine.dispose()
