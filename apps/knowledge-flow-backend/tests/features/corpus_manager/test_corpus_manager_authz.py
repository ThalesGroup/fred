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

"""AUTHZ-05 §27: corpus_manager endpoints must be team-scoped, not org-scoped.

`capabilities`/`tasks_get`/`tasks_result`/`tasks_list` previously accepted any
global Keycloak `viewer`/`editor` via `OrganizationPermission.CAN_READ_CONTENT`
regardless of team membership. They now require an explicit `team_id`/scope
and check the specific `TeamPermission`/`TagPermission`/`DocumentPermission` —
these tests pin the exact permission and resource id checked, mirroring
`features/ingestion/test_fast_delete_authz.py`'s pattern.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import DocumentPermission, KeycloakUser, TagPermission, TeamPermission, get_current_user

from knowledge_flow_backend.features.corpus_manager import corpus_manager_controller as corpus_module
from knowledge_flow_backend.features.corpus_manager.corpus_manager_controller import (
    CorpusManagerController,
)


class _FakeRebac:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))

    async def check_user_team_permission_or_raise(self, user, permission, team_id, **_kw) -> None:
        self.calls.append((permission, team_id))


@pytest.fixture
def corpus_client(monkeypatch):
    fake_rebac = _FakeRebac()
    monkeypatch.setattr(corpus_module, "get_rebac_engine", lambda: fake_rebac)

    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    CorpusManagerController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    with TestClient(app) as client:
        yield client, fake_rebac


def test_capabilities_requires_team_id_and_checks_team_permission(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.get("/knowledge-flow/v1/corpus/capabilities", params={"team_id": "team-a"})

    assert response.status_code == 200
    assert fake_rebac.calls == [(TeamPermission.CAN_READ_MEMEBERS, "team-a")]


def test_capabilities_rejects_missing_team_id(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.get("/knowledge-flow/v1/corpus/capabilities")

    assert response.status_code == 422
    assert fake_rebac.calls == []


def test_build_toc_checks_tag_permission_for_each_scoped_tag(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"tag_ids": ["tag-1", "tag-2"]}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (TagPermission.UPDATE, "tag-1"),
        (TagPermission.UPDATE, "tag-2"),
    ]


def test_build_toc_checks_document_permission_for_scoped_documents(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"document_uids": ["doc-1"]}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (DocumentPermission.PROCESS, "doc-1"),
    ]


def test_build_toc_rejects_library_id_only_scope_as_unauthorizable(corpus_client) -> None:
    """A `library_id`/`project_id`-only scope has no ReBAC object to check
    against yet — default deny (RFC §2.5), not a silent org-level bypass."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"library_id": "lib-1"}},
    )

    assert response.status_code == 400
    assert fake_rebac.calls == [(TeamPermission.CAN_READ_MEMEBERS, "team-a")]


def test_build_toc_rejects_missing_team_id(corpus_client) -> None:
    """AUTHZ-05 review finding: the created task is filed under team_id — it
    must be required, not silently absent."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"scope": {"tag_ids": ["tag-1"]}},
    )

    assert response.status_code == 422
    assert fake_rebac.calls == []


def test_tasks_list_requires_team_id_and_checks_team_permission(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post("/knowledge-flow/v1/corpus/tasks/list", json={"team_id": "team-b"})

    assert response.status_code == 200
    assert fake_rebac.calls == [(TeamPermission.CAN_READ_MEMEBERS, "team-b")]


def test_tasks_get_denies_task_from_a_different_team(corpus_client) -> None:
    """AUTHZ-05 review finding: a task created under team-a must not be
    readable by naming a different team_id, even one the caller genuinely
    belongs to — this was the IDOR the fix closes. Same response shape as a
    truly unknown task_id, so this endpoint cannot be used as an oracle to
    learn that another team's task_id exists."""
    client, fake_rebac = corpus_client

    created = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"tag_ids": ["tag-1"]}},
    )
    task_id = created.json()["task_id"]
    fake_rebac.calls.clear()

    cross_team = client.post(
        "/knowledge-flow/v1/corpus/tasks/get",
        json={"task_id": task_id, "team_id": "team-b"},
    )

    assert cross_team.status_code == 200
    assert cross_team.json()["operation"] == "unknown"
    assert fake_rebac.calls == [(TeamPermission.CAN_READ_MEMEBERS, "team-b")]

    same_team = client.post(
        "/knowledge-flow/v1/corpus/tasks/get",
        json={"task_id": task_id, "team_id": "team-a"},
    )
    assert same_team.status_code == 200
    assert same_team.json()["operation"] == "build_corpus_toc"


def test_tasks_list_only_returns_the_requested_team_own_tasks(corpus_client) -> None:
    """AUTHZ-05 review finding: tasks_list previously ignored team_id
    entirely and returned every task in the pod's shared store, regardless of
    which team the caller asked about."""
    client, fake_rebac = corpus_client

    client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"tag_ids": ["tag-1"]}},
    )
    client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-b", "scope": {"tag_ids": ["tag-2"]}},
    )
    fake_rebac.calls.clear()

    response = client.post("/knowledge-flow/v1/corpus/tasks/list", json={"team_id": "team-a"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert all(item["team_id"] == "team-a" for item in payload["items"])
