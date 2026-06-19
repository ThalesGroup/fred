import asyncio
from unittest.mock import AsyncMock

from fred_core import KeycloakUser

from knowledge_flow_backend.features.scheduler import in_memory_scheduler as scheduler_module
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
                display_name="sample.md",
                document_uid="doc-1",
                task_id="task-1",
                processed_by=user,
            )
        ],
        max_parallelism=1,
    )


def test_run_push_ingestion_pipeline_emits_task_events(monkeypatch):
    async def _scenario() -> None:
        user = _build_user()
        definition = _build_pipeline(user)
        metadata = AsyncMock()
        metadata.document_uid = "doc-1"

        emitted: list[dict[str, object]] = []

        async def fake_emit_ingestion_task_event(**kwargs):
            emitted.append(kwargs)

        monkeypatch.setattr(
            scheduler_module,
            "get_push_file_metadata",
            AsyncMock(return_value=metadata),
        )
        monkeypatch.setattr(
            scheduler_module,
            "push_input_process",
            AsyncMock(return_value=metadata),
        )
        monkeypatch.setattr(
            scheduler_module,
            "output_process",
            AsyncMock(return_value=metadata),
        )
        monkeypatch.setattr(
            scheduler_module,
            "emit_ingestion_task_event",
            fake_emit_ingestion_task_event,
        )

        result = await scheduler_module._run_push_ingestion_pipeline(definition)

        assert result == "success"
        assert [event["state"] for event in emitted] == ["running", "running", "succeeded"]
        assert [event["step"] for event in emitted] == ["uploading", "processing", "done"]
        assert emitted[-1]["progress"] == 1.0
        assert emitted[-1]["document_uid"] == "doc-1"

    asyncio.run(_scenario())


def test_run_push_ingestion_pipeline_emits_failed_task_event(monkeypatch):
    async def _scenario() -> None:
        user = _build_user()
        definition = _build_pipeline(user)
        metadata = AsyncMock()
        metadata.document_uid = "doc-1"

        emitted: list[dict[str, object]] = []

        async def fake_emit_ingestion_task_event(**kwargs):
            emitted.append(kwargs)

        monkeypatch.setattr(
            scheduler_module,
            "get_push_file_metadata",
            AsyncMock(return_value=metadata),
        )
        monkeypatch.setattr(
            scheduler_module,
            "push_input_process",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(
            scheduler_module,
            "emit_ingestion_task_event",
            fake_emit_ingestion_task_event,
        )

        try:
            await scheduler_module._run_push_ingestion_pipeline(definition)
        except RuntimeError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("Expected RuntimeError from push_input_process")

        assert [event["state"] for event in emitted] == ["running", "running", "failed"]
        assert emitted[-1]["error"] == "boom"
        assert emitted[-1]["failed"] == 1

    asyncio.run(_scenario())
