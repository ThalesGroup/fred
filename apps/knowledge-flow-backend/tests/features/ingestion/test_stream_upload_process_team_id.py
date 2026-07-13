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

"""`_stream_upload_process` must tag every created task_run with the resolved
destination team_id. Before this fix, `task_svc.start(...)` never received a
`team_id`, so every ingestion task was created with `team_id=NULL` — a
team-scoped Activity query (`WHERE team_id = :team_id`) never matches NULL, so
a team admin saw an empty Activity page while a platform admin (no team_id
filter) saw everything (found via live testing, see
`NOTES-INGESTION-TASK-TRACKING-FIX.md`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _FakeService:
    def __init__(self) -> None:
        self._n = 0

    async def extract_metadata(self, user, file_path, tags, source_tag, profile):
        self._n += 1
        return SimpleNamespace(document_uid=f"doc-{self._n}", document_name=file_path.name, file_type=file_path.suffix.lstrip("."))

    def save_input(self, user, metadata, input_dir) -> None:
        return None

    async def save_metadata(self, user, metadata) -> None:
        return None


class _FakeKpi:
    def emit(self, **kwargs) -> None:
        return None


class _FakeTaskService:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.bound: list[tuple[str, str]] = []
        self._next_id = 0

    async def start(self, req, *, created_by, team_id=None, target=None):
        self._next_id += 1
        task_id = f"task-{self._next_id}"
        self.started.append({"task_id": task_id, "created_by": created_by, "team_id": team_id, "target": target})
        return SimpleNamespace(task_id=task_id)

    async def bind_execution(self, task_id: str, *, execution_id: str) -> None:
        self.bound.append((task_id, execution_id))

    async def fail_task(self, task_id: str, message: str) -> bool:
        return True


class _FakeSchedulerTaskService:
    async def submit_documents(self, *, user, pipeline_name, files, background_tasks=None):
        return None, SimpleNamespace(workflow_id="wf-1")


def _controller(resolved_team_ids: set[str]) -> IngestionController:
    controller = IngestionController.__new__(IngestionController)
    controller.service = _FakeService()
    controller._scheduler_backend = lambda: SchedulerBackend.MEMORY

    async def _fake_resolve_tag_owners(tags, user):
        # Resolution itself is covered by test_resolve_tag_owners.py — here we
        # only care whether the resolved id reaches task_svc.start(...).
        return resolved_team_ids, set()

    controller._resolve_tag_owners = _fake_resolve_tag_owners  # type: ignore[method-assign]
    return controller


def _user() -> KeycloakUser:
    return KeycloakUser(uid="bob", username="bob", email=None, roles=[])


async def _drain(controller: IngestionController, monkeypatch: pytest.MonkeyPatch, tmp_path, task_service: _FakeTaskService, tags: list[str]) -> None:
    input_dir = tmp_path / "upload-workdir" / "input"
    input_dir.mkdir(parents=True)
    input_temp_file = input_dir / "sample.pdf"
    input_temp_file.write_bytes(b"%PDF-1.4")

    fake_ctx = SimpleNamespace(get_task_service=lambda: task_service)
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: fake_ctx))

    event_stream = controller._stream_upload_process(
        preloaded_files=[("sample.pdf", input_temp_file)],
        user=_user(),
        tags=tags,
        source_tag="fred",
        profile=IngestionProcessingProfile.medium,
        scheduler_task_service=_FakeSchedulerTaskService(),
        background_tasks=None,
        kpi=_FakeKpi(),
        kpi_actor=SimpleNamespace(type="human"),
        timer_dims={},
    )
    async for _ in event_stream:
        pass


@pytest.mark.asyncio
async def test_task_is_created_with_the_resolved_team_id(monkeypatch, tmp_path):
    task_service = _FakeTaskService()
    controller = _controller(resolved_team_ids={"team-fredlab"})

    await _drain(controller, monkeypatch, tmp_path, task_service, tags=["tag-ecb"])

    assert len(task_service.started) == 1
    assert task_service.started[0]["team_id"] == "team-fredlab"


@pytest.mark.asyncio
async def test_task_team_id_is_none_when_tags_are_ambiguous_across_teams(monkeypatch, tmp_path):
    # Two teams resolved for one request's tags — deliberately do not guess.
    task_service = _FakeTaskService()
    controller = _controller(resolved_team_ids={"team-a", "team-b"})

    await _drain(controller, monkeypatch, tmp_path, task_service, tags=["tag-a", "tag-b"])

    assert task_service.started[0]["team_id"] is None


@pytest.mark.asyncio
async def test_task_team_id_is_none_for_a_personal_space_upload(monkeypatch, tmp_path):
    # No team resolved at all (personal-space tag) — team_id stays None, same as
    # before this fix; only a platform admin sees these, which is correct.
    task_service = _FakeTaskService()
    controller = _controller(resolved_team_ids=set())

    await _drain(controller, monkeypatch, tmp_path, task_service, tags=["tag-personal"])

    assert task_service.started[0]["team_id"] is None
