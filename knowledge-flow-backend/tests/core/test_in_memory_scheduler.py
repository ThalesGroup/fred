import asyncio
from unittest.mock import Mock

from fastapi import BackgroundTasks
from fred_core import KeycloakUser

from knowledge_flow_backend.features.scheduler import in_memory_scheduler as scheduler_module
from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess, PipelineDefinition


def _build_user() -> KeycloakUser:
    return KeycloakUser(
        uid="test-user",
        username="testuser",
        email="testuser@localhost",
        roles=["admin"],
        groups=["admins"],
    )


def _build_pipeline(user: KeycloakUser) -> PipelineDefinition:
    return PipelineDefinition(
        name="test-pipeline",
        files=[
            FileToProcess(
                source_tag="fred",
                tags=[],
                display_name="sample.csv",
                document_uid="doc-1",
                processed_by=user,
            )
        ],
        max_parallelism=1,
    )


async def _wait_for_workflow_status(
    scheduler: InMemoryScheduler,
    *,
    workflow_id: str,
    expected_status: str,
    timeout_s: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    last_status = None
    while asyncio.get_running_loop().time() < deadline:
        last_status = await scheduler.get_workflow_execution_status(workflow_id)
        if last_status == expected_status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Workflow status never reached {expected_status}. Last status: {last_status}")


def test_in_memory_scheduler_reports_running_then_completed(monkeypatch):
    async def _scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def fake_run_ingestion_pipeline(definition: PipelineDefinition) -> str:
            started.set()
            await release.wait()
            return "success"

        monkeypatch.setattr(scheduler_module, "_run_ingestion_pipeline", fake_run_ingestion_pipeline)

        scheduler = InMemoryScheduler(metadata_service=Mock())
        user = _build_user()
        definition = _build_pipeline(user)
        background_tasks = BackgroundTasks()

        handle = await scheduler.start_document_processing(
            user=user,
            definition=definition,
            background_tasks=background_tasks,
        )

        assert await scheduler.get_workflow_execution_status(handle.workflow_id) == "RUNNING"
        assert await scheduler.get_workflow_last_error(handle.workflow_id) is None

        background_runner = asyncio.create_task(background_tasks())
        await started.wait()

        release.set()
        await background_runner
        await _wait_for_workflow_status(
            scheduler,
            workflow_id=handle.workflow_id,
            expected_status="COMPLETED",
        )
        assert await scheduler.get_workflow_last_error(handle.workflow_id) is None

    asyncio.run(_scenario())


def test_in_memory_scheduler_reports_failed_and_last_error(monkeypatch):
    async def _scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def fake_run_ingestion_pipeline(definition: PipelineDefinition) -> str:
            started.set()
            await release.wait()
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(scheduler_module, "_run_ingestion_pipeline", fake_run_ingestion_pipeline)

        scheduler = InMemoryScheduler(metadata_service=Mock())
        user = _build_user()
        definition = _build_pipeline(user)
        background_tasks = BackgroundTasks()

        handle = await scheduler.start_document_processing(
            user=user,
            definition=definition,
            background_tasks=background_tasks,
        )

        assert await scheduler.get_workflow_execution_status(handle.workflow_id) == "RUNNING"

        background_runner = asyncio.create_task(background_tasks())
        await started.wait()
        release.set()
        await background_runner

        await _wait_for_workflow_status(
            scheduler,
            workflow_id=handle.workflow_id,
            expected_status="FAILED",
        )
        last_error = await scheduler.get_workflow_last_error(handle.workflow_id)
        assert last_error is not None
        assert "RuntimeError: simulated failure" in last_error

    asyncio.run(_scenario())
