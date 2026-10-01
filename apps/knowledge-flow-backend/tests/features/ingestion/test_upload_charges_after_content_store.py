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

"""Storage usage must only ever count bytes that reached the content store.

`save_metadata` is what charges the quota (`MetadataService.
_persist_metadata_and_follow_up` -> `_adjust_team_storage`), and `save_input` is
what writes the raw file to the content store (S3/GCS/filesystem). The upload
route already calls them in that order, so an upload that dies before its bytes
land is never charged — but nothing enforced the order, and swapping the two
lines is an easy, invisible mistake: every existing test would still pass while
users started paying quota for files that were never stored.

These pin the ordering itself, driving the real `_stream_upload_process`, so the
invariant fails loudly instead of silently.

Not covered here: an ingestion that fails *after* `save_input` keeps both the
document and the charge, which is correct — the raw bytes really are in the
content store. A user-requested cancel is a separate path with its own coverage
(`delete_cancelled_document`, #2315) since it erases the document and releases
the quota with it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _RecordingService:
    """Records the order of the two calls the invariant is about."""

    def __init__(self, *, save_input_raises: bool = False) -> None:
        self.calls: list[str] = []
        self._save_input_raises = save_input_raises

    async def extract_metadata(self, user, file_path, tags, source_tag, profile, *, apply_versioning=True):
        self.calls.append("extract_metadata")
        return SimpleNamespace(document_uid="doc-1", document_name=file_path.name, file_type=file_path.suffix.lstrip("."))

    async def apply_versioning(self, metadata):
        return metadata

    def save_input(self, user, metadata, input_dir) -> None:
        self.calls.append("save_input")
        if self._save_input_raises:
            raise RuntimeError("content store unreachable")

    async def save_metadata(self, user, metadata) -> None:
        self.calls.append("save_metadata")


class _FakeKpi:
    def emit(self, **kwargs) -> None:
        return None


class _FakeTaskService:
    async def start(self, req, *, created_by, team_id=None, target=None):
        return SimpleNamespace(task_id="task-1")

    async def bind_execution(self, task_id: str, *, execution_id: str) -> None:
        return None

    async def fail_task(self, task_id: str, message: str) -> bool:
        return True


class _FakeSchedulerTaskService:
    async def admit_documents(self, *, user, pipeline_name, files, upload_only=False):
        for file in files:
            file.task_id = "task-1"
        return SimpleNamespace(files=files)

    async def deliver_documents(self, definition, background_tasks=None):
        return SimpleNamespace(workflow_id="wf-1")


def _user() -> KeycloakUser:
    return KeycloakUser(uid="bob", username="bob", email=None, roles=[])


async def _drain(service: _RecordingService, monkeypatch: pytest.MonkeyPatch, tmp_path) -> list[str]:
    controller = IngestionController.__new__(IngestionController)
    controller.service = service
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY

    async def _fake_resolve_tag_owners(tags, user):
        return {"team-a"}, set()

    controller._resolve_tag_owners = _fake_resolve_tag_owners  # type: ignore[method-assign]

    input_dir = tmp_path / "upload-workdir" / "input"
    input_dir.mkdir(parents=True)
    input_temp_file = input_dir / "sample.pdf"
    input_temp_file.write_bytes(b"%PDF-1.4")

    fake_ctx = SimpleNamespace(get_task_service=_FakeTaskService)
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: fake_ctx))

    events: list[str] = []
    async for event in controller._stream_upload_process(
        preloaded_files=[("sample.pdf", input_temp_file)],
        user=_user(),
        tags=["tag-a"],
        source_tag="fred",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=_FakeSchedulerTaskService(),
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_content_store_write_precedes_the_quota_charge(monkeypatch, tmp_path) -> None:
    service = _RecordingService()

    await _drain(service, monkeypatch, tmp_path)

    assert service.calls.index("save_input") < service.calls.index("save_metadata"), f"quota is charged before the file reaches the content store: {service.calls}"


@pytest.mark.asyncio
async def test_a_content_store_failure_never_charges_the_quota(monkeypatch, tmp_path) -> None:
    service = _RecordingService(save_input_raises=True)

    events = await _drain(service, monkeypatch, tmp_path)

    assert "save_metadata" not in service.calls, "an upload whose bytes never reached the content store was charged anyway"
    assert any("failed" in event for event in events), "the failed upload was not reported to the client"


@pytest.mark.asyncio
async def test_batch_keeps_sequential_versions_after_admission(tmp_path):
    from unittest.mock import AsyncMock

    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    stored = []
    versioning = IngestionService.__new__(IngestionService)
    versioning.metadata_service = SimpleNamespace(metadata_store=SimpleNamespace(get_metadata_in_tag=AsyncMock(side_effect=lambda folder: list(stored))))

    async def extract(user, *, file_path, apply_versioning, **kwargs):
        assert apply_versioning is False
        return SimpleNamespace(
            document_uid=file_path.parent.parent.name,
            identity=SimpleNamespace(document_name="report.pdf", canonical_name=None, version=None),
            tags=SimpleNamespace(tag_ids=["folder"]),
        )

    async def save(user, *, metadata):
        stored.append(metadata)

    controller = IngestionController.__new__(IngestionController)
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY
    controller.service = SimpleNamespace(extract_metadata=extract, apply_versioning=versioning.apply_versioning, save_input=lambda *args, **kwargs: None, save_metadata=save)
    preloaded = []
    for index in range(2):
        path = tmp_path / f"upload-{index}" / "input" / "report.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(str(index).encode())
        preloaded.append((path.name, path))
    events = [
        event
        async for event in controller._stream_upload_process(
            preloaded_files=preloaded,
            user=_user(),
            tags=["folder"],
            source_tag="fred",
            profile=IngestionProcessingProfile.medium,
            scheduler_task_service=_FakeSchedulerTaskService(),
            background_tasks=None,
            kpi=_FakeKpi(),
            kpi_actor=SimpleNamespace(type="human"),
        )
    ]
    assert [metadata.identity.version for metadata in stored] == [0, 1]
    assert '"status": "success"' in events[-1]


@pytest.mark.asyncio
async def test_versioning_requires_folder_without_global_inventory():
    from unittest.mock import AsyncMock

    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    service = IngestionService.__new__(IngestionService)
    store = SimpleNamespace(get_metadata_in_tag=AsyncMock(), get_all_metadata=AsyncMock())
    service.metadata_service = SimpleNamespace(metadata_store=store)
    metadata = SimpleNamespace(identity=SimpleNamespace(document_name="report.pdf"), tags=SimpleNamespace(tag_ids=[]))
    with pytest.raises(ValueError, match="destination folder"):
        await service.apply_versioning(metadata)
    store.get_metadata_in_tag.assert_not_called()
    store.get_all_metadata.assert_not_called()
