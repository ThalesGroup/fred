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

"""Patch-note migrations: the announcement kind, then the browsable history."""

import importlib.util
import json
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


def _insert(
    connection,
    announcement_id: str,
    *,
    kind: str | None,
    enabled: bool,
    created_at: str = "2026-10-09",
):
    kind_column = ", kind" if kind else ""
    kind_value = f", '{kind}'" if kind else ""
    connection.execute(
        sa.text(
            "INSERT INTO platform_announcement (id, severity, title, "
            "description_short, description_long, enabled, dismissible, "
            f"content_version, created_at, updated_at{kind_column}) VALUES "
            "(:id, 'info', '{}', '{}', '{}', :enabled, 1, 1, "
            f":created_at, :created_at{kind_value})"
        ),
        {"id": announcement_id, "enabled": enabled, "created_at": created_at},
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


_HISTORY = "e5ff6d80cc9f_browse_patch_note_history.py"


@pytest.fixture
def with_patch_notes(engine):
    """Three patch notes of different ages, the middle one enabled and dismissed."""
    _run(engine, _load("cb6f39c6d80c_add_patch_note_announcements.py"), "upgrade")
    with engine.begin() as connection:
        _insert(
            connection, "old", kind="patch_note", enabled=False, created_at="2026-08-01"
        )
        _insert(
            connection, "mid", kind="patch_note", enabled=True, created_at="2026-09-01"
        )
        _insert(
            connection, "new", kind="patch_note", enabled=False, created_at="2026-10-01"
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_dismissal VALUES "
                "('mid', 'alice', '2026-09-02')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_activation_event "
                "(id, announcement_id, kind, label, action, occurred_at) VALUES "
                "('e1', 'mid', 'patch_note', '{}', 'activated', '2026-09-01')"
            )
        )
    return engine


def _rows(engine, columns: str):
    with engine.begin() as connection:
        return connection.execute(
            sa.text(
                f"SELECT {columns} FROM platform_announcement ORDER BY created_at DESC"
            )
        ).all()


def test_history_upgrade_orders_newest_first_and_announces_nothing(with_patch_notes):
    engine = with_patch_notes
    _run(engine, _load(_HISTORY), "upgrade")

    assert _rows(engine, "id, position, enabled") == [
        ("legacy", None, 1),
        ("new", 1, 0),
        ("mid", 2, 1),
        ("old", 3, 0),
    ]
    tables = set(sa.inspect(engine).get_table_names())
    assert "platform_announcement_seen" in tables
    assert "platform_announcement_dismissal" not in tables
    seen = sa.inspect(engine).get_columns("platform_announcement_seen")
    assert {c["name"] for c in seen} == {"user_id", "announcement_event_id", "seen_at"}
    with engine.begin() as connection:
        # Nothing announced and nobody marked: no user gets a dialog.
        actions = connection.scalars(
            sa.text("SELECT action FROM platform_announcement_activation_event")
        ).all()
        assert actions == ["activated"]
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM platform_announcement_seen")
            )
            == 0
        )
        # The one-enabled rule is gone.
        connection.execute(
            sa.text("UPDATE platform_announcement SET enabled = 1 WHERE id = 'old'")
        )
    indexes = sa.inspect(engine).get_indexes("platform_announcement_activation_event")
    assert [i["column_names"] for i in indexes] == [["occurred_at"]]


def test_history_downgrade_keeps_the_top_visible_note_and_round_trips(
    with_patch_notes,
):
    engine = with_patch_notes
    migration = _load(_HISTORY)
    _run(engine, migration, "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE platform_announcement SET enabled = 1 WHERE id = 'old'")
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_activation_event "
                "(id, announcement_id, kind, label, action, occurred_at) VALUES "
                "('e2', 'mid', 'patch_note', '{}', 'announced', '2026-10-02'), "
                "('e3', 'mid', 'patch_note', '{}', 'unannounced', '2026-10-03')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_seen VALUES "
                "('alice', 'e2', '2026-10-02')"
            )
        )

    _run(engine, migration, "downgrade")

    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert "platform_announcement_dismissal" in tables
    assert "platform_announcement_seen" not in tables
    columns = {c["name"] for c in inspector.get_columns("platform_announcement")}
    assert "position" not in columns
    # "mid" is above "old", so it is the one the restored index lets stay on.
    assert _rows(engine, "id, enabled") == [
        ("legacy", 1),
        ("new", 0),
        ("mid", 1),
        ("old", 0),
    ]
    with engine.begin() as connection:
        actions = connection.scalars(
            sa.text("SELECT action FROM platform_announcement_activation_event")
        ).all()
        assert actions == ["activated"]
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE platform_announcement SET enabled = 1 WHERE id = 'new'")
            )

    _run(engine, migration, "upgrade")
    assert _rows(engine, "id, position") == [
        ("legacy", None),
        ("new", 1),
        ("mid", 2),
        ("old", 3),
    ]


_PACKAGES = "a6c1d94e27b3_patch_note_packages_and_exposures.py"


def _add_event(connection, event_id, announcement_id, kind, action, at, actor=None):
    connection.execute(
        sa.text(
            "INSERT INTO platform_announcement_activation_event "
            "(id, announcement_id, kind, label, action, severity, actor_uid, "
            "occurred_at) VALUES (:id, :a, :kind, :label, :action, :severity, "
            ":actor, :at)"
        ),
        {
            "id": event_id,
            "a": announcement_id,
            "kind": kind,
            "label": '{"en": "' + announcement_id + '"}',
            "action": action,
            "severity": "warning" if kind == "banner" else None,
            "actor": actor,
            "at": f"{at} 10:00:00.000000",
        },
    )


@pytest.fixture
def with_events(with_patch_notes):
    """After the first history migration: banner and patch-note events, "mid" enabled."""
    engine = with_patch_notes
    _run(engine, _load(_HISTORY), "upgrade")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                'UPDATE platform_announcement SET title = \'{"en": "Mid"}\', '
                'description_long = \'{"en": "# Mid", "fr": "# Milieu"}\' '
                "WHERE id = 'mid'"
            )
        )
        _add_event(
            connection, "b1", "legacy", "banner", "activated", "2026-08-01", "alice"
        )
        _add_event(
            connection, "b2", "legacy", "banner", "deactivated", "2026-08-05", "bob"
        )
        _add_event(
            connection, "b3", "legacy", "banner", "activated", "2026-08-09", "bob"
        )
        # A deactivation with no activation before it pairs with nothing.
        _add_event(connection, "b0", "gone", "banner", "deactivated", "2026-07-01")
        _add_event(
            connection, "p1", "old", "patch_note", "activated", "2026-08-02", "alice"
        )
        _add_event(connection, "p2", "old", "patch_note", "deactivated", "2026-08-31")
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_seen VALUES "
                "('alice', 'e9', '2026-10-02 10:00:00.000000')"
            )
        )
    return engine


def _lines(engine):
    with engine.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT id, kind, announcement_id, actor_uid, severity, note_count, "
                "opens_dialog, activated_at, deactivated_at, package, label "
                "FROM platform_announcement_exposure ORDER BY activated_at, id"
            )
        ).mappings()
        return [dict(row) for row in rows]


def test_exposure_upgrade_pairs_events_and_freezes_the_enabled_note(with_events):
    engine = with_events
    _run(engine, _load(_PACKAGES), "upgrade")

    *converted, package = _lines(engine)
    assert [
        (
            line["id"],
            line["kind"],
            line["actor_uid"],
            line["activated_at"][:10],
            (line["deactivated_at"] or "")[:10],
        )
        for line in converted[:3]
    ] == [
        ("b1", "banner", "alice", "2026-08-01", "2026-08-05"),
        ("p1", "patch_note", "alice", "2026-08-02", "2026-08-31"),
        ("b3", "banner", "bob", "2026-08-09", ""),
    ]
    assert converted[0]["severity"] == "warning"
    assert json.loads(converted[0]["label"]) == {"en": "legacy"}
    # "e1" is the enabled note's own activation: ended, it kept no content.
    [earlier] = converted[3:]
    assert earlier["id"] == "e1" and earlier["deactivated_at"] is not None
    assert all(line["note_count"] is None for line in converted)
    assert all(line["package"] is None for line in converted)

    assert (package["kind"], package["announcement_id"]) == ("patch_note", "mid")
    assert (package["note_count"], package["actor_uid"]) == (1, None)
    # Readable, pending for nobody.
    assert package["opens_dialog"] == 0 and package["deactivated_at"] is None
    assert json.loads(package["label"]) == {"en": "Mid"}
    assert json.loads(package["package"]) == [
        {
            "id": "mid",
            "title": {"en": "Mid"},
            "description_long": {"en": "# Mid", "fr": "# Milieu"},
        }
    ]

    inspector = sa.inspect(engine)
    assert "platform_announcement_activation_event" not in inspector.get_table_names()
    seen = {c["name"] for c in inspector.get_columns("platform_announcement_seen")}
    assert seen == {"user_id", "announcement_id", "seen_at"}
    with engine.begin() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT announcement_id FROM platform_announcement_seen")
            )
            == "e9"
        )
        # The toggle stays on: the note is in the next announcement too.
        assert (
            connection.scalar(
                sa.text("SELECT enabled FROM platform_announcement WHERE id = 'mid'")
            )
            == 1
        )


def test_exposure_upgrade_without_enabled_patch_note_leaves_no_package(with_events):
    engine = with_events
    with engine.begin() as connection:
        connection.execute(sa.text("UPDATE platform_announcement SET enabled = 0"))

    _run(engine, _load(_PACKAGES), "upgrade")

    assert all(line["note_count"] is None for line in _lines(engine))


def test_exposure_downgrade_rebuilds_events_and_round_trips(with_events):
    engine = with_events
    migration = _load(_PACKAGES)
    _run(engine, migration, "upgrade")
    before = [line["id"] for line in _lines(engine) if line["note_count"] is None]
    with engine.begin() as connection:
        # An announcement made after the upgrade, then withdrawn.
        connection.execute(
            sa.text(
                "INSERT INTO platform_announcement_exposure (id, kind, "
                "announcement_id, label, actor_uid, activated_at, deactivated_at, "
                "note_count, package, opens_dialog) VALUES ('n1', 'patch_note', "
                "'mid', '{}', 'carol', '2026-10-20 10:00:00.000000', "
                "'2026-10-21 10:00:00.000000', 1, '[]', 1)"
            )
        )

    _run(engine, migration, "downgrade")

    inspector = sa.inspect(engine)
    assert "platform_announcement_exposure" not in inspector.get_table_names()
    seen = {c["name"] for c in inspector.get_columns("platform_announcement_seen")}
    assert "announcement_event_id" in seen
    with engine.begin() as connection:
        events = connection.execute(
            sa.text(
                "SELECT announcement_id, action, actor_uid FROM "
                "platform_announcement_activation_event ORDER BY occurred_at, action"
            )
        ).all()
    assert [tuple(e) for e in events if e[0] == "legacy"] == [
        ("legacy", "activated", "alice"),
        ("legacy", "deactivated", None),
        ("legacy", "activated", "bob"),
    ]
    announcing = [tuple(e) for e in events if e[1] in ("announced", "unannounced")]
    # The upgrade's own package is not an announcement: it would open a dialog.
    assert announcing == [("mid", "announced", "carol"), ("mid", "unannounced", None)]

    _run(engine, migration, "upgrade")
    again = [line["id"] for line in _lines(engine) if line["note_count"] is None]
    assert set(before) <= set(again)
