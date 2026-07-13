import pathlib
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, Status
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _FakeKpi:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _FakeService:
    async def extract_metadata(self, user, file_path: pathlib.Path, tags, source_tag, profile):
        return SimpleNamespace(document_uid="doc-1", file_type=file_path.suffix.lstrip("."))

    def save_input(self, user, metadata, input_dir: pathlib.Path) -> None:
        assert input_dir.exists()

    async def save_metadata(self, user, metadata) -> None:
        return None


@pytest.mark.asyncio
async def test_stream_upload_process_cleans_preloaded_upload_workdir(tmp_path, monkeypatch):
    """
    Ensure the API-side upload workdir is deleted once synchronous ingestion completes.

    Why this exists:
    - `/upload-process-documents` persists the upload into shared content storage,
      so its temporary API-side copy should not remain under `/tmp` after the file
      finishes processing.

    How to use:
    - Build one fake preloaded upload path, consume `_stream_upload_process(...)`,
      then assert the workdir has been removed.
    """
    workdir = tmp_path / "upload-workdir"
    input_dir = workdir / "input"
    input_dir.mkdir(parents=True)
    input_temp_file = input_dir / "sample.csv"
    input_temp_file.write_text("city,amount\nParis,10\n", encoding="utf-8")

    controller = IngestionController.__new__(IngestionController)
    controller.service = _FakeService()
    controller.scheduler_task_service = None
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY
    user = KeycloakUser(
        uid="user-1",
        username="user1",
        email="user1@localhost",
        roles=["admin"],
    )

    async def _fake_push_input_process(*args, **kwargs):
        return kwargs["metadata"]

    async def _fake_output_process(*args, **kwargs):
        return kwargs["metadata"]

    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.push_input_process",
        _fake_push_input_process,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.output_process",
        _fake_output_process,
    )

    event_stream = controller._stream_upload_process(
        preloaded_files=[("sample.csv", input_temp_file)],
        user=user,
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=None,
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
        timer_dims={},
    )

    events = [event async for event in event_stream]

    assert any(f'"status":"{Status.FINISHED.value}"' in event for event in events)
    assert not workdir.exists()
