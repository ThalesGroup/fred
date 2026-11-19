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

"""Offline unit tests: `build_ownership_filters` / `autogenerate_diffs` (#2314).

The scenario throughout mirrors the real shared-`CoreBase` layout: one
metadata carries this backend's own table AND a table another backend's
Alembic tree migrates. The filters must keep autogenerate on the owned side
in both directions — never CREATE a foreign table that is missing from the
database (the metadata-side leak `include_name` alone cannot stop), and
never DROP or report drift for a foreign table that is present.
"""

from __future__ import annotations

import sqlalchemy as sa
from fred_core.sql.alembic_env import autogenerate_diffs


def _shared_metadata() -> sa.MetaData:
    """One metadata with an owned table and a foreign one, like CoreBase."""
    metadata = sa.MetaData()
    sa.Table("mine", metadata, sa.Column("id", sa.String, primary_key=True))
    sa.Table("theirs", metadata, sa.Column("id", sa.String, primary_key=True))
    return metadata


def _table_names(diffs) -> set[tuple[str, str]]:
    """Flatten autogenerate diffs to {(op_name, table_name)} for assertions."""
    ops: set[tuple[str, str]] = set()
    for diff in diffs:
        entry = diff[0] if isinstance(diff, list) else diff
        op_name = entry[0]
        target = entry[-1] if op_name.endswith("_table") else entry[-2]
        name = target.name if hasattr(target, "name") else str(target)
        ops.add((op_name, name))
    return ops


def test_foreign_table_missing_from_db_is_never_proposed_as_create() -> None:
    """The #2314 leak: `theirs` is on the shared metadata but absent from the
    database — without the metadata-side filter it comes out as add_table."""
    engine = sa.create_engine("sqlite://")
    metadata = _shared_metadata()
    with engine.connect() as connection:
        ops = _table_names(autogenerate_diffs(connection, metadata, {"mine"}))

    assert ("add_table", "mine") in ops
    assert all(name != "theirs" for _, name in ops)


def test_foreign_table_present_in_db_is_never_dropped_or_reported() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = _shared_metadata()
    with engine.connect() as connection:
        # The database holds both tables; this tree owns only `mine`.
        metadata.create_all(connection)
        # A column drift on the foreign table must be invisible too.
        connection.execute(sa.text("ALTER TABLE theirs ADD COLUMN extra TEXT"))
        diffs = autogenerate_diffs(connection, metadata, {"mine"})

    assert diffs == []


def test_owned_and_matching_database_yields_empty_migration() -> None:
    """The acceptance shape from #2314: a fully migrated database produces an
    empty autogenerate run, foreign tables notwithstanding."""
    engine = sa.create_engine("sqlite://")
    metadata = _shared_metadata()
    with engine.connect() as connection:
        metadata.tables["mine"].create(connection)
        diffs = autogenerate_diffs(connection, metadata, {"mine"})

    assert diffs == []


def _migration_fixture(tmp_path, *, create_schema: bool):
    from alembic.config import Config

    versions = tmp_path / "versions"
    versions.mkdir()
    (tmp_path / "env.py").write_text(
        "from alembic import context\n"
        "from sqlalchemy import MetaData\n"
        "from fred_core.common import PostgresStoreConfig\n"
        "from fred_core.sql import make_alembic_env\n"
        "offline, online = make_alembic_env(\n"
        "    MetaData(), lambda: PostgresStoreConfig(),\n"
        f"    create_schema={create_schema!r})\n"
        "offline() if context.is_offline_mode() else online()\n"
    )
    (versions / "initial.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = 'initial'\n"
        "down_revision = None\n"
        "def upgrade():\n"
        "    op.create_table('owned', sa.Column('id', sa.Integer, primary_key=True))\n"
    )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    return config


def test_schema_initialization_offline_is_opt_in_and_quotes_identifiers(
    tmp_path, monkeypatch
):
    import io

    from alembic import command

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused")
    monkeypatch.setenv("DATABASE_SCHEMA", "select")
    for enabled in (False, True):
        directory = tmp_path / str(enabled)
        directory.mkdir()
        config = _migration_fixture(directory, create_schema=enabled)
        config.output_buffer = io.StringIO()
        command.upgrade(config, "head", sql=True)
        sql = config.output_buffer.getvalue()
        assert ('CREATE SCHEMA IF NOT EXISTS "select"' in sql) is enabled
        assert 'SET search_path TO "select"' in sql
        if enabled:
            assert sql.index("BEGIN;") < sql.index("CREATE SCHEMA")
            assert sql.index("CREATE SCHEMA") < sql.index(
                'CREATE TABLE "select".alembic_version'
            )
            assert sql.index("CREATE TABLE owned") < sql.index("COMMIT;")


def test_schema_initialization_keeps_sqlite_and_reruns_unchanged(tmp_path, monkeypatch):
    from alembic import command

    db = tmp_path / "database.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.delenv("DATABASE_SCHEMA", raising=False)
    config = _migration_fixture(tmp_path, create_schema=True)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        assert set(sa.inspect(engine).get_table_names()) == {"alembic_version", "owned"}
    finally:
        engine.dispose()
