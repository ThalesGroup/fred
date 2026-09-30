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

"""`02d556a6f182_give_every_hidden_alternate_version_a_name_of_its_own` — the
portable branch, driven through Alembic's `Operations` context against a real
SQLite engine exactly as `alembic upgrade` would, following
`test_document_labels_migration.py`.

This file covers the SQLite branch only. The PostgreSQL branch — the one that
actually runs on a deployment — is covered by
`test_alternate_version_migration_postgres.py`, which needs a real PostgreSQL
and so is marked `integration` and excluded from `make test`. Both exist
deliberately: `test_postgres_document_store_sql.py` records a production
failure that a SQLite-only test could never have caught, in this same table.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_MIGRATION_FILE = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "02d556a6f182_give_every_hidden_alternate_version_a_name_of_its_own.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("alternate_version_migration_02d556a6f182", _MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load_migration_module()


def _engine() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE metadata (document_uid VARCHAR PRIMARY KEY, source_tag VARCHAR, tag_ids JSON, doc JSON)"))
    return engine


def _insert(engine: sa.Engine, uid: str, name: str, tags: list[str], version: int | None = None, **identity: object) -> None:
    doc: dict = {"identity": {"document_name": name, "document_uid": uid, **identity}}
    if version is not None:
        doc["identity"]["version"] = version
        doc["identity"]["canonical_name"] = name
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES (:uid, :tags, :doc)"),
            {"uid": uid, "tags": json.dumps(tags), "doc": json.dumps(doc)},
        )


def _run_upgrade(engine: sa.Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _migration.upgrade()
        conn.commit()


def _identities(engine: sa.Engine) -> dict[str, dict]:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT document_uid, doc FROM metadata")).fetchall()
    return {uid: json.loads(doc)["identity"] for uid, doc in rows}


def test_alternate_sharing_a_name_gets_the_suffix_before_the_extension() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    identities = _identities(engine)
    assert identities["base"]["document_name"] == "report.pdf"
    assert identities["alt"]["document_name"] == "report (1).pdf"


def test_the_versioning_fields_are_gone_from_every_alternate() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    alt = _identities(engine)["alt"]
    assert "version" not in alt
    assert "canonical_name" not in alt


def test_an_alternate_whose_base_is_gone_keeps_the_name_it_has() -> None:
    """The developer's own corpus holds exactly this: promotion only runs when
    the deleted document was itself a base in the same folder, so an alternate
    outlives its base easily. Suffixing it would be renaming for nothing."""
    engine = _engine()
    _insert(engine, "orphan", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    identity = _identities(engine)["orphan"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity


def test_the_suffix_skips_a_number_a_third_document_already_holds() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "squatter", "report (1).pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report (2).pdf"


def test_two_alternates_in_one_folder_do_not_both_claim_the_same_number() -> None:
    engine = _engine()
    _insert(engine, "base-a", "report.pdf", ["folder-a"])
    _insert(engine, "alt-a", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "base-b", "report.pdf", ["folder-a"])
    _insert(engine, "alt-b", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    names = {uid: identity["document_name"] for uid, identity in _identities(engine).items()}
    assert sorted(names.values()) == ["report (1).pdf", "report (2).pdf", "report.pdf", "report.pdf"]


def test_a_name_free_in_one_folder_but_taken_in_another_is_not_used() -> None:
    """An alternate in two folders has to end up unambiguous in both."""
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "elsewhere", "report (1).pdf", ["folder-b"])
    _insert(engine, "alt", "report.pdf", ["folder-a", "folder-b"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report (2).pdf"


def test_a_same_name_document_in_another_folder_is_not_a_collision() -> None:
    engine = _engine()
    _insert(engine, "unrelated", "report.pdf", ["folder-b"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report.pdf"


def test_a_document_in_no_folder_keeps_its_name() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", [])
    _insert(engine, "alt", "report.pdf", [], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report.pdf"


def test_an_ordinary_document_keeps_its_name_but_loses_the_dead_fields() -> None:
    """`version: 0` is not an alternate and must not be renamed — but leaving the
    key behind would leave dead data reading like a live field."""
    engine = _engine()
    _insert(engine, "plain", "report.pdf", ["folder-a"], version=0)
    _insert(engine, "no-version-key", "memo.pdf", ["folder-a"])

    _run_upgrade(engine)

    identities = _identities(engine)
    assert identities["plain"]["document_name"] == "report.pdf"
    assert "version" not in identities["plain"]
    assert "canonical_name" not in identities["plain"]
    assert identities["no-version-key"]["document_name"] == "memo.pdf"


def test_a_nameless_alternate_does_not_destroy_its_own_row() -> None:
    """`jsonb_set` is strict: one NULL argument makes the whole result NULL, and
    `doc` is nullable, so setting a missing name would blank the document
    entirely — after which every listing holding that row fails to deserialise,
    taking the folder page with it, not just the one document."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('nameless', :tags, :doc)"),
            {"tags": json.dumps(["folder-a"]), "doc": json.dumps({"identity": {"document_uid": "nameless", "version": 1}})},
        )

    _run_upgrade(engine)

    with engine.connect() as conn:
        doc = conn.execute(sa.text("SELECT doc FROM metadata WHERE document_uid = 'nameless'")).scalar_one()
    assert doc is not None
    identity = json.loads(doc)["identity"]
    assert identity["document_uid"] == "nameless"
    assert "version" not in identity


def test_not_one_document_is_left_carrying_either_field() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "plain", "memo.pdf", ["folder-a"], version=0)

    _run_upgrade(engine)

    for identity in _identities(engine).values():
        assert "version" not in identity
        assert "canonical_name" not in identity


def test_a_title_survives_the_rename() -> None:
    """`rename_document` clears `title` because a user renaming a document
    supersedes their own earlier title. A migration carries no such intent, and
    dropping the title would lose what the user actually typed."""
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1, title="Rapport annuel")

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["title"] == "Rapport annuel"


def test_running_it_twice_changes_nothing_the_second_time() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)
    after_first = _identities(engine)
    _run_upgrade(engine)

    assert _identities(engine) == after_first


def test_a_run_resumed_after_a_partial_one_finishes_the_job() -> None:
    """A crash mid-migration leaves some alternates renamed and cleared and
    others untouched, because each document is one statement. The resumed run
    must pick up only the ones still carrying the fields."""
    engine = _engine()
    _insert(engine, "base-a", "report.pdf", ["folder-a"])
    _insert(engine, "alt-a", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "base-b", "memo.pdf", ["folder-a"])
    _insert(engine, "alt-b", "memo.pdf", ["folder-a"], version=1)

    # Simulate the first run having finished alt-a only.
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE metadata SET doc = :doc WHERE document_uid = 'alt-a'"),
            {"doc": json.dumps({"identity": {"document_name": "report (1).pdf", "document_uid": "alt-a"}})},
        )

    _run_upgrade(engine)

    names = {uid: identity["document_name"] for uid, identity in _identities(engine).items()}
    assert names["alt-a"] == "report (1).pdf"
    assert names["alt-b"] == "memo (1).pdf"


def test_no_document_is_deleted_and_every_uid_survives() -> None:
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "orphan", "memo.pdf", ["folder-b"], version=1)

    _run_upgrade(engine)

    with engine.connect() as conn:
        uids = {row[0] for row in conn.execute(sa.text("SELECT document_uid FROM metadata"))}
    assert uids == {"base", "alt", "orphan"}


def test_every_document_in_a_folder_ends_up_with_a_distinct_name() -> None:
    """The property the whole migration exists for: no folder is left holding
    two documents a user cannot tell apart."""
    engine = _engine()
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "other", "memo.pdf", ["folder-a"])

    _run_upgrade(engine)

    names = [identity["document_name"] for identity in _identities(engine).values()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("report.pdf", "report (1).pdf"),
        ("2-regl_PASSI_v2.2.pdf", "2-regl_PASSI_v2.2 (1).pdf"),
        ("archive.tar.gz", "archive.tar (1).gz"),
        ("README", "README (1)"),
        (".gitignore", ".gitignore (1)"),
    ],
)
def test_the_suffix_goes_before_the_extension(name: str, expected: str) -> None:
    assert _migration._suffixed(name, 1) == expected


def test_a_non_numeric_version_is_not_treated_as_an_alternate() -> None:
    """Nothing should write a string there, but a hand-edited row must not make
    the migration raise on a cast — it is dropped like any other stale key,
    without the document being renamed."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('odd', :tags, :doc)"),
            {"tags": json.dumps(["folder-a"]), "doc": json.dumps({"identity": {"document_name": "report.pdf", "document_uid": "odd", "version": "not-a-number"}})},
        )

    _run_upgrade(engine)

    identity = _identities(engine)["odd"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity
