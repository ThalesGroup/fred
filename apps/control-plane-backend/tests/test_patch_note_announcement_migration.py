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

"""Patch-note migration: existing rows become banners, one enabled patch note."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

_VERSIONS = Path(__file__).parents[1] / "alembic/versions"
_NEW_TABLES = {
    "platform_announcement_dismissal",
    "platform_announcement_activation_event",
}


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, migration, operation: str) -> None:
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, operation)()


def _insert(connection, announcement_id: str, *, kind: str | None, enabled: bool):
    kind_column = ", kind" if kind else ""
    kind_value = f", '{kind}'" if kind else ""
    connection.execute(
        sa.text(
            "INSERT INTO platform_announcement (id, severity, title, "
            "description_short, description_long, enabled, dismissible, "
            f"content_version, created_at, updated_at{kind_column}) VALUES "
            "(:id, 'info', '{}', '{}', '{}', :enabled, 1, 1, "
            f"'2026-10-09', '2026-10-09'{kind_value})"
        ),
        {"id": announcement_id, "enabled": enabled},
    )


@pytest.fixture
def engine():
    engine = sa.create_engine("sqlite://")
    _run(engine, _load("b88202b8451e_add_platform_announcement_table.py"), "upgrade")
    with engine.begin() as connection:
        _insert(connection, "legacy", kind=None, enabled=True)
    try:
        yield engine
    finally:
        engine.dispose()


def test_upgrade_backfills_banners_and_enforces_one_active_patch_note(engine):
    migration = _load("cb6f39c6d80c_add_patch_note_announcements.py")
    _run(engine, migration, "upgrade")

    with engine.begin() as connection:
        kind = connection.scalar(
            sa.text("SELECT kind FROM platform_announcement WHERE id = 'legacy'")
        )
        _insert(connection, "p1", kind="patch_note", enabled=True)
        _insert(connection, "p2", kind="patch_note", enabled=False)
    assert kind == "banner"
    assert _NEW_TABLES <= set(sa.inspect(engine).get_table_names())
    severity = {
        c["name"]: c
        for c in sa.inspect(engine).get_columns(
            "platform_announcement_activation_event"
        )
    }["severity"]
    assert severity["nullable"] is True
    dismissal = {
        c["name"]: c
        for c in sa.inspect(engine).get_columns("platform_announcement_dismissal")
    }
    assert set(dismissal) == {"announcement_id", "user_id", "dismissed_at"}
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE platform_announcement SET enabled = 1 WHERE id = 'p2'")
            )


def test_downgrade_drops_the_new_column_and_tables_and_the_patch_notes(engine):
    migration = _load("cb6f39c6d80c_add_patch_note_announcements.py")
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        _insert(connection, "p1", kind="patch_note", enabled=True)
    _run(engine, migration, "downgrade")

    inspector = sa.inspect(engine)
    assert not _NEW_TABLES & set(inspector.get_table_names())
    columns = {c["name"] for c in inspector.get_columns("platform_announcement")}
    assert "kind" not in columns
    with engine.begin() as connection:
        ids = connection.scalars(sa.text("SELECT id FROM platform_announcement"))
        # A patch note left behind would come back as a broken banner.
        assert list(ids) == ["legacy"]
