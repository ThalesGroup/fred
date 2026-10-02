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

Driven through `create_async_engine` + `run_sync`, which is how
`fred_core.sql.alembic_env` runs a migration: the DBAPI underneath is therefore
asyncpg, the one a deployment uses. Which driver runs matters because parameter
typing is where it differs — asyncpg prepares server-side, so a parameter whose
type PostgreSQL cannot infer fails there. Dropping the `CAST` inside this
migration's `to_jsonb` reproduces the failure here as
`could not determine polymorphic type because input has type unknown`.

Run:

    docker compose -f ../../scripts/docker-compose.postgres.yml up -d
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
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
# The disposable PostgreSQL `scripts/docker-compose.postgres.yml` provisions —
# the default `alembic.mk` and the control-plane's store tests already use. Never
# the dev stack's own database, whose `metadata` table holds a real corpus and
# which this migration's unqualified `UPDATE metadata` would reach.
_DEFAULT_DSN = "postgresql+asyncpg://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret

_MIGRATION_FILE = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "02d556a6f182_give_every_hidden_alternate_version_a_name_of_its_own.py"


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("alternate_version_migration_pg_02d556a6f182", _MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load_migration_module()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    schema = f"kf_alt_itest_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    await admin.dispose()

    # The migration's SQL hardcodes `metadata`, so isolation comes from the
    # connection's search_path rather than from a table prefix.
    scoped = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with scoped.begin() as conn:
            await conn.execute(
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
        await scoped.dispose()
        admin = create_async_engine(dsn)
        async with admin.begin() as conn:
            await conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def _insert(engine: AsyncEngine, uid: str, name: str, tags: list[str] | None, version: int | None = None, **identity: object) -> None:
    doc: dict = {"identity": {"document_name": name, "document_uid": uid, **identity}}
    if version is not None:
        doc["identity"]["version"] = version
        doc["identity"]["canonical_name"] = name
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES (:uid, :tags, CAST(:doc AS jsonb))"),
            {"uid": uid, "tags": tags, "doc": json.dumps(doc)},
        )


def _do_upgrade(sync_conn: sa.Connection) -> None:
    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        _migration.upgrade()


async def _run_upgrade(engine: AsyncEngine) -> None:
    """Exactly `alembic_env`'s shape: an async connection, `run_sync`, asyncpg."""
    async with engine.begin() as conn:
        await conn.run_sync(_do_upgrade)


async def _identities(engine: AsyncEngine) -> dict[str, dict]:
    async with engine.connect() as conn:
        rows = (await conn.execute(sa.text("SELECT document_uid, doc FROM metadata"))).fetchall()
    return {uid: doc["identity"] for uid, doc in rows}


@pytest.mark.asyncio
async def test_the_statements_run_at_all_on_postgresql(engine: AsyncEngine) -> None:
    """The regression guard: every parameter has to be typable where it sits."""
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["alt"]["document_name"] == "report (1).pdf"
    assert "version" not in identities["alt"]
    assert "canonical_name" not in identities["alt"]
    assert identities["base"]["document_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_an_alternate_whose_base_is_gone_keeps_the_name_it_has(engine: AsyncEngine) -> None:
    await _insert(engine, "orphan", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)

    identity = (await _identities(engine))["orphan"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity


@pytest.mark.asyncio
async def test_the_suffix_skips_a_number_a_third_document_already_holds(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "squatter", "report (1).pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)

    assert (await _identities(engine))["alt"]["document_name"] == "report (2).pdf"


@pytest.mark.asyncio
async def test_two_alternates_in_one_folder_do_not_both_claim_the_same_number(engine: AsyncEngine) -> None:
    """Each rename is committed before the next candidate is tested, so the
    second alternate's collision query already sees the first one's new name."""
    await _insert(engine, "base-a", "report.pdf", ["folder-a"])
    await _insert(engine, "alt-a", "report.pdf", ["folder-a"], version=1)
    await _insert(engine, "base-b", "report.pdf", ["folder-a"])
    await _insert(engine, "alt-b", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)

    names = sorted(identity["document_name"] for identity in (await _identities(engine)).values())
    assert names == ["report (1).pdf", "report (2).pdf", "report.pdf", "report.pdf"]


@pytest.mark.asyncio
async def test_a_name_free_in_one_folder_but_taken_in_another_is_not_used(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "elsewhere", "report (1).pdf", ["folder-b"])
    await _insert(engine, "alt", "report.pdf", ["folder-a", "folder-b"], version=1)

    await _run_upgrade(engine)

    assert (await _identities(engine))["alt"]["document_name"] == "report (2).pdf"


@pytest.mark.asyncio
async def test_a_same_name_document_in_another_folder_is_not_a_collision(engine: AsyncEngine) -> None:
    await _insert(engine, "unrelated", "report.pdf", ["folder-b"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)

    assert (await _identities(engine))["alt"]["document_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_a_document_with_no_tags_at_all_keeps_its_name(engine: AsyncEngine) -> None:
    """`tag_ids` is NULL rather than empty for documents that never had one, and
    `&&` against NULL is NULL, not false — hence the COALESCE in the select."""
    await _insert(engine, "base", "report.pdf", None)
    await _insert(engine, "alt", "report.pdf", None, version=1)

    await _run_upgrade(engine)

    identity = (await _identities(engine))["alt"]
    assert identity["document_name"] == "report.pdf"
    assert "version" not in identity


@pytest.mark.asyncio
async def test_an_ordinary_document_is_not_rewritten_at_all(engine: AsyncEngine) -> None:
    """Almost every row carried `version: 0`, so a guard on "has either key"
    filters nothing and rewrites the whole table — measured at 20 s and 1.1 GB of
    WAL at 500k documents, against the 30 s `statement_timeout` `alembic_env`
    sets, in one transaction. The keys are inert and leave on the next save."""
    await _insert(engine, "plain", "report.pdf", ["folder-a"], version=0)
    await _insert(engine, "no-version-key", "memo.pdf", ["folder-a"])

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["plain"]["document_name"] == "report.pdf"
    assert identities["plain"]["version"] == 0
    assert identities["no-version-key"]["document_name"] == "memo.pdf"


@pytest.mark.asyncio
async def test_a_nameless_alternate_does_not_destroy_its_own_row(engine: AsyncEngine) -> None:
    """`jsonb_set` is strict: one NULL argument makes the whole result NULL, and
    `doc` is nullable, so setting a missing name blanks the document entirely —
    after which every listing holding that row fails to deserialise, taking the
    folder page with it, not just the one document."""
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('nameless', :tags, CAST(:doc AS jsonb))"),
            {"tags": ["folder-a"], "doc": json.dumps({"identity": {"document_uid": "nameless", "version": 1}})},
        )

    await _run_upgrade(engine)

    async with engine.connect() as conn:
        doc = (await conn.execute(sa.text("SELECT doc FROM metadata WHERE document_uid = 'nameless'"))).scalar_one()
    assert doc is not None
    assert doc["identity"]["document_uid"] == "nameless"


@pytest.mark.asyncio
async def test_only_the_alternates_are_touched(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"], version=0)
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    await _insert(engine, "plain", "memo.pdf", ["folder-a"], version=0)

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert "version" not in identities["alt"]
    assert identities["base"]["version"] == 0
    assert identities["plain"]["version"] == 0


@pytest.mark.asyncio
async def test_a_version_too_large_for_int4_is_still_migrated(engine: AsyncEngine) -> None:
    """`::int` here raised `NumericValueOutOfRangeError` and aborted the whole
    upgrade. The old model bounded `version` below with `ge=0`, never above."""
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "huge", "report.pdf", ["folder-a"], version=3000000000)

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["huge"]["document_name"] == "report (1).pdf"
    assert "version" not in identities["huge"]


@pytest.mark.asyncio
async def test_a_version_that_is_a_numeric_string_is_not_an_alternate(engine: AsyncEngine) -> None:
    """The regex form matched "1" and renamed the document while the portable
    branch left it alone. Both now ask for a JSON number."""
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('stringy', :tags, CAST(:doc AS jsonb))"),
            {"tags": ["folder-a"], "doc": json.dumps({"identity": {"document_name": "report.pdf", "document_uid": "stringy", "version": "1"}})},
        )

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["stringy"]["document_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_a_scalar_identity_does_not_abort_the_whole_upgrade(engine: AsyncEngine) -> None:
    """`'{"identity":"version"}'::jsonb -> 'identity' ?| ARRAY['version']` is
    true, so the strip pass reached `- 'version'` on a scalar and failed with
    "cannot delete from scalar", taking every other document down with it."""
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('odd-shape', :tags, CAST(:doc AS jsonb))"),
            {"tags": ["folder-a"], "doc": json.dumps({"identity": "version"})},
        )

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["alt"]["document_name"] == "report (1).pdf"


@pytest.mark.asyncio
async def test_a_non_numeric_version_does_not_raise_on_the_cast(engine: AsyncEngine) -> None:
    """The CASE guard exists because PostgreSQL does not promise to evaluate a
    regex test in the same WHERE before the `::int` beside it."""
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO metadata (document_uid, tag_ids, doc) VALUES ('odd', :tags, CAST(:doc AS jsonb))"),
            {"tags": ["folder-a"], "doc": json.dumps({"identity": {"document_name": "report.pdf", "document_uid": "odd", "version": "not-a-number"}})},
        )

    await _run_upgrade(engine)

    identities = await _identities(engine)
    assert identities["odd"]["document_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_a_title_survives_the_rename(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1, title="Rapport annuel")

    await _run_upgrade(engine)

    assert (await _identities(engine))["alt"]["title"] == "Rapport annuel"


@pytest.mark.asyncio
async def test_running_it_twice_changes_nothing_the_second_time(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)

    await _run_upgrade(engine)
    after_first = await _identities(engine)
    await _run_upgrade(engine)

    assert (await _identities(engine)) == after_first


@pytest.mark.asyncio
async def test_no_document_is_deleted(engine: AsyncEngine) -> None:
    await _insert(engine, "base", "report.pdf", ["folder-a"])
    await _insert(engine, "alt", "report.pdf", ["folder-a"], version=1)
    await _insert(engine, "orphan", "memo.pdf", ["folder-b"], version=1)

    await _run_upgrade(engine)

    async with engine.connect() as conn:
        uids = {row[0] for row in (await conn.execute(sa.text("SELECT document_uid FROM metadata")))}
    assert uids == {"base", "alt", "orphan"}
