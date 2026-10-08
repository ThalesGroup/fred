# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Exercise the migrated space constraints, including real PostgreSQL."""

from collections.abc import Iterator
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection

from fred_core.models import Base
from fred_core.sql.alembic_env import autogenerate_diffs
from fred_core.teams.space_models import SpaceRow
from fred_core.users.user_models import UserRow

_PATH = (
    Path(__file__).parents[1] / "alembic/versions/bc21d49e01a7_add_space_identity.py"
)
_SPEC = spec_from_file_location("space_identity_migration", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
migration = module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)

_OWNER = UUID("00000000-0000-0000-0000-000000000001")


def space(
    identifier: str, kind: str, parent: str | None = None, **fields: object
) -> dict[str, object]:
    return {
        "id": identifier,
        "name": identifier,
        "kind": kind,
        "parent_id": parent,
        "parent_kind": {"team": "organization", "project": "team"}.get(kind),
        "parent_team_kind": "collaborative" if kind == "project" else None,
        "team_kind": "collaborative" if kind == "team" else None,
        "personal_owner_id": None,
        **fields,
    }


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
def database(request: pytest.FixtureRequest) -> Iterator[Connection]:
    url = "sqlite://"
    if request.param == "postgresql":
        url = os.environ.get("FRED_SPACE_TEST_POSTGRES_URL", "")
        if not url:
            pytest.skip(
                "Set FRED_SPACE_TEST_POSTGRES_URL for isolated-schema PostgreSQL checks"
            )
    engine = sa.create_engine(url)
    schema = f"space_test_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            if request.param == "postgresql":
                connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(sa.text(f'SET search_path TO "{schema}"'))
            else:
                connection.execute(sa.text("PRAGMA foreign_keys = ON"))
            UserRow.__table__.create(connection)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            connection.execute(sa.insert(UserRow), {"id": _OWNER})
            for row in (
                space("org-a", "organization"),
                space("org-b", "organization"),
                space("team-a", "team", "org-a", name="Research"),
                space("team-b", "team", "org-b", name="Research"),
                space(
                    "private",
                    "team",
                    "org-a",
                    team_kind="personal",
                    personal_owner_id=_OWNER,
                ),
                space("project-a", "project", "team-a", name="Atlas"),
                space("project-b", "project", "team-b", name="Atlas"),
            ):
                connection.execute(sa.insert(SpaceRow), row)
            connection.commit()
            try:
                yield connection
            finally:
                connection.rollback()
                if request.param == "postgresql":
                    connection.execute(sa.text("SET search_path TO public"))
                    connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
                    connection.commit()
    finally:
        engine.dispose()


def test_scoped_names_and_preserved_ids(database: Connection) -> None:
    assert database.execute(
        sa.select(SpaceRow.id).where(SpaceRow.name == "Research")
    ).scalars().all() == ["team-a", "team-b"]
    assert (
        database.execute(
            sa.select(sa.func.count())
            .select_from(SpaceRow)
            .where(SpaceRow.name == "Atlas")
        ).scalar_one()
        == 2
    )


@pytest.mark.parametrize(
    "row",
    [
        space("bad", "workspace"),
        space("bad", "organization", "org-a"),
        space("bad", "team"),
        space("bad", "team", "missing"),
        space("bad", "team", "team-a"),
        space("bad", "team", "org-a", parent_kind=None),
        space("bad", "team", "org-a", team_kind=None),
        space("bad", "team", "org-a", team_kind="personal"),
        space("bad", "team", "org-a", personal_owner_id=_OWNER),
        space("bad", "project", "org-a"),
        space("bad", "project", "private"),
        space("bad", "project", "team-a", parent_team_kind=None),
        space("bad", "project", "project-a"),
        space("bad", "project", "team-a", personal_owner_id=_OWNER),
        space("bad", "organization", name="  "),
        space("bad", "organization", name="org-a"),
        space("bad", "team", "org-a", name="Research"),
        space("bad", "project", "team-a", name="Atlas"),
        space("bad", "team", "org-a", team_kind="personal", personal_owner_id=_OWNER),
        space(
            "bad", "team", "org-a", team_kind="personal", personal_owner_id=UUID(int=2)
        ),
    ],
)
def test_invalid_structure_is_rejected(
    database: Connection, row: dict[str, object]
) -> None:
    with pytest.raises(sa.exc.IntegrityError), database.begin_nested():
        database.execute(sa.insert(SpaceRow), row)


def test_parent_cannot_be_deleted_while_referenced(database: Connection) -> None:
    with pytest.raises(sa.exc.IntegrityError), database.begin_nested():
        database.execute(sa.delete(SpaceRow).where(SpaceRow.id == "team-a"))


def test_migration_matches_orm(database: Connection) -> None:
    assert autogenerate_diffs(database, Base.metadata, frozenset({"space"})) == []


def test_schema_downgrade(database: Connection) -> None:
    with Operations.context(MigrationContext.configure(database)):
        migration.downgrade()
    assert not sa.inspect(database).has_table("space")


def test_user_organization_upgrade_preserves_an_unassigned_identity() -> None:
    path = _PATH.with_name("cd32e50f12b8_add_user_organization.py")
    spec = spec_from_file_location("user_organization_migration", path)
    assert spec is not None and spec.loader is not None
    assignment_migration = module_from_spec(spec)
    spec.loader.exec_module(assignment_migration)
    legacy_users = sa.Table(
        "users",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String()),
    )
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("PRAGMA foreign_keys = ON"))
            legacy_users.create(connection)
            connection.execute(
                sa.insert(legacy_users), {"id": _OWNER, "username": "alice"}
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assignment_migration.upgrade()
            row = connection.execute(
                sa.text(
                    "SELECT username, organization_id, organization_kind FROM users"
                )
            ).one()
            assert row == ("alice", None, "organization")
            connection.execute(sa.insert(SpaceRow), space("org", "organization"))
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.execute(
                    sa.text("UPDATE users SET organization_id = 'missing'")
                )
            connection.execute(sa.text("UPDATE users SET organization_id = 'org'"))
            with Operations.context(MigrationContext.configure(connection)):
                assignment_migration.downgrade()
                migration.downgrade()
            assert {
                column["name"] for column in sa.inspect(connection).get_columns("users")
            } == {"id", "username"}
            assert connection.scalar(sa.select(legacy_users.c.username)) == "alice"
    finally:
        engine.dispose()


def _team_settings_migration():
    path = _PATH.with_name("de43f61a23c9_link_team_settings_to_spaces.py")
    spec = spec_from_file_location("team_settings_migration", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_team_settings(database: Connection, identifier: str = "team-a") -> None:
    table = sa.Table(
        "teammetadata",
        sa.MetaData(),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.String(180)),
        sa.UniqueConstraint("name", name="uq_teammetadata_name"),
    )
    table.create(database)
    database.execute(
        sa.insert(table),
        {
            "id": identifier,
            "name": "Research",
            "description": "Preserved settings",
        },
    )
    database.commit()


def test_team_settings_upgrade_preserves_identity_and_settings(
    database: Connection,
) -> None:
    _legacy_team_settings(database)
    with Operations.context(MigrationContext.configure(database)):
        _team_settings_migration().upgrade()
    assert database.execute(
        sa.text(
            "SELECT t.id, s.name, t.description FROM teammetadata t JOIN space s ON s.id = t.id"
        )
    ).one() == ("team-a", "Research", "Preserved settings")
    assert "name" not in {
        c["name"] for c in sa.inspect(database).get_columns("teammetadata")
    }
    database.execute(sa.text("INSERT INTO teammetadata (id) VALUES ('team-b')"))
    assert (
        database.execute(sa.text("SELECT count(*) FROM teammetadata")).scalar_one() == 2
    )


@pytest.mark.parametrize(
    "identifier,kind",
    [
        ("org-a", "team"),
        ("project-a", "team"),
        ("missing", "team"),
        ("team-b", "organization"),
    ],
)
def test_settings_require_a_team_space(
    database: Connection, identifier: str, kind: str
) -> None:
    _legacy_team_settings(database)
    with Operations.context(MigrationContext.configure(database)):
        _team_settings_migration().upgrade()
    with pytest.raises(sa.exc.IntegrityError), database.begin_nested():
        database.execute(
            sa.text("INSERT INTO teammetadata (id, space_kind) VALUES (:id, :kind)"),
            {"id": identifier, "kind": kind},
        )


def test_team_settings_upgrade_requires_explicit_translation(
    database: Connection,
) -> None:
    _legacy_team_settings(database, "unmapped-team")
    with Operations.context(MigrationContext.configure(database)):
        with pytest.raises(RuntimeError, match="Translate existing team identities"):
            _team_settings_migration().upgrade()
    assert (
        database.execute(sa.text("SELECT name FROM teammetadata")).scalar_one()
        == "Research"
    )
    assert "space_kind" not in {
        c["name"] for c in sa.inspect(database).get_columns("teammetadata")
    }


def test_team_settings_downgrade_restores_names(database: Connection) -> None:
    _legacy_team_settings(database)
    with Operations.context(MigrationContext.configure(database)):
        migration = _team_settings_migration()
        migration.upgrade()
        migration.downgrade()
    assert database.execute(sa.text("SELECT id, name FROM teammetadata")).one() == (
        "team-a",
        "Research",
    )
