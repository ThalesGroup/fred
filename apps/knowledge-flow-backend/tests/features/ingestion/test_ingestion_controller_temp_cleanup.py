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

import pathlib
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, Status
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from tests.features.ingestion.test_upload_charges_after_content_store import _FakeSchedulerTaskService


class _FakeKpi:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _FakeService:
    async def extract_metadata(self, user, file_path: pathlib.Path, tags, source_tag, profile, *, apply_versioning=True):
        return SimpleNamespace(document_uid="doc-1", file_type=file_path.suffix.lstrip("."))

    async def apply_versioning(self, metadata):
        return metadata

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

    event_stream = controller._stream_upload_process(
        preloaded_files=[("sample.csv", input_temp_file)],
        user=user,
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=_FakeSchedulerTaskService(),
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
    )

    events = [event async for event in event_stream]

    assert any('"step": "done", "status": "success"' in event for event in events)
    assert not workdir.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"", "empty (0 bytes)"), (b"%PDF-1.4\ntruncated", "PDF could not be read")],
)
async def test_invalid_pdf_upload_stream_explains_failure_without_server_path(tmp_path, content, expected):
    """Exercise the real PDF validator through the progress stream consumed by the UI."""
    import json

    from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor

    class InvalidPdfService(_FakeService):
        async def extract_metadata(self, user, file_path, tags, source_tag, profile, *, apply_versioning=True):
            processor = PdfMarkdownProcessor.__new__(PdfMarkdownProcessor)
            return processor.process_metadata(file_path, tags, source_tag)

    workdir = tmp_path / "upload-workdir"
    input_dir = workdir / "input"
    input_dir.mkdir(parents=True)
    path = input_dir / "document.pdf"
    path.write_bytes(content)
    controller = IngestionController.__new__(IngestionController)
    controller.service = InvalidPdfService()
    stream = controller._stream_upload_process(
        preloaded_files=[(path.name, path)],
        user=KeycloakUser(uid="user-1", username="user1", email="user1@localhost", roles=["admin"]),
        tags=[],
        source_tag="uploads",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=_FakeSchedulerTaskService(),
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
    )
    events = [json.loads(event) async for event in stream]
    failure = next(event for event in events if event.get("error"))
    assert failure["status"] == Status.FAILED.value
    assert failure["filename"] == "document.pdf"
    assert expected in failure["error"]
    assert "download" in failure["error"].lower()
    assert str(tmp_path) not in failure["error"]
    assert "ValueError" not in failure["error"]
    assert "InputValidationError" not in failure["error"]
    assert events[-1]["status"] == Status.FAILED.value
    assert not workdir.exists()


@pytest.mark.asyncio
async def test_scheduler_start_error_reaches_upload_progress(tmp_path):
    import json
    from unittest.mock import AsyncMock

    folder = tmp_path / "upload" / "input"
    folder.mkdir(parents=True)
    path = folder / "sample.csv"
    path.write_text("city\nParis\n")
    controller = IngestionController.__new__(IngestionController)
    controller.service = _FakeService()
    controller._scheduler_backend = lambda: SchedulerBackend.TEMPORAL
    scheduler = _FakeSchedulerTaskService()
    scheduler.deliver_documents = AsyncMock(side_effect=RuntimeError("Ingestion start not confirmed (workflow-id)."))
    events = [
        json.loads(event)
        async for event in controller._stream_upload_process(
            preloaded_files=[(path.name, path)],
            user=KeycloakUser(uid="user", username="user", roles=[]),
            tags=["folder"],
            source_tag="uploads",
            profile=IngestionProcessingProfile.medium,
            scheduler_task_service=scheduler,
            background_tasks=None,
            kpi=_FakeKpi(),
            kpi_actor=SimpleNamespace(type="human"),
        )
    ]
    assert events[-1]["status"] == Status.FAILED.value
    assert "start not confirmed" in events[-1]["error"]
    assert any(event.get("filename") == path.name and event["status"] == Status.FAILED.value for event in events)
    scheduler.deliver_documents.assert_awaited_once()
