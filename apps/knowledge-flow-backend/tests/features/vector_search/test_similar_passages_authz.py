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

"""Authz gate for the similar-passages route published on the similarity MCP.

Every named target must be readable before any search runs: READ on each
library folder and on each document.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, DocumentPermission, KeycloakUser, Resource, TagPermission, get_current_user
from fred_core.common import register_exception_handlers
from fred_core.kpi import NoOpKPIWriter

from knowledge_flow_backend.features.vector_search import vector_search_controller as controller_module
from knowledge_flow_backend.features.vector_search.vector_search_controller import VectorSearchController

_ROUTE = "/documents/similar-passages"


class _FakeRebac:
    def __init__(self, *, denied: set[str] | None = None) -> None:
        self.denied = denied or set()
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if resource_id in self.denied:
            raise AuthorizationError(user.uid, str(permission), Resource.DOCUMENTS)


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def similarity_search(self, **kwargs):
        self.calls.append(kwargs)
        return []


def _build_client(monkeypatch, rebac: _FakeRebac) -> tuple[TestClient, _FakeService]:
    service = _FakeService()
    monkeypatch.setattr(controller_module, "VectorSearchService", lambda: service)
    monkeypatch.setattr(controller_module, "get_kpi_writer", NoOpKPIWriter)
    monkeypatch.setattr(controller_module, "get_rebac_engine", lambda: rebac)

    router = APIRouter()
    VectorSearchController(router)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", roles=[], email=None)
    return TestClient(app), service


def test_route_checks_every_target_then_searches(monkeypatch) -> None:
    rebac = _FakeRebac()
    client, service = _build_client(monkeypatch, rebac)

    response = client.post(_ROUTE, json={"anchor": "clause", "document_uids": ["doc-1"], "document_library_tags_ids": ["tag-1"], "top_k": 3})

    assert response.status_code == 200
    assert rebac.calls == [(TagPermission.READ, "tag-1"), (DocumentPermission.READ, "doc-1")]
    assert len(service.calls) == 1
    assert service.calls[0]["document_uids"] == ["doc-1"]
    assert service.calls[0]["document_library_tags_ids"] == ["tag-1"]
    assert service.calls[0]["top_k"] == 3


def test_route_denies_when_one_target_is_unreadable(monkeypatch) -> None:
    rebac = _FakeRebac(denied={"doc-2"})
    client, service = _build_client(monkeypatch, rebac)

    response = client.post(_ROUTE, json={"anchor": "clause", "document_uids": ["doc-1", "doc-2"]})

    assert response.status_code == 403
    assert service.calls == []


def test_route_requires_a_target(monkeypatch) -> None:
    client, service = _build_client(monkeypatch, _FakeRebac())

    response = client.post(_ROUTE, json={"anchor": "clause"})

    assert response.status_code == 422
    assert service.calls == []
