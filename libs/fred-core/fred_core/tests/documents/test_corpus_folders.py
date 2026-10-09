# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.documents.corpus_folder_models import CorpusFolderRow
from fred_core.documents.corpus_folder_store import CorpusFolderStore
from fred_core.sql.alembic_env import autogenerate_diffs
from fred_core.teams.space_models import SpaceRow
from fred_core.users.user_models import UserRow


_PATH = (
    Path(__file__).parents[5]
    / "apps/knowledge-flow-backend/alembic/versions/ef54a72b19d0_add_corpus_folders.py"
)
_SPEC = spec_from_file_location("corpus_folder_migration", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
migration = module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)


@pytest_asyncio.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
async def database(request, tmp_path):
    schema = f"folder_test_{uuid4().hex}"
    url = sa.engine.make_url(f"sqlite+aiosqlite:///{tmp_path / 'folders.db'}")
    options = {}
    if request.param == "postgresql":
        configured = os.environ.get("FRED_SPACE_TEST_POSTGRES_URL")
        if not configured:
            pytest.skip(
                "Set FRED_SPACE_TEST_POSTGRES_URL for isolated PostgreSQL checks"
            )
        url = sa.engine.make_url(configured).set(drivername="postgresql+asyncpg")
        options = {"server_settings": {"search_path": schema}}
    engine = create_async_engine(url, connect_args=options)
    if request.param == "sqlite":

        @sa.event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys = ON")

    metadata = sa.MetaData()
    for model in (UserRow, SpaceRow, CorpusFolderRow):
        model.__table__.to_metadata(metadata)

    def install(connection):
        metadata.create_all(
            connection, tables=[metadata.tables["users"], metadata.tables["space"]]
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    try:
        async with engine.begin() as connection:
            if request.param == "postgresql":
                await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(install)
            await connection.execute(
                sa.insert(SpaceRow),
                [dict(id=i, kind="organization", name=i) for i in ("org-a", "org-b")],
            )
        yield engine, metadata
    finally:
        if request.param == "postgresql":
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_folder_migration_matches_model_and_downgrades(database):
    engine, metadata = database
    async with engine.begin() as connection:
        assert (
            await connection.run_sync(
                lambda c: autogenerate_diffs(c, metadata, {"corpus_folder"})
            )
            == []
        )

        def downgrade(c):
            with Operations.context(MigrationContext.configure(c)):
                migration.downgrade()
            assert not sa.inspect(c).has_table("corpus_folder")

        await connection.run_sync(downgrade)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"space_id": "missing"},
        {"parent_id": "missing"},
        {"parent_id": "invalid"},
        {"parent_id": "foreign"},
        {"name": ""},
        {"name": " padded "},
        {"name": "a/b"},
        {"name": "a\\b"},
        {"name": "Root"},
        {"parent_id": "root", "name": "Child"},
        {"parent_id": "root", "synchronized_by": "git:source"},
        {"parent_id": "root", "source_version": "revision"},
    ],
)
async def test_invalid_folder_structure_is_rejected_by_sql(database, fields):
    engine, _ = database
    store = CorpusFolderStore(engine)
    await store.create("root", "org-a", "Root")
    await store.create("foreign", "org-b", "Root")
    await store.create("child", "org-a", "Child", parent_id="root")
    with pytest.raises(sa.exc.IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                sa.insert(CorpusFolderRow).values(
                    {"id": "invalid", "space_id": "org-a", "name": "New", **fields}
                )
            )


@pytest.mark.asyncio
async def test_listing_is_paged_and_scoped_without_document_ids(database):
    engine, _ = database
    store = CorpusFolderStore(engine)
    for space in ("org-a", "org-b"):
        await store.create(space + "-root", space, "Root")
    await store.create("child-a", "org-a", "Same", parent_id="org-a-root")
    await store.create("child-b", "org-b", "Same", parent_id="org-b-root")
    statements = []

    @sa.event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    folders = await store.list_children(("org-a",), "org-a-root", limit=1)
    assert [folder.id for folder in folders] == ["child-a"]
    assert len(statements) == 1
    assert "item_ids" not in folders[0].model_dump()
    assert await store.list_children(("org-a",), "org-a-root", limit=1, offset=1) == []
    assert await store.list_children(("org-a",), "org-b-root", limit=1) == []
    assert await store.list_children((), None, limit=1) == []


@pytest.mark.asyncio
async def test_rename_preserves_identity_parent_and_space(database):
    engine, _ = database
    store = CorpusFolderStore(engine)
    await store.create("root", "org-a", "Root")
    before = await store.create("child", "org-a", "Child", parent_id="root")
    after = await store.update("child", " Renamed ", "Description")
    assert after is not None
    assert (after.id, after.space_id, after.parent_id) == (
        before.id,
        before.space_id,
        before.parent_id,
    )
    assert after.name == "Renamed"
    assert after.description == "Description"
    assert await store.get("child") == after
    assert await store.get("missing") is None
    with pytest.raises(sa.exc.IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                sa.delete(CorpusFolderRow).where(CorpusFolderRow.id == "root")
            )
