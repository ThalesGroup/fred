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

"""Who these routes let in, and who they turn away.

A source is mirrored by a workload, never by a person: GCU admission has no
record to check for a service account, and skipping it is only safe while a
human token is refused outright. Admission, and the shape of a write's answer,
are all that is exercised here — the service behind them has its own tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import fred_core.security.oidc as oidc
import pytest
from fastapi import APIRouter, BackgroundTasks, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user, get_current_user_without_gcu
from fred_core.security.structure import SERVICE_AGENT_ROLE

import knowledge_flow_backend.features.library_sync.controller as controller_module
from knowledge_flow_backend.features.library_sync.controller import (
    LibrarySyncController,
    require_sync_client,
)
from knowledge_flow_backend.features.library_sync.structures import (
    DocumentAccepted,
    LibrarySourceVersion,
    SynchronizationUnavailable,
)

SOURCE_VERSION_PATH = "/libraries/library/source-version"
DOCUMENTS_PATH = "/libraries/library/documents"


class _RecordingService:
    """Stands in for the real service, which reaches a store these tests do not run."""

    def __init__(self) -> None:
        self.seen: list[tuple[KeycloakUser, str]] = []
        self.writes: list[dict[str, object]] = []
        self.unavailable = False

    async def read_source_version(self, user: KeycloakUser, library_id: str) -> str:
        self.seen.append((user, library_id))
        return "revision-1"

    async def write_document(self, user: KeycloakUser, *, library_id, path, source_key, document_version, source_tag, upload, background_tasks=None) -> DocumentAccepted:
        if self.unavailable:
            raise SynchronizationUnavailable("no scheduler is enabled")
        self.writes.append({"user": user, "library_id": library_id, "path": path, "source_key": source_key, "background_tasks": background_tasks})
        return DocumentAccepted(source_key=source_key, path=path, document_version=document_version, created=True, document_uid="doc-1", task_id="task-1")


@pytest.fixture
def sync(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The routes, plus the stub they reached, with no store behind either."""
    monkeypatch.setattr(controller_module, "LibrarySyncService", _RecordingService)
    router = APIRouter()
    controller = LibrarySyncController(router)
    return SimpleNamespace(router=router, service=controller.service)


def _client(sync: SimpleNamespace, user: KeycloakUser | None = None) -> TestClient:
    """Serve the routes as `user`, or as whatever the real dependency returns."""
    app = FastAPI()
    app.include_router(sync.router)
    if user is not None:
        app.dependency_overrides[get_current_user_without_gcu] = lambda: user
    return TestClient(app)


@pytest.mark.parametrize(
    "path,method",
    [
        ("/libraries/{library_id}/documents", "POST"),
        ("/libraries/{library_id}/documents", "DELETE"),
        ("/libraries/{library_id}/source-version", "GET"),
        ("/libraries/{library_id}/source-version", "PUT"),
        ("/libraries/{library_id}/synchronized-by", "PUT"),
    ],
)
def test_machine_routes_use_jwt_without_human_admission(sync: SimpleNamespace, path: str, method: str) -> None:
    route = next(r for r in sync.router.routes if isinstance(r, APIRoute) and r.path == path and method in r.methods)
    calls = {d.call for d in route.dependant.dependencies}
    assert require_sync_client in calls
    guard = next(d for d in route.dependant.dependencies if d.call is require_sync_client)
    assert get_current_user_without_gcu in {d.call for d in guard.dependencies}
    assert get_current_user not in calls


def test_a_workload_reaches_the_service_without_a_user_record(
    sync: SimpleNamespace,
) -> None:
    machine = KeycloakUser(uid="machine", username="sync", roles=[SERVICE_AGENT_ROLE], client_id="sync-client")
    with _client(sync, machine) as client:
        response = client.get(SOURCE_VERSION_PATH)
    assert response.status_code == 200
    assert response.json() == LibrarySourceVersion(source_version="revision-1").model_dump()
    assert sync.service.seen == [(machine, "library")]


def _machine() -> KeycloakUser:
    return KeycloakUser(uid="machine", username="sync", roles=[SERVICE_AGENT_ROLE], client_id="sync-client")


def _post_document(client: TestClient):
    return client.post(
        DOCUMENTS_PATH,
        data={"path": "specs/api.md", "source_key": "specs/api.md", "document_version": "etag-1"},
        files={"file": ("api.md", b"# api\n", "text/markdown")},
    )


def test_a_write_is_accepted_with_a_task_to_follow(sync: SimpleNamespace) -> None:
    """Accepted, not done: the pipeline the upload surface uses answers later, through the task."""
    with _client(sync, _machine()) as client:
        response = _post_document(client)

    assert response.status_code == 202
    expected = DocumentAccepted(source_key="specs/api.md", path="specs/api.md", document_version="etag-1", created=True, document_uid="doc-1", task_id="task-1")
    assert response.json() == expected.model_dump()
    [write] = sync.service.writes
    assert (write["library_id"], write["path"], write["source_key"]) == ("library", "specs/api.md", "specs/api.md")
    # The request's own background tasks reach the service, so a memory-backed
    # pipeline runs after the answer instead of holding it.
    assert isinstance(write["background_tasks"], BackgroundTasks)


def test_a_stack_that_cannot_schedule_says_so_instead_of_half_accepting(sync: SimpleNamespace) -> None:
    sync.service.unavailable = True
    with _client(sync, _machine()) as client:
        response = _post_document(client)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "scheduling_unavailable"
    assert sync.service.writes == []


def test_a_human_token_cannot_bypass_gcu_through_these_routes(
    sync: SimpleNamespace,
) -> None:
    human = KeycloakUser(uid="human", username="human", roles=[], client_id="frontend")
    with _client(sync, human) as client:
        response = client.get(SOURCE_VERSION_PATH)
    assert response.status_code == 403
    assert sync.service.seen == []


def test_a_stack_with_authentication_off_cannot_synchronize(
    sync: SimpleNamespace,
) -> None:
    """Synchronizing requires a deployment that authenticates. That is the design.

    Runs the real dependency rather than a supplied identity: with authentication
    off, the mock it returns carries `admin` and no workload role, so it is
    refused like any other non-workload caller. A Knowledge Base is not meant to
    run against such a stack, and failing here is how that stays true.
    """
    assert not oidc.KEYCLOAK_ENABLED, "this test describes a stack with authentication off"
    with _client(sync) as client:
        response = client.get(SOURCE_VERSION_PATH)
    assert response.status_code == 403
    assert sync.service.seen == []
