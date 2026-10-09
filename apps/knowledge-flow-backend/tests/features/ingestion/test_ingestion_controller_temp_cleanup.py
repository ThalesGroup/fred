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

import asyncio
import json
import logging
import pathlib
import threading
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.logs.context import request_log_scope
from fred_core.logs.processors import install_context_capture
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
    )

    events = [event async for event in event_stream]

    assert any(f'"status":"{Status.FINISHED.value}"' in event for event in events)
    assert not workdir.exists()


@pytest.mark.asyncio
async def test_cancelled_upload_keeps_workdir_until_content_store_write_finishes(tmp_path):
    """A client disconnect cannot stop the write thread, so cleanup must wait for it."""
    started = threading.Event()
    release = threading.Event()
    seen_input: list[bool] = []

    class BlockingSaveService(_FakeService):
        def save_input(self, user, metadata, input_dir: pathlib.Path) -> None:
            started.set()
            release.wait(timeout=5)
            seen_input.append(input_dir.exists())

    workdir = tmp_path / "upload-workdir"
    input_dir = workdir / "input"
    input_dir.mkdir(parents=True)
    input_temp_file = input_dir / "sample.csv"
    input_temp_file.write_text("city,amount\nParis,10\n", encoding="utf-8")
    controller = IngestionController.__new__(IngestionController)
    controller.service = BlockingSaveService()
    stream = controller._stream_upload_process(
        preloaded_files=[("sample.csv", input_temp_file)],
        user=KeycloakUser(uid="user-1", username="user1", email="user1@localhost", roles=["admin"]),
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=None,
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
    )

    with request_log_scope(request_id="upload-request", correlation_id="upload-operation") as owner:
        consumer = asyncio.create_task(anext_all(stream))
        await asyncio.to_thread(started.wait, 5)
        consumer.cancel()
        await asyncio.wait([consumer])
        assert consumer.cancelled()
        assert owner.values == {"request_id": "upload-request", "correlation_id": "upload-operation"}
    assert workdir.exists()

    release.set()
    for _ in range(100):
        if not workdir.exists():
            break
        await asyncio.sleep(0.01)
    assert seen_input == [True]
    assert not workdir.exists()


async def anext_all(stream) -> None:
    async for _ in stream:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduled", [False, True])
async def test_upload_batch_and_http_completion_do_not_inherit_final_document(tmp_path, monkeypatch, caplog, scheduled):
    from fred_core.logs.context import bind_operation_context
    from fred_core.logs.http import RequestLoggingFastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.responses import StreamingResponse

    class DistinctDocumentService(_FakeService):
        async def extract_metadata(self, user, file_path, tags, source_tag, profile):
            return SimpleNamespace(document_uid={"first.csv": "doc-a", "second.csv": "doc-b"}[file_path.name], file_type="csv")

    async def process(**kwargs):
        return kwargs["metadata"]

    async def submit_documents(**kwargs):
        files = [SimpleNamespace(document_uid=file.document_uid, task_id=f"task-{index}") for index, file in enumerate(kwargs["files"])]
        return SimpleNamespace(files=files), SimpleNamespace(workflow_id="upload-workflow")

    monkeypatch.setattr("knowledge_flow_backend.features.ingestion.ingestion_controller.push_input_process", process)
    monkeypatch.setattr("knowledge_flow_backend.features.ingestion.ingestion_controller.output_process", process)
    controller = IngestionController.__new__(IngestionController)
    controller.service = DistinctDocumentService()
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY
    paths = []
    for index, name in enumerate(("first.csv", "second.csv")):
        path = tmp_path / str(index) / "input" / name
        path.parent.mkdir(parents=True)
        path.write_text("synthetic", encoding="utf-8")
        paths.append((name, path))
    app = RequestLoggingFastAPI()

    @app.get("/upload")
    async def upload():
        bind_operation_context(document_uid="previous-document", task_id="previous-task")
        return StreamingResponse(
            controller._stream_upload_process(
                preloaded_files=paths,
                user=KeycloakUser(uid="user-1", username="synthetic", roles=[]),
                tags=[],
                source_tag="uploads",
                profile=IngestionProcessingProfile.medium,
                scheduler_task_service=SimpleNamespace(submit_documents=submit_documents) if scheduled else None,
                background_tasks=None,
                kpi=_FakeKpi(),
                kpi_actor=SimpleNamespace(type="human"),
            ),
            media_type="application/x-ndjson",
        )

    install_context_capture()
    with caplog.at_level(logging.INFO):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/upload")
    assert response.status_code == 200
    assert json.loads(response.text.splitlines()[-1])["status"] == Status.SUCCESS.value
    prepared = [record for record in caplog.records if record.getMessage() == "Upload preparation completed"]
    assert {record._fred_snapshot.values["document_uid"] for record in prepared} == {"doc-a", "doc-b"}
    batch = next(record for record in caplog.records if record.getMessage() == "Upload batch completed")
    completed = [record for record in caplog.records if record.name == "http"]
    assert len(completed) == 1
    for record in [batch, completed[0]]:
        assert record._fred_snapshot.values.get("document_uid") is None
        assert record._fred_snapshot.values.get("task_id") is None
        if scheduled:
            assert record._fred_snapshot.values["workflow_id"] == "upload-workflow"


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
        async def extract_metadata(self, user, file_path, tags, source_tag, profile):
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
        scheduler_task_service=None,
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
