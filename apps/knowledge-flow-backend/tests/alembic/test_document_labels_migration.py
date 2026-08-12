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

"""`bcd7cbdbedca_add_document_labels_table` — runs the migration's own
`upgrade()`/`downgrade()` functions directly against a real (sync) SQLite
engine, driven through Alembic's `Operations` context exactly as the real
`alembic upgrade`/`downgrade` CLI would. This is narrower than the full CLI
(no revision-chain walking) but exercises the actual backfill/strip/
reconstruct SQL this migration runs, which `make db-check-sqlite` cannot
fully do on its own (see the module docstring caveat below).

IMPORTANT LIMITATION: this runs the migration's SQLite branch only, offline
and on every `make test` run. The PostgreSQL-specific branch (the set-based
`INSERT ... SELECT` backfill over `jsonb_array_elements_text`, and the
`jsonb_agg`-based downgrade reconstruction) has no PostgreSQL available in
this offline test environment and is not exercised by this file — same
documented gap as `test_postgres_document_store_bulk_mark_vector_done.py`.
It was verified manually, upgrade and downgrade, against a real disposable
PostgreSQL 16 container (multi-label, duplicate/whitespace normalization,
Unicode/special characters, empty-array, missing-key, and a post-migration
mutation surviving downgrade) as part of the labels-lot close-out that
introduced the set-based rewrite; recommend the same manual check for any
future edit to this migration's PostgreSQL branch.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_FILE = _MIGRATIONS_DIR / "bcd7cbdbedca_add_document_labels_table.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("document_labels_migration_bcd7cbdbedca", _MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load_migration_module()


def _make_sqlite_engine_with_parent_schema() -> sa.Engine:
    """A sync SQLite engine with just enough schema for this migration to run
    against: `metadata.document_uid`/`doc`, the parent state before
    `bcd7cbdbedca` -- i.e. deliberately WITHOUT `document_labels`, which is
    exactly what this migration's `upgrade()` is responsible for creating."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE metadata (document_uid VARCHAR PRIMARY KEY, source_tag VARCHAR, doc JSON)"))
    return engine


def _run_upgrade(engine: sa.Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _migration.upgrade()
        conn.commit()


def _run_downgrade(engine: sa.Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _migration.downgrade()
        conn.commit()


def _insert_metadata_row(engine: sa.Engine, *, document_uid: str, doc: dict) -> None:
    import json

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, source_tag, doc) VALUES (:uid, 'fred', :doc)"),
            {"uid": document_uid, "doc": json.dumps(doc)},
        )


def _document_labels_rows(engine: sa.Engine) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT document_uid, label FROM document_labels ORDER BY document_uid, label")).fetchall()
    return [(r[0], r[1]) for r in rows]


def _doc_json(engine: sa.Engine, document_uid: str) -> dict:
    import json

    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT doc FROM metadata WHERE document_uid = :uid"), {"uid": document_uid}).fetchone()
    assert row is not None
    return json.loads(row[0]) if isinstance(row[0], str) else row[0]


def test_upgrade_creates_the_table_and_leaves_a_labelless_document_untouched() -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-no-labels",
        doc={"identity": {"document_name": "n.pdf", "document_uid": "doc-no-labels"}},
    )

    _run_upgrade(engine)

    assert _document_labels_rows(engine) == []
    assert "labels" not in _doc_json(engine, "doc-no-labels")


def test_upgrade_backfills_a_document_with_several_labels() -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-multi",
        doc={
            "identity": {"document_name": "m.pdf", "document_uid": "doc-multi"},
            "labels": ["DAT", "MEX"],
        },
    )

    _run_upgrade(engine)

    assert _document_labels_rows(engine) == [("doc-multi", "DAT"), ("doc-multi", "MEX")]
    assert "labels" not in _doc_json(engine, "doc-multi")


def test_upgrade_deduplicates_labels_that_only_collide_after_normalization() -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-dupe",
        doc={
            "identity": {"document_name": "d.pdf", "document_uid": "doc-dupe"},
            "labels": [" DAT ", "DAT", "DAT", "", "   "],
        },
    )

    _run_upgrade(engine)

    assert _document_labels_rows(engine) == [("doc-dupe", "DAT")]


def test_upgrade_preserves_unicode_and_special_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    tricky = ["café", "日本語", "a/b#c?d%e"]
    _insert_metadata_row(
        engine,
        document_uid="doc-unicode",
        doc={"identity": {"document_name": "u.pdf", "document_uid": "doc-unicode"}, "labels": tricky},
    )

    _run_upgrade(engine)

    stored = sorted(label for _, label in _document_labels_rows(engine))
    assert stored == sorted(tricky)


def test_upgrade_is_safe_for_a_document_missing_the_labels_key_entirely() -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-old",
        doc={"identity": {"document_name": "o.pdf", "document_uid": "doc-old"}},  # no "labels" key at all
    )

    _run_upgrade(engine)  # must not raise

    assert _document_labels_rows(engine) == []


def test_downgrade_reconstructs_labels_in_the_json_blob_without_data_loss() -> None:
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-a",
        doc={"identity": {"document_name": "a.pdf", "document_uid": "doc-a"}, "labels": ["DAT", "MEX"]},
    )
    _insert_metadata_row(
        engine,
        document_uid="doc-b",
        doc={"identity": {"document_name": "b.pdf", "document_uid": "doc-b"}},
    )
    _run_upgrade(engine)

    _run_downgrade(engine)

    assert _doc_json(engine, "doc-a")["labels"] == ["DAT", "MEX"]
    # A document that never had a label reconstructs to an empty list, not a
    # missing key -- matching DocumentMetadata.labels' own default_factory.
    assert _doc_json(engine, "doc-b")["labels"] == []
    with engine.connect() as conn:
        table_exists = conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='document_labels'")).fetchone()
    assert table_exists is None


def test_downgrade_after_a_post_migration_label_mutation_still_reconstructs_it() -> None:
    """The label was never in the original backfill -- it was added later,
    through the new table only -- and must still come back on downgrade."""
    engine = _make_sqlite_engine_with_parent_schema()
    _insert_metadata_row(
        engine,
        document_uid="doc-c",
        doc={"identity": {"document_name": "c.pdf", "document_uid": "doc-c"}},
    )
    _run_upgrade(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO document_labels (document_uid, label) VALUES ('doc-c', 'ADDED-AFTER-MIGRATION')"))

    _run_downgrade(engine)

    assert _doc_json(engine, "doc-c")["labels"] == ["ADDED-AFTER-MIGRATION"]
