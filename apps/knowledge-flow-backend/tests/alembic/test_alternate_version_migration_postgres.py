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
PostgreSQL branch, against a real PostgreSQL.

This is the branch a deployment runs, and it is the half a SQLite test cannot
reach: `jsonb_set`, `#-`, `to_jsonb` and the `&&` array overlap all exist only
here, and PostgreSQL infers a bind parameter's type from where it sits. The
sibling `test_postgres_document_store_sql.py` records a production failure in
this same table caused by exactly that — a parameter passed somewhere
PostgreSQL could not type it, which every SQLite test happily accepted.

Run:

    export FRED_PG_DSN="postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret
    .venv/bin/pytest tests/alembic/test_alternate_version_migration_postgres.py -m integration

Each test gets its own throwaway schema, dropped on teardown, so it never reads
or writes the dev database's real tables.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest
import sqlalchemy as sa

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
_DEFAULT_DSN = "postgresql+psycopg2://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret

_MIGRATION_FILE = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "02d556a6f182_give_every_hidden_alternate_version_a_name_of_its_own.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("alternate_version_migration_pg_02d556a6f182", _MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load_migration_module()


def _sync_dsn() -> str:
    """The lane's env var carries an asyncpg DSN; this migration runs on a sync
    connection, so the driver is swapped rather than asking for a second var."""
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    return dsn.replace("+asyncpg", "+psycopg2")


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    dsn = _sync_dsn()
    schema = f"kf_alt_itest_{uuid.uuid4().hex[:8]}"

    admin = sa.create_engine(dsn)
    with admin.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    admin.dispose()

    # The migration's SQL hardcodes `metadata`, so isolation comes from the
    # connection's search_path rather than from a table prefix.
    scoped = sa.create_engine(dsn, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with scoped.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE metadata (
                        document_uid VARCHAR PRIMARY KEY,
                        source_tag VARCHAR,
                        tag_ids VARCHAR[],
                        doc JSONB
                    )
                    """
                )
            )
        yield scoped
    finally:
        scoped.dispose()
        admin = sa.create_engine(dsn)
        with admin.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _insert(engine: sa.Engine, uid: str, name: str, tags: list[str] | None, version: int | None = None, **identity: object) -> None:
    doc: dict = {"identity": {"document_name": name, "document_uid": uid, **identity}}
    if version is not None:
        doc["identity"]["version"] = version
        doc["identity"]["canonical_name"] = name
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES (:uid, :tags, CAST(:doc AS jsonb))"),
            {"uid": uid, "tags": tags, "doc": json.dumps(doc)},
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
    return {uid: doc["identity"] for uid, doc in rows}


def test_the_statements_run_at_all_on_postgresql(engine: sa.Engine) -> None:
    """The regression guard: every parameter has to be typable where it sits."""
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    identities = _identities(engine)
    assert identities["alt"]["document_name"] == "report (1).pdf"
    assert "version" not in identities["alt"]
    assert "canonical_name" not in identities["alt"]
    assert identities["base"]["document_name"] == "report.pdf"


def test_an_alternate_whose_base_is_gone_keeps_the_name_it_has(engine: sa.Engine) -> None:
    _insert(engine, "orphan", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    identity = _identities(engine)["orphan"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity


def test_the_suffix_skips_a_number_a_third_document_already_holds(engine: sa.Engine) -> None:
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "squatter", "report (1).pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report (2).pdf"


def test_two_alternates_in_one_folder_do_not_both_claim_the_same_number(engine: sa.Engine) -> None:
    """Each rename is committed before the next candidate is tested, so the
    second alternate's collision query already sees the first one's new name."""
    _insert(engine, "base-a", "report.pdf", ["folder-a"])
    _insert(engine, "alt-a", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "base-b", "report.pdf", ["folder-a"])
    _insert(engine, "alt-b", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    names = sorted(identity["document_name"] for identity in _identities(engine).values())
    assert names == ["report (1).pdf", "report (2).pdf", "report.pdf", "report.pdf"]


def test_a_name_free_in_one_folder_but_taken_in_another_is_not_used(engine: sa.Engine) -> None:
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "elsewhere", "report (1).pdf", ["folder-b"])
    _insert(engine, "alt", "report.pdf", ["folder-a", "folder-b"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report (2).pdf"


def test_a_same_name_document_in_another_folder_is_not_a_collision(engine: sa.Engine) -> None:
    _insert(engine, "unrelated", "report.pdf", ["folder-b"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["document_name"] == "report.pdf"


def test_a_document_with_no_tags_at_all_keeps_its_name(engine: sa.Engine) -> None:
    """`tag_ids` is NULL rather than empty for documents that never had one, and
    `&&` against NULL is NULL, not false — hence the COALESCE in the select."""
    _insert(engine, "base", "report.pdf", None)
    _insert(engine, "alt", "report.pdf", None, version=1)

    _run_upgrade(engine)

    identity = _identities(engine)["alt"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity


def test_ordinary_documents_are_left_alone(engine: sa.Engine) -> None:
    _insert(engine, "plain", "report.pdf", ["folder-a"], version=0)
    _insert(engine, "no-version-key", "memo.pdf", ["folder-a"])

    _run_upgrade(engine)

    identities = _identities(engine)
    assert identities["plain"]["version"] == 0
    assert identities["no-version-key"]["document_name"] == "memo.pdf"


def test_a_non_numeric_version_does_not_raise_on_the_cast(engine: sa.Engine) -> None:
    """The CASE guard exists because PostgreSQL does not promise to evaluate a
    regex test in the same WHERE before the `::int` beside it."""
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('odd', :tags, CAST(:doc AS jsonb))"),
            {"tags": ["folder-a"], "doc": json.dumps({"identity": {"document_name": "report.pdf", "document_uid": "odd", "version": "not-a-number"}})},
        )

    _run_upgrade(engine)

    assert _identities(engine)["odd"]["version"] == "not-a-number"


def test_a_title_survives_the_rename(engine: sa.Engine) -> None:
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1, title="Rapport annuel")

    _run_upgrade(engine)

    assert _identities(engine)["alt"]["title"] == "Rapport annuel"


def test_running_it_twice_changes_nothing_the_second_time(engine: sa.Engine) -> None:
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    _run_upgrade(engine)
    after_first = _identities(engine)
    _run_upgrade(engine)

    assert _identities(engine) == after_first


def test_no_document_is_deleted(engine: sa.Engine) -> None:
    _insert(engine, "base", "report.pdf", ["folder-a"])
    _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    _insert(engine, "orphan", "memo.pdf", ["folder-b"], version=1)

    _run_upgrade(engine)

    with engine.connect() as conn:
        uids = {row[0] for row in conn.execute(sa.text("SELECT document_uid FROM metadata"))}
    assert uids == {"base", "alt", "orphan"}
