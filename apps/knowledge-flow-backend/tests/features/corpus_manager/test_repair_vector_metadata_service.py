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

"""`CorpusManagerService.repair_vector_metadata` (#2234, 3a) error handling:
a `task_run` row is created (state `pending`) *before* the Temporal workflow is
started. If starting the workflow itself fails, that row must never be left
pending with no execution behind it -- `fail_task` must be called with the
real error, and the original exception must still propagate to the caller
(not be masked by a `fail_task`-only success). This exercises the real
`repair_vector_metadata` method directly, not through FastAPI/TestClient --
`test_corpus_manager_authz.py` covers the HTTP/authz layer with this method
stubbed out.
"""

from __future__ import annotations

import pytest

from knowledge_flow_backend.features.corpus_manager import corpus_manager_service as corpus_service_module
from knowledge_flow_backend.features.corpus_manager.corpus_manager_service import (
    CorpusManagerService,
    RepairVectorMetadataRequestV1,
)


class _FakeUser:
    uid = "alice"


class _FakeTaskService:
    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.failed: list[tuple[str, str]] = []
        self.bound: list[tuple[str, str]] = []

    async def start(self, start_req, *, created_by, team_id, target):
        self.started.append((created_by, team_id, target))
        return type("Resp", (), {"task_id": "task-1"})()

    async def fail_task(self, task_id: str, message: str) -> bool:
        self.failed.append((task_id, message))
        return True

    async def bind_execution(self, task_id: str, *, execution_id: str) -> None:
        self.bound.append((task_id, execution_id))


class _FakeAppContext:
    def __init__(self, task_service: _FakeTaskService) -> None:
        self._task_service = task_service

    def get_task_service(self):
        return self._task_service


class _RaisingIngestionTaskService:
    """`start_repair_vector_metadata` fails as if the Temporal frontend were
    unreachable -- the scenario `fail_task` exists for."""

    async def start_repair_vector_metadata(self, *, source_tag: str, task_id: str):
        raise RuntimeError("Temporal frontend unreachable")


class _SucceedingIngestionTaskService:
    async def start_repair_vector_metadata(self, *, source_tag: str, task_id: str):
        return type("Handle", (), {"workflow_id": "wf-1"})()


def _patch_app_context(monkeypatch, task_service: _FakeTaskService) -> None:
    fake_ctx = _FakeAppContext(task_service)
    monkeypatch.setattr(
        corpus_service_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: fake_ctx),
    )


@pytest.mark.asyncio
async def test_repair_vector_metadata_fails_the_task_when_temporal_submission_raises(monkeypatch) -> None:
    task_service = _FakeTaskService()
    _patch_app_context(monkeypatch, task_service)
    service = CorpusManagerService(ingestion_task_service=_RaisingIngestionTaskService())
    req = RepairVectorMetadataRequestV1(source_tag="fred", team_id="team-a")

    with pytest.raises(RuntimeError, match="Temporal frontend unreachable"):
        await service.repair_vector_metadata(req, _FakeUser())

    # The task_run row created by task_svc.start() must be driven to `failed`
    # with a bounded, explicit message -- never left pending with no workflow.
    assert task_service.failed == [("task-1", "Temporal frontend unreachable")]
    # bind_execution must never be attempted -- there is no workflow to bind to.
    assert task_service.bound == []


@pytest.mark.asyncio
async def test_repair_vector_metadata_truncates_an_unbounded_error_message(monkeypatch) -> None:
    task_service = _FakeTaskService()
    _patch_app_context(monkeypatch, task_service)

    class _RaisingWithHugeMessage:
        async def start_repair_vector_metadata(self, *, source_tag: str, task_id: str):
            raise RuntimeError("x" * 10_000)

    service = CorpusManagerService(ingestion_task_service=_RaisingWithHugeMessage())
    req = RepairVectorMetadataRequestV1(source_tag="fred", team_id="team-a")

    with pytest.raises(RuntimeError):
        await service.repair_vector_metadata(req, _FakeUser())

    assert len(task_service.failed) == 1
    _, message = task_service.failed[0]
    assert len(message) <= 500


@pytest.mark.asyncio
async def test_repair_vector_metadata_binds_execution_on_success_and_never_fails_the_task(monkeypatch) -> None:
    task_service = _FakeTaskService()
    _patch_app_context(monkeypatch, task_service)
    service = CorpusManagerService(ingestion_task_service=_SucceedingIngestionTaskService())
    req = RepairVectorMetadataRequestV1(source_tag="fred", team_id="team-a")

    resp = await service.repair_vector_metadata(req, _FakeUser())

    assert resp.task_id == "task-1"
    assert task_service.bound == [("task-1", "wf-1")]
    assert task_service.failed == []
