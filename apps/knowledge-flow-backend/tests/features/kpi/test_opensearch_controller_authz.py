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

"""Raw OpenSearch Ops surface authz wiring (issue #2009).

Cluster health, indices, mappings, shard allocation, and diagnostics are
platform-wide infrastructure visibility with no personal-scope subset, so
every route requires `CAN_OBSERVE_PLATFORM` — same capability as
`/kpi/query`'s `view_global` branch. Exercised via a representative sample
of routes (cheap GET, path param, and derived-summary shapes) rather than
all ~22, since they all share one gate.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission, Resource, get_current_user
from fred_core.common import register_exception_handlers

from knowledge_flow_backend.features.kpi import opensearch_controller as opensearch_controller_module
from knowledge_flow_backend.features.kpi.opensearch_controller import OpenSearchOpsController


class _FakeOpenSearchClient:
    class _Cluster:
        def health(self):
            return {"status": "green"}

    class _Cat:
        def indices(self, **_kw):
            return []

        def shards(self, **_kw):
            return []

    def __init__(self) -> None:
        self.cluster = self._Cluster()
        self.cat = self._Cat()


class _FakeRebac:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if self.deny:
            raise AuthorizationError(user.uid, str(permission), Resource.ORGANIZATION)


def _build_app(monkeypatch, rebac: _FakeRebac) -> TestClient:
    client = _FakeOpenSearchClient()

    class _FakeAppContext:
        def get_opensearch_client(self):
            return client

    monkeypatch.setattr(opensearch_controller_module, "get_app_context", lambda: _FakeAppContext())
    monkeypatch.setattr(opensearch_controller_module, "get_rebac_engine", lambda: rebac)

    router = APIRouter()
    OpenSearchOpsController(router)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", roles=[], email=None)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/os/health", "/os/indices", "/os/shards", "/os/diagnostics"])
def test_route_requires_can_observe_platform(monkeypatch, path) -> None:
    rebac = _FakeRebac(deny=False)
    client = _build_app(monkeypatch, rebac)

    response = client.get(path)

    assert response.status_code == 200
    assert (OrganizationPermission.CAN_OBSERVE_PLATFORM, "fred") in rebac.calls


@pytest.mark.parametrize("path", ["/os/health", "/os/indices", "/os/shards", "/os/diagnostics"])
def test_route_denies_caller_without_can_observe_platform(monkeypatch, path) -> None:
    rebac = _FakeRebac(deny=True)
    client = _build_app(monkeypatch, rebac)

    response = client.get(path)

    assert response.status_code == 403
