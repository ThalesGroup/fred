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
