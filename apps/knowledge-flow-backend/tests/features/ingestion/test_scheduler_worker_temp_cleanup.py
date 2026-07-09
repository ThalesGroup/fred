import logging
import pathlib
import shutil
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.scheduler.activities import output_process
from knowledge_flow_backend.features.scheduler.push_files_activities import push_input_process
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess


class _TrackedTemporaryDirectory:
    """
    Track that a worker tempdir is removed when the context manager exits.

    Why this exists:
    - Worker cleanup relies on `tempfile.TemporaryDirectory(...)`.
    - These tests need an observable directory under `tmp_path` so they can
      assert the workdir really disappears after the activity completes.

    How to use:
    - Instantiate with a target path.
    - Patch the module-local `tempfile.TemporaryDirectory` factory to return it.
    """

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.exited = False

    def __enter__(self) -> str:
        self.path.mkdir(parents=True, exist_ok=True)
        return str(self.path)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True
        shutil.rmtree(self.path, ignore_errors=True)


class _FakeMetadata:
    def __init__(self, *, document_uid: str, document_name: str) -> None:
        self.document_uid = document_uid
        self.document_name = document_name
        self.processing = SimpleNamespace(stages={})
        self.errors: list[tuple[object, str]] = []

    def set_stage_status(self, stage, status) -> None:
        self.processing.stages[stage] = status

    def mark_stage_done(self, stage) -> None:
        self.processing.stages[stage] = "DONE"

    def mark_stage_error(self, stage, error_message: str) -> None:
        self.errors.append((stage, error_message))


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="test-user",
        username="testuser",
        email="testuser@localhost",
        roles=["admin"],
    )


@pytest.mark.asyncio
async def test_push_input_process_cleans_worker_tempdir(tmp_path, monkeypatch):
    """
    Ensure push-input workers remove their temporary workdir after processing.

    Why this exists:
    - Push ingestion workers materialize input/output directories under a
      temporary worker folder.
    - Once output persistence completes, that folder should not remain on disk.

    How to use:
    - Patch the worker tempdir factory, run `push_input_process(...)`, then
      assert the tracked folder no longer exists.
    """
    tracked_dir = _TrackedTemporaryDirectory(tmp_path / "worker-push-temp")
    input_file = tmp_path / "sample.csv"
    input_file.write_text("city,amount\nParis,10\n", encoding="utf-8")
    metadata = _FakeMetadata(document_uid="doc-push", document_name="sample.csv")

    class _FakeService:
        def __init__(self) -> None:
            self.context = SimpleNamespace(is_tabular_file=lambda _: True, is_spreadsheet_file=lambda _: False)

        async def save_metadata(self, user, metadata) -> None:
            return None

        def process_input(self, user, input_path, output_dir, metadata, profile) -> None:
            output_dir.mkdir(parents=True, exist_ok=True)

        def save_output(self, user, metadata, output_dir) -> None:
            return None

    async def _fake_to_thread_with_heartbeat(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_service.get_ingestion_service",
        lambda: _FakeService(),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.push_files_activities.to_thread_with_heartbeat",
        _fake_to_thread_with_heartbeat,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.push_files_activities.emit_temporal_activity_result_kpis",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.push_files_activities.activity.logger",
        logging.getLogger("test-push-input-process"),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.push_files_activities.tempfile.TemporaryDirectory",
        lambda prefix="": tracked_dir,
    )

    result = await push_input_process(
        user=_user(),
        metadata=metadata,
        input_file=str(input_file),
        profile=IngestionProcessingProfile.medium,
    )

    assert result is metadata
    assert tracked_dir.exited is True
    assert not tracked_dir.path.exists()


@pytest.mark.asyncio
async def test_output_process_cleans_worker_tempdir(tmp_path, monkeypatch):
    """
    Ensure output workers remove their temporary workdir after tabular processing.

    Why this exists:
    - Output workers restore persisted document content into a temporary local
      folder before running processors.
    - That restored worker folder should disappear once the activity finishes.

    How to use:
    - Patch the worker tempdir factory, run `output_process(...)`, then assert
      the tracked folder no longer exists.
    """
    tracked_dir = _TrackedTemporaryDirectory(tmp_path / "worker-output-temp")
    metadata = _FakeMetadata(document_uid="doc-output", document_name="sample.csv")
    user = _user()
    file = FileToProcess(
        source_tag="fred",
        tags=[],
        display_name="sample.csv",
        document_uid="doc-output",
        profile=IngestionProcessingProfile.medium,
        processed_by=user,
    )

    class _FakeService:
        async def save_metadata(self, user, metadata) -> None:
            return None

        def get_local_copy(self, user, metadata, working_dir) -> pathlib.Path:
            input_dir = working_dir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            (input_dir / metadata.document_name).write_text("city,amount\nParis,10\n", encoding="utf-8")
            return working_dir

        def process_output(self, user, file_name_for_processing, output_dir, metadata, profile):
            return metadata

    fake_app_context = SimpleNamespace(is_tabular_file=lambda _: True, is_spreadsheet_file=lambda _: False)

    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_service.get_ingestion_service",
        lambda: _FakeService(),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.application_context.ApplicationContext.get_instance",
        lambda: fake_app_context,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.activities.emit_temporal_activity_result_kpis",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.activities.activity.logger",
        logging.getLogger("test-output-process"),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.scheduler.activities.tempfile.TemporaryDirectory",
        lambda prefix="": tracked_dir,
    )

    result = await output_process(file=file, metadata=metadata, accept_memory_storage=True)

    assert result is metadata
    assert tracked_dir.exited is True
    assert not tracked_dir.path.exists()
