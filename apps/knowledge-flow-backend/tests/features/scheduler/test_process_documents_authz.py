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

"""AUTHZ-05 §27: `/process-documents` must be team-scoped via each file's tags,
not the org-level `CAN_PROCESS_CONTENT` gate any global Keycloak `editor`
satisfied regardless of team membership. Mirrors the existing, already-correct
per-tag pattern in `ingestion_controller.py`'s `upload-process-documents`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, DocumentPermission, KeycloakUser, Resource, TagPermission, get_current_user
from fred_core.common.fastapi_handlers import register_exception_handlers

from knowledge_flow_backend.features.scheduler import scheduler_controller as scheduler_module
from knowledge_flow_backend.features.scheduler.scheduler_controller import SchedulerController
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService


class _FakeRebac:
    def __init__(self, *, deny_tag: str | None = None) -> None:
        self.calls: list[tuple[object, str]] = []
        self._deny_tag = deny_tag

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if resource_id == self._deny_tag:
            raise AuthorizationError(user.uid, permission.value, Resource.TAGS)


@pytest.fixture
def scheduler_client(monkeypatch, app_context):
    fake_rebac = _FakeRebac()
    monkeypatch.setattr(scheduler_module, "get_rebac_engine", lambda: fake_rebac)

    async def metadata(_self, user, uid):
        return SimpleNamespace(
            tags=SimpleNamespace(tag_ids={"doc-1": ["tag-a", "tag-b"], "doc-2": ["tag-c"], "no-tags": []}[uid]),
            source=SimpleNamespace(source_tag="uploads"),
            document_name=uid,
            processing=SimpleNamespace(stages={"raw": "done"}, profile=None),
        )

    monkeypatch.setattr(scheduler_module.MetadataService, "get_document_metadata", metadata)

    async def _fake_submit_documents(self, *, user, pipeline_name, files, background_tasks=None):
        definition = SimpleNamespace(name=pipeline_name, files=files)
        handle = SimpleNamespace(workflow_id="wf-1", run_id="run-1")
        return definition, handle

    monkeypatch.setattr(IngestionTaskService, "submit_documents", _fake_submit_documents)

    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(prefix="/knowledge-flow/v1")
    SchedulerController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    with TestClient(app) as client:
        yield client, fake_rebac


def _file(document_uid: str, tags: list[str]) -> dict:
    return {"source_tag": "uploads", "tags": tags, "document_uid": document_uid}


def test_process_documents_checks_tag_permission_per_file(scheduler_client) -> None:
    client, fake_rebac = scheduler_client

    response = client.post(
        "/knowledge-flow/v1/process-documents",
        json={
            "pipeline_name": "test-pipeline",
            "files": [_file("doc-1", ["tag-a", "tag-b"]), _file("doc-2", ["tag-c"])],
        },
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (DocumentPermission.PROCESS, "doc-1"),
        (DocumentPermission.PROCESS, "doc-2"),
        (TagPermission.UPDATE, "tag-a"),
        (TagPermission.UPDATE, "tag-b"),
        (TagPermission.UPDATE, "tag-c"),
    ]


def test_process_documents_denies_when_caller_lacks_tag_permission(scheduler_client) -> None:
    client, fake_rebac = scheduler_client
    fake_rebac._deny_tag = "tag-b"

    response = client.post(
        "/knowledge-flow/v1/process-documents",
        json={
            "pipeline_name": "test-pipeline",
            "files": [_file("doc-1", ["tag-a", "tag-b"])],
        },
    )

    assert response.status_code == 403
    # Denied on tag-b, before any further (e.g. tag-c) checks or submission.
    assert fake_rebac.calls == [
        (DocumentPermission.PROCESS, "doc-1"),
        (TagPermission.UPDATE, "tag-a"),
        (TagPermission.UPDATE, "tag-b"),
    ]


def test_process_documents_denies_file_with_no_tags(scheduler_client) -> None:
    # AUTHZ-05 §27 review item 2: an empty `tags` list must not silently bypass
    # the per-tag authorization loop — it must be refused explicitly, before any
    # rebac call or scheduler submission.
    client, fake_rebac = scheduler_client

    response = client.post(
        "/knowledge-flow/v1/process-documents",
        json={
            "pipeline_name": "test-pipeline",
            "files": [_file("no-tags", ["forged-tag"])],
        },
    )

    assert response.status_code == 400
    assert fake_rebac.calls == [(DocumentPermission.PROCESS, "no-tags")]


def test_process_documents_denies_whole_request_when_one_file_has_no_tags(scheduler_client) -> None:
    # Mixed request: one file with valid tags, one with none. The check is
    # per-file, so the whole submission must be refused, not just the bad file.
    client, fake_rebac = scheduler_client

    response = client.post(
        "/knowledge-flow/v1/process-documents",
        json={
            "pipeline_name": "test-pipeline",
            "files": [_file("doc-1", ["tag-a"]), _file("no-tags", ["forged-tag"])],
        },
    )

    assert response.status_code == 400
    assert fake_rebac.calls == [(DocumentPermission.PROCESS, "doc-1"), (DocumentPermission.PROCESS, "no-tags")]


@pytest.mark.parametrize(
    "stages,profile,requested,status",
    [
        ({"raw": "done"}, None, None, 422),
        ({"raw": "done"}, None, "rich", 200),
        ({"raw": "done", "preview": "failed"}, "rich", "fast", 200),
        ({"raw": "done", "preview": "in_progress"}, "rich", "rich", 409),
        ({"raw": "done", "vector": "done"}, "rich", "rich", 409),
    ],
)
def test_relaunch_eligibility_and_profile(scheduler_client, monkeypatch, stages, profile, requested, status):
    client, _ = scheduler_client

    async def metadata(_self, user, uid):
        return SimpleNamespace(tags=SimpleNamespace(tag_ids=["tag-a"]), source=SimpleNamespace(source_tag="uploads"), document_name=uid, processing=SimpleNamespace(stages=stages, profile=profile))

    monkeypatch.setattr(scheduler_module.MetadataService, "get_document_metadata", metadata)
    submitted = []

    async def submit(_self, **kwargs):
        submitted.extend(kwargs["files"])
        return SimpleNamespace(name="relaunch", files=kwargs["files"]), SimpleNamespace(workflow_id="wf", run_id=None)

    monkeypatch.setattr(IngestionTaskService, "submit_documents", submit)
    file = _file("doc-1", ["tag-a"])
    if requested:
        file["profile"] = requested
    response = client.post("/knowledge-flow/v1/process-documents", json={"files": [file], "pipeline_name": "relaunch", "relaunch": True})
    assert response.status_code == status
    if status == 200:
        assert submitted[0].profile == (profile or requested)
    else:
        assert not submitted
