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
from knowledge_flow_backend.models.task_models import TASK_TABLES, IngestionSubmissionRow, KfTaskRunRow

USER = KeycloakUser(uid="alice", username="alice", roles=[])


def batch(*uids):
    return PipelineDefinition(name="retry", files=[FileToProcess(source_tag="uploads", document_uid=uid, profile="rich", processed_by=USER) for uid in uids], max_parallelism=2)


@pytest_asyncio.fixture
async def delivery(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'delivery.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    scheduler = SimpleNamespace(start_document_processing=AsyncMock(side_effect=lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)))
    value = IngestionDelivery(engine, SimpleNamespace(store=TaskStore(engine, TASK_TABLES)), scheduler)
    yield value
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_admissions_reserve_document_once(delivery):
    results = await asyncio.gather(delivery.admit(USER, batch("doc"), {}), delivery.admit(USER, batch("doc"), {}), return_exceptions=True)
    assert sum(isinstance(result, IngestionAlreadyActive) for result in results) == 1
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1
        assert await session.scalar(select(func.count()).select_from(IngestionSubmissionRow)) == 1


@pytest.mark.asyncio
async def test_batch_collision_rolls_back_all_new_tasks(delivery):
    await delivery.admit(USER, batch("busy"), {})
    with pytest.raises(IngestionAlreadyActive):
        await delivery.admit(USER, batch("free", "busy"), {})
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1
    await delivery.admit(USER, batch("free"), {})


@pytest.mark.asyncio
async def test_restart_before_delivery_preserves_profile_task_and_execution(delivery):
    definition = batch("doc")
    await delivery.admit(USER, definition, {"doc": "team"})
    run = await delivery.tasks.store.get_run(definition.files[0].task_id)
    assert run.execution_id == definition.workflow_id
    assert run.team_id == "team"
    await delivery.retry_pending()
    sent = delivery.scheduler.start_document_processing.call_args.kwargs["definition"]
    assert sent.files[0].profile == "rich"
    assert sent.files[0].task_id == run.task_id
    assert sent.max_parallelism == 2
    assert sent.workflow_id == run.execution_id
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(IngestionSubmissionRow)) == 0


@pytest.mark.asyncio
async def test_ambiguous_start_keeps_reservation_and_retries_same_execution(delivery):
    definition = batch("doc")
    await delivery.admit(USER, definition, {})
    delivery.scheduler.start_document_processing.side_effect = TimeoutError()
    await delivery.deliver(definition.workflow_id)
    assert (await delivery.tasks.store.get_run(definition.files[0].task_id)).state == "pending"
    with pytest.raises(IngestionAlreadyActive):
        await delivery.admit(USER, batch("doc"), {})
    delivery.scheduler.start_document_processing.side_effect = lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)
    await delivery.retry_pending()
    assert {call.kwargs["definition"].workflow_id for call in delivery.scheduler.start_document_processing.call_args_list} == {definition.workflow_id}


@pytest.mark.asyncio
async def test_terminal_task_allows_new_generation(delivery):
    from datetime import datetime, timezone

    first = batch("doc")
    await delivery.admit(USER, first, {})
    await delivery.deliver(first.workflow_id)
    await delivery.tasks.store.record_event(IngestionTaskEvent(task_id=first.files[0].task_id, state=TaskState.failed, seq=0, timestamp=datetime.now(timezone.utc)))
    second = batch("doc")
    await delivery.admit(USER, second, {})
    assert second.workflow_id != first.workflow_id
    assert second.files[0].task_id != first.files[0].task_id


@pytest.mark.asyncio
async def test_delivery_interruption_retains_the_committed_request(delivery):
    class ProcessStopped(BaseException):
        pass

    definition = batch("doc")
    await delivery.admit(USER, definition, {})
    delivery.scheduler.start_document_processing.side_effect = ProcessStopped()
    with pytest.raises(ProcessStopped):
        await delivery.deliver(definition.workflow_id)
    delivery.scheduler.start_document_processing.side_effect = lambda **kw: WorkflowHandle(workflow_id=kw["definition"].workflow_id)
    await delivery.retry_pending()
    assert delivery.scheduler.start_document_processing.await_count == 2
    assert (await delivery.tasks.store.get_run(definition.files[0].task_id)).execution_id == definition.workflow_id


@pytest.mark.asyncio
async def test_retry_sweep_drains_more_than_one_concurrency_window(delivery):
    for index in range(17):
        await delivery.admit(USER, batch(f"doc-{index}"), {})
    await delivery.retry_pending()
    assert delivery.scheduler.start_document_processing.await_count == 17
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(IngestionSubmissionRow)) == 0


@pytest.mark.asyncio
async def test_internal_precreated_task_is_adopted_once(delivery):
    from fred_core.tasks.models import TaskTarget

    await delivery.tasks.store.create(task_id="existing", kind="ingestion", created_by=USER.uid, target=TaskTarget(type="document", id="doc", label="doc"))
    definition = batch("doc")
    definition.files[0].task_id = "existing"
    await delivery.admit(USER, definition, {})
    assert (await delivery.tasks.store.get_run("existing")).execution_id == definition.workflow_id
    with pytest.raises(IngestionAlreadyActive):
        await delivery.admit(USER, definition, {})
    async with delivery.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KfTaskRunRow)) == 1


@pytest.mark.asyncio
async def test_memory_background_delivery_keeps_payload_until_work_is_complete(delivery):
    from fastapi import BackgroundTasks

    from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler

    scheduler = InMemoryScheduler.__new__(InMemoryScheduler)

    async def run(**kwargs):
        # A separate transaction must remain available while local work executes.
        async with delivery.sessions.begin() as session:
            row = await session.get(KfTaskRunRow, definition.files[0].task_id)
            row.state = "succeeded"
        return WorkflowHandle(workflow_id=definition.workflow_id)

    scheduler.start_document_processing = AsyncMock(side_effect=run)
    delivery.scheduler = scheduler
    definition = batch("doc")
    await delivery.admit(USER, definition, {})
    background = BackgroundTasks()
    await delivery.deliver(definition.workflow_id, background)
    scheduler.start_document_processing.assert_not_awaited()
    async with delivery.sessions() as session:
        assert await session.get(IngestionSubmissionRow, definition.workflow_id) is not None
    await background()
    scheduler.start_document_processing.assert_awaited_once()
    async with delivery.sessions() as session:
        assert await session.get(IngestionSubmissionRow, definition.workflow_id) is None
