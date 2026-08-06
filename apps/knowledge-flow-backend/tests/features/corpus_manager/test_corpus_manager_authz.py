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
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core import ORGANIZATION_ID, DocumentPermission, KeycloakUser, OrganizationPermission, TagPermission, TeamPermission, get_current_user
from fred_core.tasks.models import StartTaskResponse

from knowledge_flow_backend.features.corpus_manager import corpus_manager_controller as corpus_module
from knowledge_flow_backend.features.corpus_manager.corpus_manager_controller import (
    CorpusManagerController,
)
from knowledge_flow_backend.features.corpus_manager.corpus_manager_service import CorpusManagerService


class _FakeRebac:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))

    async def check_user_team_permission_or_raise(self, user, permission, team_id, **_kw) -> None:
        self.calls.append((permission, team_id))


async def _fake_revectorize_corpus(self, req, user) -> StartTaskResponse:
    """Stub for CorpusManagerService.revectorize_corpus (MIGR-07): the tests in this
    module exercise `_authorize_scope`/`_authorize_team`, not the real Temporal
    wiring (the `app_context` autouse fixture runs with `scheduler.enabled=False`,
    so there is no `IngestionTaskService` behind the real method in this suite)."""
    return StartTaskResponse(task_id="fake-task-id")


async def _fake_repair_vector_metadata(self, req, user) -> StartTaskResponse:
    """Stub for CorpusManagerService.repair_vector_metadata (#2234, 3a): same
    reasoning as `_fake_revectorize_corpus` -- these tests exercise
    `_authorize_repair_vector_metadata`, not the real Temporal wiring."""
    return StartTaskResponse(task_id="fake-repair-task-id")


@pytest.fixture
def corpus_client(monkeypatch):
    fake_rebac = _FakeRebac()
    monkeypatch.setattr(corpus_module, "get_rebac_engine", lambda: fake_rebac)
    monkeypatch.setattr(CorpusManagerService, "revectorize_corpus", _fake_revectorize_corpus)
    monkeypatch.setattr(CorpusManagerService, "repair_vector_metadata", _fake_repair_vector_metadata)

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


# ── MIGR-07: revectorize scope authorization ──────────────────────────────────
# `source_tag` is a real CorpusScopeV1 field (the migration's default revectorize
# scope — CORPUS-REVECTORIZE-RFC.md §4) but was previously neither accepted by
# CorpusScopeV1._validate_non_empty nor authorized at all in _authorize_scope. A
# source_tag-only scope spans arbitrary teams, so it must gate on
# OrganizationPermission.CAN_MANAGE_PLATFORM, not team membership; tag_ids and
# document_uids scopes keep the existing per-tag/per-document checks.


def test_revectorize_tag_ids_scope_checks_team_and_tag_permission(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/revectorize",
        json={"team_id": "team-a", "scope": {"tag_ids": ["tag-1"]}},
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "fake-task-id"}
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (TagPermission.UPDATE, "tag-1"),
    ]


def test_revectorize_document_uids_scope_checks_team_and_document_permission(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/revectorize",
        json={"team_id": "team-a", "scope": {"document_uids": ["doc-1"]}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (DocumentPermission.PROCESS, "doc-1"),
    ]


def test_revectorize_source_tag_only_scope_is_accepted_and_requires_platform_admin(corpus_client) -> None:
    """A source_tag-only scope previously 422'd at the pydantic layer
    (CorpusScopeV1._validate_non_empty didn't count source_tag) and, before that
    fix, had no authorization path at all. It must now pass validation and gate on
    CAN_MANAGE_PLATFORM instead of a team/tag/document check it has no object for."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/revectorize",
        json={"team_id": "team-a", "scope": {"source_tag": "kea-import"}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID),
    ]


def test_revectorize_source_tag_combined_with_tag_ids_uses_the_narrower_tag_check(corpus_client) -> None:
    """CAN_MANAGE_PLATFORM is only required for a source_tag-ONLY scope; a request
    that also names tag_ids/document_uids keeps the existing narrower check."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/revectorize",
        json={"team_id": "team-a", "scope": {"source_tag": "kea-import", "tag_ids": ["tag-1"]}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (TagPermission.UPDATE, "tag-1"),
    ]


def test_revectorize_source_tag_only_scope_rejects_non_platform_admin(monkeypatch) -> None:
    """A team member without CAN_MANAGE_PLATFORM must be denied a source_tag-wide
    revectorize — this scope spans arbitrary teams, so team membership alone isn't
    enough (mirrors /documents/audit and import-export reset(-full)'s gate)."""

    class _DenyingPlatformAdminRebac(_FakeRebac):
        async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
            self.calls.append((permission, resource_id))
            if permission == OrganizationPermission.CAN_MANAGE_PLATFORM:
                raise HTTPException(403, "not a platform admin")

    fake_rebac = _DenyingPlatformAdminRebac()
    monkeypatch.setattr(corpus_module, "get_rebac_engine", lambda: fake_rebac)
    monkeypatch.setattr(CorpusManagerService, "revectorize_corpus", _fake_revectorize_corpus)

    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    CorpusManagerController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    with TestClient(app) as client:
        response = client.post(
            "/knowledge-flow/v1/corpus/revectorize",
            json={"team_id": "team-a", "scope": {"source_tag": "kea-import"}},
        )

    assert response.status_code == 403
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID),
    ]


def test_build_toc_source_tag_only_scope_also_requires_platform_admin(corpus_client) -> None:
    """_authorize_scope is shared across build_toc/revectorize/purge_vectors — the
    source_tag fix applies uniformly, not just to the revectorize route."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/build-toc",
        json={"team_id": "team-a", "scope": {"source_tag": "kea-import"}},
    )

    assert response.status_code == 200
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID),
    ]


# ── #2234 (3a): repair-vector-metadata authorization + input validation ──────
# Always a bare source_tag scope (no tag_ids/document_uids variant exists on
# RepairVectorMetadataRequestV1) -- so, unlike revectorize, it always requires
# BOTH real membership on the filing team AND platform-admin, every time
# (`_authorize_repair_vector_metadata`), never just the narrower tag/document
# check revectorize falls back to for a non-source_tag scope.


def test_repair_vector_metadata_checks_team_and_platform_admin_permission(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/repair-vector-metadata",
        json={"team_id": "team-a", "source_tag": "kea-import"},
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "fake-repair-task-id"}
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID),
    ]


def test_repair_vector_metadata_rejects_non_platform_admin(monkeypatch) -> None:
    """A team member without CAN_MANAGE_PLATFORM must be denied -- this action
    always spans arbitrary teams, so team membership alone is never enough."""

    class _DenyingPlatformAdminRebac(_FakeRebac):
        async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
            self.calls.append((permission, resource_id))
            if permission == OrganizationPermission.CAN_MANAGE_PLATFORM:
                raise HTTPException(403, "not a platform admin")

    fake_rebac = _DenyingPlatformAdminRebac()
    monkeypatch.setattr(corpus_module, "get_rebac_engine", lambda: fake_rebac)
    monkeypatch.setattr(CorpusManagerService, "repair_vector_metadata", _fake_repair_vector_metadata)

    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    CorpusManagerController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    with TestClient(app) as client:
        response = client.post(
            "/knowledge-flow/v1/corpus/repair-vector-metadata",
            json={"team_id": "team-a", "source_tag": "kea-import"},
        )

    assert response.status_code == 403
    assert fake_rebac.calls == [
        (TeamPermission.CAN_READ_MEMEBERS, "team-a"),
        (OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID),
    ]


def test_repair_vector_metadata_rejects_empty_source_tag(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/repair-vector-metadata",
        json={"team_id": "team-a", "source_tag": ""},
    )

    assert response.status_code == 422
    assert fake_rebac.calls == []


def test_repair_vector_metadata_rejects_whitespace_only_source_tag(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/repair-vector-metadata",
        json={"team_id": "team-a", "source_tag": "   "},
    )

    assert response.status_code == 422
    assert fake_rebac.calls == []


def test_repair_vector_metadata_rejects_whitespace_only_team_id(corpus_client) -> None:
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/repair-vector-metadata",
        json={"team_id": "   ", "source_tag": "kea-import"},
    )

    assert response.status_code == 422
    assert fake_rebac.calls == []


def test_repair_vector_metadata_strips_surrounding_whitespace() -> None:
    """A valid but padded source_tag/team_id must be usable, not rejected --
    only the pure-whitespace/empty case is invalid."""
    from knowledge_flow_backend.features.corpus_manager.corpus_manager_service import RepairVectorMetadataRequestV1

    req = RepairVectorMetadataRequestV1(source_tag="  kea-import  ", team_id=" team-a ")

    assert req.source_tag == "kea-import"
    assert req.team_id == "team-a"


def test_repair_vector_metadata_rejects_unknown_fields(corpus_client) -> None:
    """`extra="forbid"` must still hold after adding the strip/non-empty
    validator -- e.g. a stray `options`/`scope` field on the payload must 422,
    not be silently ignored."""
    client, fake_rebac = corpus_client

    response = client.post(
        "/knowledge-flow/v1/corpus/repair-vector-metadata",
        json={"team_id": "team-a", "source_tag": "kea-import", "options": {"force": True}},
    )

    assert response.status_code == 422
    assert fake_rebac.calls == []
