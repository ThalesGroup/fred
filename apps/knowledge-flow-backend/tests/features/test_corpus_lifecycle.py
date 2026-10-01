from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fred_core import KeycloakUser
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.tasks.store import TaskStore
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionDelivery
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy, CorpusLifecycle
from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.task_models import TASK_TABLES, KfTaskRunRow

USER = KeycloakUser(uid="alice", username="alice", roles=[])


@pytest_asyncio.fixture
async def admission(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(TagRow.__table__.create)
        await connection.run_sync(DocumentMetadataRow.__table__.create)
        await connection.execute(
            insert(TagRow),
            [
                dict(doc={"created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z"}, tag_id="root", name="Root", path=None, owner_id="team", type="document"),
                dict(doc={"created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z"}, tag_id="child", name="Child", path="Root", owner_id="team", type="document"),
                dict(doc={"created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z"}, tag_id="other", name="Other", path=None, owner_id="team", type="document"),
            ],
        )
    delivery = IngestionDelivery(engine, SimpleNamespace(store=TaskStore(engine, TASK_TABLES)), AsyncMock())
    try:
        yield delivery
    finally:
        await engine.dispose()


def _batch(folder="child"):
    return PipelineDefinition(name="test", files=[FileToProcess(source_tag="uploads", tags=[folder], document_uid="doc", processed_by=USER)])


@pytest.mark.asyncio
async def test_preparation_without_metadata_prevents_deleting_its_parent(admission):
    definition = _batch()
    await admission.admit(USER, definition)
    async with admission.sessions.begin() as session:
        assert await session.get(DocumentMetadataRow, "doc") is None
        with pytest.raises(CorpusBusy, match="Ingestion task"):
            await CorpusLifecycle.claim_folder_deletion(session, "root", "delete")
    async with admission.sessions() as session:
        assert all(row.deletion_task_id is None for row in (await session.scalars(select(TagRow))).all())


@pytest.mark.asyncio
async def test_claim_hides_entire_tree_and_refuses_new_ingestion_without_tasks(admission):
    async with admission.sessions.begin() as session:
        assert await CorpusLifecycle.claim_folder_deletion(session, "root", "delete") == ["child", "root"]
    with pytest.raises(CorpusBusy, match="being deleted"):
        await admission.admit(USER, _batch())
    async with admission.sessions.begin() as session:
        assert (await session.scalars(select(KfTaskRunRow))).all() == []
        # Replay by the same Temporal task keeps the claim; another deletion conflicts.
        assert await CorpusLifecycle.claim_folder_deletion(session, "root", "delete") == ["child", "root"]
        with pytest.raises(CorpusBusy):
            await CorpusLifecycle.claim_folder_deletion(session, "root", "different-delete")
    await admission.admit(USER, _batch("other"))


@pytest.mark.asyncio
async def test_source_refile_reserves_original_and_destination_folders(admission):
    async with admission.sessions.begin() as session:
        session.add(DocumentMetadataRow(document_uid="doc", kind="corpus", folder_id="child"))
    await admission.admit(USER, _batch("other"))
    async with admission.sessions.begin() as session:
        for folder in ["root", "other"]:
            with pytest.raises(CorpusBusy, match="Ingestion task"):
                await CorpusLifecycle.claim_folder_deletion(session, folder, "delete")


@pytest.mark.asyncio
async def test_claimed_tree_is_hidden_before_paging_and_refuses_child_creation(admission):
    from datetime import datetime, timezone

    from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
    from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
    from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess
    from knowledge_flow_backend.features.tag.structure import Tag, TagType

    store = PostgresTagStore(admission.sessions.kw["bind"])
    access = CorpusAccess(AsyncMock(), store)
    async with admission.sessions.begin() as session:
        await CorpusLifecycle.claim_folder_deletion(session, "root", "delete")
    assert [folder.id for folder in await access.list_readable_folders(USER, "team", limit=1)] == ["other"]
    with pytest.raises(TagNotFoundError):
        await access.get_folder(USER, "child")
    with pytest.raises(CorpusBusy):
        await access.get_folder(USER, "child", write=True)
    now = datetime.now(timezone.utc)
    with pytest.raises(CorpusBusy):
        await store.create_tag(Tag(id="new", owner_id="team", name="New", path="Root/Child", type=TagType.DOCUMENT, created_at=now, updated_at=now))
    # Cleanup and quota code still reads retained rows through the internal store.
    assert (await store.get_tag_by_id("child")).deletion_task_id == "delete"
