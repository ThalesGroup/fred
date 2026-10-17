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

"""A team's required description: request bounds, the HTTP 422s, the
placeholder flag on the `Team` DTO, the import fallback and the migration."""

from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from control_plane_backend.import_export.exporter import run_export
from control_plane_backend.teams.schemas import CreateTeamRequest, UpdateTeamRequest
from control_plane_backend.teams.service import _build_team_dto, create_team
from fred_core.common import TeamId
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.metadata_store import TEAM_DESCRIPTION_PLACEHOLDER, TeamMetadata
from fred_core.teams.team_metatada_models import TeamMetadataRow
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_import_export_team_metadata import _import, _make_engine, _seed_team
from test_team_registry_governance import (
    _deps,
    _FakeMetadataStore,
    _FakePromptCategoryStoreForSeed,
    _FakePromptStoreForSeed,
    _FakeRebac,
    _stub_team_projection,
    _user,
)

_VALID = "Automate the drafting of our monthly HR reports."


def _create(description: Any) -> CreateTeamRequest:
    payload = {"name": "Ops", "initial_team_admin_ids": ["alice"]}
    if description is not ...:
        payload["description"] = description
    return CreateTeamRequest.model_validate(payload)


# --- request bounds ----------------------------------------------------------


@pytest.mark.parametrize("description", [..., None, "   Short text here   ", "x" * 501])
def test_create_refuses_a_missing_or_out_of_bounds_description(
    description: Any,
) -> None:
    with pytest.raises(ValidationError):
        _create(description)


def test_create_accepts_the_bounds_and_trims() -> None:
    assert _create("x" * 20).description == "x" * 20
    assert _create("x" * 500).description == "x" * 500
    assert (
        _create("  Summarise customer tickets for the support desk.  ").description
        == "Summarise customer tickets for the support desk."
    )


@pytest.mark.parametrize("description", [None, "", "   ", "Too short", "x" * 501])
def test_update_refuses_clearing_or_out_of_bounds(description: str | None) -> None:
    with pytest.raises(ValidationError):
        UpdateTeamRequest.model_validate({"description": description})


def test_update_leaves_an_unset_description_alone() -> None:
    request = UpdateTeamRequest.model_validate({"joining_mode": "open"})
    assert "description" not in request.model_dump(exclude_unset=True)


# --- HTTP --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_patch_answer_422_before_reaching_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    calls: list[str] = []

    async def _record(*_args: Any, **_kwargs: Any) -> None:
        calls.append("service")

    monkeypatch.setattr(
        "control_plane_backend.teams.api.create_team_from_service", _record
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.api.update_team_from_service", _record
    )
    from control_plane_backend.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        created = await client.post(
            "/control-plane/v1/teams",
            json={"name": "Ops", "initial_team_admin_ids": ["alice"]},
        )
        cleared = await client.patch(
            "/control-plane/v1/teams/ops", json={"description": None}
        )
        shortened = await client.patch(
            "/control-plane/v1/teams/ops", json={"description": "Too short"}
        )

    assert [created.status_code, cleared.status_code, shortened.status_code] == [
        422,
        422,
        422,
    ]
    assert calls == []


# --- service -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_team_stores_the_trimmed_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeMetadataStore()
    _stub_team_projection(monkeypatch)

    team = await create_team(
        _user(),
        _create(f"  {_VALID}  "),
        _deps(
            _FakeRebac(),
            store,
            prompt_store=_FakePromptStoreForSeed(),
            prompt_category_store=_FakePromptCategoryStoreForSeed(),
        ),
    )

    assert store.teams[str(team.id)].description == _VALID


@pytest.mark.parametrize(
    ("description", "expected"),
    [(TEAM_DESCRIPTION_PLACEHOLDER, True), (_VALID, False), (None, False)],
)
def test_team_dto_reports_the_placeholder(
    description: str | None, expected: bool
) -> None:
    metadata = TeamMetadata(id=TeamId("t1"), name="Ops", description=description)
    team = _build_team_dto(
        metadata=metadata,
        admin_ids=set(),
        member_ids=set(),
        is_member=False,
        my_relations=set(),
        admin_summaries={},
        content_store=cast(Any, object()),
        default_max_resources_storage_size=None,
    )
    assert team.description_is_placeholder is expected


# --- import ------------------------------------------------------------------


def _with_team_rows(bundle: bytes, rows: list[dict[str, Any]]) -> bytes:
    """Rewrite the bundle's team metadata: the source database's own CHECK
    would refuse these rows, an older export would not."""
    source = zipfile.ZipFile(io.BytesIO(bundle))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "postgres/team_metadata.jsonl":
                template = json.loads(data.decode().splitlines()[0])
                data = "\n".join(
                    json.dumps({**template, **row}) for row in rows
                ).encode()
            target.writestr(item, data)
    return out.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (None, TEAM_DESCRIPTION_PLACEHOLDER),
        ("Ops", TEAM_DESCRIPTION_PLACEHOLDER),
        (
            "  Prepare board meeting briefs and minutes. ",
            "Prepare board meeting briefs and minutes.",
        ),
        ("y" * 600, "y" * 500),
    ],
)
async def test_import_never_fails_on_a_team_description(
    tmp_path: Path, description: str | None, expected: str
) -> None:
    # One team per import: on SQLite, a second row's autoflush holds the write
    # lock the progress update needs.
    source = await _make_engine(tmp_path, "desc-src.sqlite3")
    dest = await _make_engine(tmp_path, "desc-dst.sqlite3")
    try:
        await _seed_team(
            source, TeamMetadataRow(id="t1", name="Ops", description=_VALID)
        )
        bundle = _with_team_rows(
            await run_export(source), [{"id": "t1", "description": description}]
        )

        report = await _import(bundle, dest)

        async with make_session_factory(dest)() as session:
            row = await session.get(TeamMetadataRow, "t1")
        assert row is not None and row.description == expected
        warned = "1 team received a default description." in report.warnings
        assert warned is (expected == TEAM_DESCRIPTION_PLACEHOLDER)
    finally:
        await source.dispose()
        await dest.dispose()


# --- migration ---------------------------------------------------------------


def _load_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/c9acb7dd3ad0_require_team_description.py"
    )
    spec = importlib.util.spec_from_file_location("require_team_description", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _run(engine: sa.Engine, step: str) -> None:
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(_load_migration(), step)()


def test_migration_backfills_then_downgrade_restores_the_old_column() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    teams = sa.Table(
        "teammetadata",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("description", sa.String(180), nullable=True),
    )
    seed = {
        "t-null": None,
        "t-blank": "   ",
        "t-short": "Ops",
        "t-padded": "  Draft and review procurement contracts.  ",
    }
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            teams.insert(), [{"id": i, "description": d} for i, d in seed.items()]
        )

    _run(engine, "upgrade")

    def _read() -> dict[str, str | None]:
        with engine.connect() as connection:
            rows = connection.execute(sa.select(teams.c.id, teams.c.description))
            return {team_id: description for team_id, description in rows}

    assert _read() == {
        "t-null": TEAM_DESCRIPTION_PLACEHOLDER,
        "t-blank": TEAM_DESCRIPTION_PLACEHOLDER,
        "t-short": TEAM_DESCRIPTION_PLACEHOLDER,
        "t-padded": "Draft and review procurement contracts.",
    }
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(teams.update().values(description="Short"))
    with engine.begin() as connection:
        connection.execute(
            teams.update().where(teams.c.id == "t-short").values(description="z" * 300)
        )

    _run(engine, "downgrade")

    after = _read()
    assert after["t-null"] is None
    assert after["t-blank"] is None
    assert after["t-short"] == "z" * 180
    assert after["t-padded"] == "Draft and review procurement contracts."
    with engine.begin() as connection:
        connection.execute(teams.update().values(description=None))
