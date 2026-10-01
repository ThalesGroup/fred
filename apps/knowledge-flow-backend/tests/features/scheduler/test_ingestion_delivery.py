import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fred_core import KeycloakUser
from fred_core.tasks.models import IngestionTaskEvent, TaskState
from fred_core.tasks.store import TaskStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.scheduler.base_scheduler import WorkflowHandle
from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionAlreadyActive, IngestionDelivery
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition
from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.task_models import TASK_TABLES, KfTaskRunRow

USER = KeycloakUser(uid="alice", username="alice", roles=[])


def batch(*uids):
    return PipelineDefinition(name="retry", files=[FileToProcess(source_tag="uploads", tags=["folder"], document_uid=uid, profile="rich", processed_by=USER) for uid in uids], max_parallelism=2)


@pytest_asyncio.fixture
async def delivery(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'delivery.db'}")
    from fred_core.documents.document_models import DocumentMetadataRow
    from fred_core.documents.tag_models import TagRow
    from sqlalchemy import insert

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(TagRow.__table__.create)
        await connection.run_sync(DocumentMetadataRow.__table__.create)
        await connection.execute(insert(TagRow).values(tag_id="folder", name="folder", owner_id="team", type="document"))
    scheduler = SimpleNamespace(start_document_processing=AsyncMock(side_effect=lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)))
    value = IngestionDelivery(engine, SimpleNamespace(store=TaskStore(engine, TASK_TABLES)), scheduler)
    yield value
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_admissions_reserve_document_once(delivery):
    results = await asyncio.gather(delivery.admit(USER, batch("doc")), delivery.admit(USER, batch("doc")), return_exceptions=True)
    assert sum(isinstance(result, IngestionAlreadyActive) for result in results) == 1
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1


@pytest.mark.asyncio
async def test_batch_collision_rolls_back_all_new_tasks(delivery):
    await delivery.admit(USER, batch("busy"))
    with pytest.raises(IngestionAlreadyActive):
        await delivery.admit(USER, batch("free", "busy"))
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1
    await delivery.admit(USER, batch("free"))


@pytest.mark.asyncio
async def test_direct_delivery_preserves_profile_task_and_execution(delivery):
    definition = batch("doc")
    await delivery.admit(USER, definition)
    run = await delivery.tasks.store.get_run(definition.files[0].task_id)
    handle = await delivery.deliver(definition)
    sent = delivery.scheduler.start_document_processing.call_args.kwargs["definition"]
    assert sent.files[0].profile == "rich"
    assert sent.files[0].task_id == run.task_id
    assert sent.max_parallelism == 2
    assert handle.workflow_id == run.execution_id
    assert run.team_id == "team"
    assert run.folder_id == "folder"
    delivery.scheduler.start_document_processing.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError("unavailable")])
async def test_start_error_is_explicit_without_redelivery_or_false_terminal_state(delivery, error):
    definition = batch("doc")
    await delivery.admit(USER, definition)
    delivery.scheduler.start_document_processing.side_effect = error
    with pytest.raises(RuntimeError, match="Ingestion start not confirmed") as caught:
        await delivery.deliver(definition)
    assert caught.value.__cause__ is error
    delivery.scheduler.start_document_processing.assert_awaited_once()
    run = await delivery.tasks.store.get_run(definition.files[0].task_id)
    assert run.state == "pending"
    assert run.execution_id == definition.workflow_id
    with pytest.raises(IngestionAlreadyActive):
        await delivery.admit(USER, batch("doc"))


@pytest.mark.asyncio
async def test_terminal_task_allows_new_generation(delivery):
    from datetime import datetime, timezone

    first = batch("doc")
    await delivery.admit(USER, first)
    await delivery.deliver(first)
    await delivery.tasks.store.record_event(IngestionTaskEvent(task_id=first.files[0].task_id, state=TaskState.failed, seq=0, timestamp=datetime.now(timezone.utc)))
    second = batch("doc")
    await delivery.admit(USER, second)
    assert second.workflow_id != first.workflow_id
    assert second.files[0].task_id != first.files[0].task_id


@pytest.mark.asyncio
async def test_admission_rejects_precreated_task(delivery):
    definition = batch("doc")
    definition.files[0].task_id = "existing"
    with pytest.raises(ValueError, match="creates its own tasks"):
        await delivery.admit(USER, definition)
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("folder_ids", [[], ["one", "two"]])
async def test_admission_requires_one_folder_before_recording_tasks(delivery, folder_ids):
    definition = batch("doc")
    definition.files[0].tags = folder_ids
    with pytest.raises(ValueError, match="exactly one destination folder"):
        await delivery.admit(USER, definition)
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 0


@pytest.mark.asyncio
async def test_memory_scheduler_owns_background_execution(delivery):
    from fastapi import BackgroundTasks

    from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler

    scheduler = InMemoryScheduler.__new__(InMemoryScheduler)
    scheduler._register_workflow = lambda user, definition: WorkflowHandle(workflow_id=definition.workflow_id)
    scheduler._set_workflow_state = lambda **kwargs: None
    scheduler._run_pipeline_with_status_tracking = AsyncMock()
    delivery.scheduler = scheduler
    definition = batch("doc")
    await delivery.admit(USER, definition)
    background = BackgroundTasks()
    await delivery.deliver(definition, background)
    scheduler._run_pipeline_with_status_tracking.assert_not_awaited()
    await background()
    scheduler._run_pipeline_with_status_tracking.assert_awaited_once_with(definition.workflow_id, definition)


@pytest.mark.asyncio
@pytest.mark.parametrize("upload_only", [False, True])
async def test_upload_batch_with_busy_tenth_document_writes_nothing(delivery, tmp_path, upload_only):
    import json

    from fred_core.scheduler import SchedulerBackend

    from knowledge_flow_backend.common.structures import IngestionProcessingProfile
    from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController

    existing = batch("doc-9")
    await delivery.admit(USER, existing)
    before = await delivery.tasks.store.get_run(existing.files[0].task_id)
    controller = IngestionController.__new__(IngestionController)
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY
    controller.service = SimpleNamespace(
        extract_metadata=AsyncMock(side_effect=lambda user, **kw: SimpleNamespace(document_uid=kw["file_path"].stem)),
        save_input=AsyncMock(),
        save_metadata=AsyncMock(),
    )
    preloaded = []
    for index in range(10):
        path = tmp_path / f"upload-{index}" / "input" / f"doc-{index}.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"local upload")
        preloaded.append((path.name, path))

    async def admit_documents(*, user, pipeline_name, files, upload_only=False):
        definition = batch(*(file.document_uid for file in files))
        await delivery.admit(user, definition, upload_only=upload_only)
        return definition

    scheduler = SimpleNamespace(admit_documents=admit_documents, deliver_documents=AsyncMock())
    events = [
        json.loads(event)
        async for event in controller._stream_upload_process(
            preloaded_files=preloaded,
            user=USER,
            tags=["folder"],
            source_tag="uploads",
            profile=IngestionProcessingProfile.medium,
            scheduler_task_service=scheduler,
            background_tasks=None,
            kpi=SimpleNamespace(emit=lambda **kw: None),
            kpi_actor=None,
            upload_only=upload_only,
        )
    ]

    controller.service.save_input.assert_not_called()
    controller.service.save_metadata.assert_not_called()
    scheduler.deliver_documents.assert_not_called()
    assert len([event for event in events if event.get("filename") and event["status"] == "failed"]) == 10
    assert events[-1]["status"] == "failed"
    assert all(not path.parent.parent.exists() for _, path in preloaded)
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1
    after = await delivery.tasks.store.get_run(existing.files[0].task_id)
    assert {column.name: getattr(after, column.name) for column in KfTaskRunRow.__table__.columns} == {column.name: getattr(before, column.name) for column in KfTaskRunRow.__table__.columns}


@pytest.mark.asyncio
async def test_upload_only_completes_reservation_without_workflow(delivery, tmp_path, monkeypatch):
    import json
    from unittest.mock import Mock

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.common.structures import IngestionProcessingProfile
    from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController

    path = tmp_path / "upload" / "input" / "report.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"local file")
    metadata = SimpleNamespace(document_uid="doc", file_type="pdf")
    controller = IngestionController.__new__(IngestionController)
    controller.service = SimpleNamespace(extract_metadata=AsyncMock(return_value=metadata), apply_versioning=AsyncMock(return_value=metadata), save_input=Mock(), save_metadata=AsyncMock())
    tasks = SimpleNamespace(record=delivery.tasks.store.record_event)
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: SimpleNamespace(get_task_service=lambda: tasks)))
    definition = batch("doc")

    async def admit_documents(**kwargs):
        assert kwargs["upload_only"] is True
        await delivery.admit(USER, definition, upload_only=True)
        return definition

    scheduler = SimpleNamespace(admit_documents=admit_documents, deliver_documents=AsyncMock())
    events = [
        json.loads(event)
        async for event in controller._stream_upload_process(
            preloaded_files=[(path.name, path)],
            user=USER,
            tags=["folder"],
            source_tag="uploads",
            profile=IngestionProcessingProfile.medium,
            scheduler_task_service=scheduler,
            background_tasks=None,
            kpi=SimpleNamespace(emit=lambda **kw: None),
            kpi_actor=None,
            upload_only=True,
        )
    ]
    assert events[-1]["status"] == "success"
    assert any(event["status"] == "finished" for event in events)
    assert not any(event.get("task_id") for event in events)
    scheduler.deliver_documents.assert_not_called()
    delivery.scheduler.start_document_processing.assert_not_called()
    run = await delivery.tasks.store.get_run(definition.files[0].task_id)
    assert run.state == "succeeded"
    assert run.execution_id is None
    assert not path.parent.parent.exists()
    await delivery.admit(USER, batch("doc"))


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 1001, 5001])
async def test_batch_admission_does_not_issue_sql_per_document(delivery, count):
    from sqlalchemy import event

    statements = []
    engine = delivery.sessions.kw["bind"]

    def count_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        await delivery.admit(USER, batch(*(f"bulk-{index}" for index in range(count))))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
    assert len(statements) <= 6
    assert sum(statement.startswith("INSERT") for statement in statements) == 1
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == count
