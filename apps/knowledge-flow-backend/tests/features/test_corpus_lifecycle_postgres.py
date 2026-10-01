"""Run against an explicitly supplied disposable PostgreSQL instance.

FRED_TEST_POSTGRES_URL=postgresql+psycopg://... uv run pytest <this file>
Each test owns and drops an isolated schema; no application tables are touched.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_core import KeycloakUser
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.tasks.store import TaskStore
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionDelivery
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy, CorpusLifecycle
from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.task_models import TASK_TABLES

pytestmark = pytest.mark.skipif(not os.environ.get("FRED_TEST_POSTGRES_URL"), reason="requires explicitly supplied disposable PostgreSQL")
USER = KeycloakUser(uid="alice", username="alice", roles=[])


@pytest_asyncio.fixture
async def admission():
    url = os.environ["FRED_TEST_POSTGRES_URL"]
    schema = f"corpus_test_{uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(TagRow.__table__.create)
            await connection.run_sync(DocumentMetadataRow.__table__.create)
            await connection.execute(
                insert(TagRow), [dict(tag_id="root", name="Root", path=None, owner_id="team", type="document"), dict(tag_id="child", name="Child", path="Root", owner_id="team", type="document")]
            )
        yield IngestionDelivery(engine, SimpleNamespace(store=TaskStore(engine, TASK_TABLES)), AsyncMock())
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _batch():
    return PipelineDefinition(name="test", files=[FileToProcess(source_tag="uploads", tags=["child"], document_uid="doc", processed_by=USER)])


@pytest.mark.asyncio
async def test_ingestion_commit_wins_over_waiting_deletion(admission, monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    create = admission.tasks.store.create

    async def hold_admission(**kwargs):
        # Real admission holds the root lock at this point.
        entered.set()
        await release.wait()
        return await create(**kwargs)

    monkeypatch.setattr(admission.tasks.store, "create", hold_admission)
    ingest = asyncio.create_task(admission.admit(USER, _batch()))
    await asyncio.wait_for(entered.wait(), 5)

    async def delete():
        async with admission.sessions.begin() as session:
            await CorpusLifecycle.claim_folder_deletion(session, "root", "delete")

    deletion = asyncio.create_task(delete())
    try:
        await asyncio.sleep(0.05)
        assert not deletion.done()
    finally:
        release.set()
    await asyncio.wait_for(ingest, 5)
    with pytest.raises(CorpusBusy, match="Ingestion task"):
        await asyncio.wait_for(deletion, 5)


@pytest.mark.asyncio
async def test_deletion_commit_wins_over_waiting_ingestion(admission):
    async with admission.sessions.begin() as session:
        await CorpusLifecycle.claim_folder_deletion(session, "root", "delete")
        ingest = asyncio.create_task(admission.admit(USER, _batch()))
        await asyncio.sleep(0.05)
        assert not ingest.done()
    with pytest.raises(CorpusBusy, match="being deleted"):
        await asyncio.wait_for(ingest, 5)


@pytest.mark.asyncio
async def test_refile_completed_while_waiting_rejects_stale_admission(admission, monkeypatch):
    from sqlalchemy import update

    async with admission.sessions.begin() as session:
        session.add(TagRow(tag_id="other", name="Other", owner_id="team", type="document"))
        session.add(DocumentMetadataRow(document_uid="doc", kind="corpus", folder_id="child"))
    before_lock = asyncio.Event()
    lock = CorpusLifecycle.lock_folders

    async def observed_lock(session, folder_ids, **kwargs):
        before_lock.set()
        return await lock(session, folder_ids, **kwargs)

    monkeypatch.setattr(CorpusLifecycle, "lock_folders", observed_lock)
    async with admission.sessions.begin() as session:
        await lock(session, {"child"})
        ingest = asyncio.create_task(admission.admit(USER, _batch()))
        await asyncio.wait_for(before_lock.wait(), 5)
        await session.execute(update(DocumentMetadataRow).where(DocumentMetadataRow.document_uid == "doc").values(folder_id="other"))
    with pytest.raises(CorpusBusy, match="membership changed"):
        await asyncio.wait_for(ingest, 5)


@pytest.mark.asyncio
async def test_admission_migration_round_trip_on_postgres(admission, monkeypatch):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[2] / "alembic/versions/b2845a001005_ingestion_folder_admission.py"
    spec = importlib.util.spec_from_file_location("admission_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = admission.sessions.kw["bind"]

    def migrate(connection):
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.downgrade()
        module.upgrade()
        assert connection.execute(text("SELECT count(*) FROM tag")).scalar() == 2

    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    await admission.admit(USER, _batch())


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_atomic_rename_keeps_large_membership_and_rolls_back_conflicts(admission, conflict):
    from sqlalchemy import select, update

    from knowledge_flow_backend.core.stores.tags.base_tag_store import TagAlreadyExistsError
    from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore

    doc = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    async with admission.sessions.begin() as session:
        await session.execute(update(TagRow).values(doc=doc))
        await session.execute(insert(TagRow), [dict(tag_id=f"sub-{i}", name=f"Sub{i}", path="Root/Child", owner_id="team", type="document", doc=doc) for i in range(1001)])
        await session.execute(insert(DocumentMetadataRow), [dict(document_uid=f"doc-{i}", kind="corpus", folder_id=f"sub-{i}") for i in range(1001)])
        if conflict:
            session.add(TagRow(tag_id="taken", name="After", owner_id="team", type="document", doc=doc))
    store = PostgresTagStore(admission.sessions.kw["bind"])
    if conflict:
        with pytest.raises(TagAlreadyExistsError):
            await store.rename_tag("root", name="After", description=None)
    else:
        await store.rename_tag("root", name="After", description=None)
    expected = "Root" if conflict else "After"
    assert (await store.get_tag_by_id("child")).full_path == f"{expected}/Child"
    async with admission.sessions() as session:
        paths = (await session.scalars(select(TagRow.path).where(TagRow.tag_id.startswith("sub-")))).all()
        assert len(paths) == 1001 and set(paths) == {f"{expected}/Child"}
        membership = dict((await session.execute(select(DocumentMetadataRow.document_uid, DocumentMetadataRow.folder_id))).tuples().all())
        assert membership == {f"doc-{i}": f"sub-{i}" for i in range(1001)}


@pytest.mark.asyncio
async def test_child_creation_refuses_parent_renamed_while_waiting(admission, monkeypatch):
    from datetime import datetime, timezone

    from sqlalchemy import update

    from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
    from knowledge_flow_backend.features.tag.structure import Tag, TagType

    async with admission.sessions.begin() as session:
        await session.execute(update(TagRow).values(doc={"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}))
    store = PostgresTagStore(admission.sessions.kw["bind"])
    renaming = asyncio.Event()
    creating = asyncio.Event()
    release = asyncio.Event()
    subtree = CorpusLifecycle.subtree
    lock = CorpusLifecycle.lock_folders

    async def hold_rename(session, folder):
        renaming.set()
        await release.wait()
        return await subtree(session, folder)

    async def observe_creation(session, folder_ids, **kwargs):
        if renaming.is_set():
            creating.set()
        return await lock(session, folder_ids, **kwargs)

    monkeypatch.setattr(CorpusLifecycle, "subtree", hold_rename)
    monkeypatch.setattr(CorpusLifecycle, "lock_folders", observe_creation)
    rename = asyncio.create_task(store.rename_tag("child", name="After", description=None))
    await asyncio.wait_for(renaming.wait(), 5)
    now = datetime.now(timezone.utc)
    child = Tag(id="new", owner_id="team", name="New", path="Root/Child", type=TagType.DOCUMENT, created_at=now, updated_at=now)
    create = asyncio.create_task(store.create_tag(child))
    try:
        await asyncio.wait_for(creating.wait(), 5)
        assert not create.done()
    finally:
        release.set()
    await asyncio.wait_for(rename, 5)
    with pytest.raises(CorpusBusy, match="parent folder was renamed"):
        await asyncio.wait_for(create, 5)
    assert await store.get_by_owner_type_full_path("team", TagType.DOCUMENT, "Root/Child/New") is None
    assert (await store.get_tag_by_id("child")).full_path == "Root/After"
