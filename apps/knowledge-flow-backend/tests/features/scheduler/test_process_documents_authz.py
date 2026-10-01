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

"""Processing uses stored membership and one editor decision per team/root."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, Resource, TeamPermission, get_current_user
from fred_core.common.fastapi_handlers import register_exception_handlers

from knowledge_flow_backend.features.scheduler import scheduler_controller as scheduler_module
from knowledge_flow_backend.features.scheduler.scheduler_controller import SchedulerController
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess


def metadata(uid, *, folder="tag-a", kind="corpus", stages=None, profile=None):
    return SimpleNamespace(
        document_uid=uid,
        kind=kind,
        tags=SimpleNamespace(tag_ids=[folder] if folder else []),
        source=SimpleNamespace(source_tag="uploads"),
        document_name=uid,
        processing=SimpleNamespace(stages=stages or {"raw": "done"}, profile=profile),
    )


@pytest.fixture
def scheduler_client(monkeypatch, app_context):
    docs = {"doc-1": metadata("doc-1"), "doc-2": metadata("doc-2", folder="tag-b"), "no-tags": metadata("no-tags", folder=None)}
    store = SimpleNamespace(get_metadata_by_uids=AsyncMock(side_effect=lambda uids: [docs[uid] for uid in uids if uid in docs]))
    rebac = SimpleNamespace(check_user_permission_or_raise=AsyncMock())
    folders = SimpleNamespace(get_tags_by_ids=AsyncMock(side_effect=lambda ids: [SimpleNamespace(id=uid, owner_id="team-a", deletion_task_id=None) for uid in ids]))
    service = SimpleNamespace(metadata_store=store, corpus_access=CorpusAccess(rebac, folders))
    monkeypatch.setattr(scheduler_module, "MetadataService", lambda: service)
    submit = AsyncMock(side_effect=lambda **kw: (SimpleNamespace(name=kw["pipeline_name"], files=kw["files"]), SimpleNamespace(workflow_id="wf-1", run_id=None)))
    monkeypatch.setattr(IngestionTaskService, "submit_documents", submit)
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(prefix="/knowledge-flow/v1")
    SchedulerController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", roles=[])
    with TestClient(app) as client:
        yield client, docs, store, rebac, submit


def request(client, uids, **kwargs):
    return client.post(
        "/knowledge-flow/v1/process-documents", json={"pipeline_name": "relaunch", "files": [{"source_tag": "forged-source", "tags": ["forged-folder"], "document_uid": uid} for uid in uids], **kwargs}
    )


@pytest.mark.parametrize("count", [2, 1001])
def test_processing_batches_use_one_team_editor_check(scheduler_client, count):
    client, docs, store, rebac, submit = scheduler_client
    docs.update({f"doc-{i}": metadata(f"doc-{i}", folder=f"folder-{i % 3}") for i in range(count)})
    uids = [f"doc-{i}" for i in range(count)]
    response = request(client, uids)
    assert response.status_code == 200
    store.get_metadata_by_uids.assert_awaited_once()
    rebac.check_user_permission_or_raise.assert_awaited_once()
    assert rebac.check_user_permission_or_raise.call_args.args[1:] == (TeamPermission.CAN_UPDATE_RESOURCES, "team-a")
    sent = submit.call_args.kwargs["files"]
    assert [file.tags for file in sent] == [docs[uid].tags.tag_ids for uid in uids]
    assert all(file.source_tag == "uploads" for file in sent)


def test_processing_denied_before_submission(scheduler_client):
    client, _, _, rebac, submit = scheduler_client
    rebac.check_user_permission_or_raise.side_effect = AuthorizationError("alice", TeamPermission.CAN_UPDATE_RESOURCES.value, Resource.TEAM)
    assert request(client, ["doc-1", "doc-2"]).status_code == 403
    submit.assert_not_called()


@pytest.mark.parametrize("uid,status", [("missing", 404), ("no-tags", 400), ("attachment", 400)])
def test_invalid_document_refuses_whole_request(scheduler_client, uid, status):
    client, docs, _, _, submit = scheduler_client
    docs["attachment"] = metadata("attachment", folder=None, kind="attachment")
    assert request(client, ["doc-1", uid]).status_code == status
    submit.assert_not_called()


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
def test_relaunch_eligibility_and_profile(scheduler_client, stages, profile, requested, status):
    client, docs, _, _, submit = scheduler_client
    docs["doc-1"] = metadata("doc-1", stages=stages, profile=profile)
    file = {"source_tag": "uploads", "tags": ["forged-folder"], "document_uid": "doc-1"}
    if requested:
        file["profile"] = requested
    response = client.post("/knowledge-flow/v1/process-documents", json={"files": [file], "pipeline_name": "relaunch", "relaunch": True})
    assert response.status_code == status
    if status == 200:
        assert submit.call_args.kwargs["files"][0].profile == (profile or requested)
    else:
        submit.assert_not_called()
