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
human token is refused outright. Admission is all that is exercised here — the
service behind it has its own tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import fred_core.security.oidc as oidc
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user, get_current_user_without_gcu
from fred_core.security.structure import (
    LOCAL_DEV_CLIENT_ID,
    SERVICE_AGENT_ROLE,
    is_service_agent,
)

import knowledge_flow_backend.features.library_sync.controller as controller_module
from knowledge_flow_backend.features.library_sync.controller import (
    LibrarySyncController,
    require_sync_client,
)
from knowledge_flow_backend.features.library_sync.structures import LibrarySourceVersion

SOURCE_VERSION_PATH = "/libraries/library/source-version"


class _RecordingService:
    """Stands in for the real service, which reaches a store these tests do not run."""

    def __init__(self) -> None:
        self.seen: list[tuple[KeycloakUser, str]] = []

    async def read_source_version(self, user: KeycloakUser, library_id: str) -> str:
        self.seen.append((user, library_id))
        return "revision-1"


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


def test_a_human_token_cannot_bypass_gcu_through_these_routes(
    sync: SimpleNamespace,
) -> None:
    human = KeycloakUser(uid="human", username="human", roles=[], client_id="frontend")
    with _client(sync, human) as client:
        response = client.get(SOURCE_VERSION_PATH)
    assert response.status_code == 403
    assert sync.service.seen == []


def test_the_local_dev_client_still_reaches_these_routes(
    sync: SimpleNamespace,
) -> None:
    """Authentication being off must not leave a local stack unable to synchronize.

    Deliberately runs the real dependency instead of supplying an identity: the
    mock it returns carries `admin` and never `service_agent`, so a hand-built
    caller would pass this while local ingestion stayed locked out.
    """
    assert not oidc.KEYCLOAK_ENABLED, "this test describes a stack with authentication off"
    with _client(sync) as client:
        response = client.get(SOURCE_VERSION_PATH)
    assert response.status_code == 200
    ((caller, _),) = sync.service.seen
    assert caller.client_id == LOCAL_DEV_CLIENT_ID
    assert not is_service_agent(caller)
