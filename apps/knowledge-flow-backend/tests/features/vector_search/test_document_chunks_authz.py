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

"""Authz gate for the ordered document-chunks route.

The route hands back a document's raw stored text with no similarity filter, so it
is gated on ReBAC DocumentPermission.READ for the requested document - the same
per-document gate the rerank route uses, not an org-level capability.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, DocumentPermission, KeycloakUser, Resource, get_current_user
from fred_core.common import register_exception_handlers
from fred_core.kpi import NoOpKPIWriter
from fred_core.store import VectorSearchHit

from knowledge_flow_backend.features.vector_search import vector_search_controller as controller_module
from knowledge_flow_backend.features.vector_search.reranker import RerankerUnavailable
from knowledge_flow_backend.features.vector_search.vector_search_controller import VectorSearchController


class _FakeRebac:
    def __init__(self, *, deny: bool) -> None:
        self.deny = deny
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if self.deny:
            raise AuthorizationError(user.uid, str(permission), Resource.DOCUMENTS)


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_document_chunks_ordered(self, *, user, document_uid, limit):
        self.calls.append({"document_uid": document_uid, "limit": limit})
        return []

    async def rerank_documents(self, question, documents, top_r):
        self.calls.append({"question": question, "top_r": top_r})
        return documents[:top_r]


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


def test_route_checks_document_read(monkeypatch) -> None:
    rebac = _FakeRebac(deny=False)
    client, service = _build_client(monkeypatch, rebac)

    response = client.get("/vector/document-chunks", params={"document_uid": "doc-1"})

    assert response.status_code == 200
    assert (DocumentPermission.READ, "doc-1") in rebac.calls
    assert service.calls == [{"document_uid": "doc-1", "limit": 200}]


def test_route_denies_caller_without_document_read(monkeypatch) -> None:
    rebac = _FakeRebac(deny=True)
    client, service = _build_client(monkeypatch, rebac)

    response = client.get("/vector/document-chunks", params={"document_uid": "doc-1"})

    assert response.status_code == 403
    assert service.calls == []


@pytest.mark.parametrize("limit", [0, 1001])
def test_limit_is_bounded(monkeypatch, limit) -> None:
    """The cap is the whole point: an unbounded fetch would blow up the prompt."""
    client, service = _build_client(monkeypatch, _FakeRebac(deny=False))

    response = client.get("/vector/document-chunks", params={"document_uid": "doc-1", "limit": limit})

    assert response.status_code == 422
    assert service.calls == []


def test_direct_rerank_keeps_document_process_gate(monkeypatch) -> None:
    rebac = _FakeRebac(deny=False)
    client, service = _build_client(monkeypatch, rebac)
    hit = VectorSearchHit(uid="doc-1", title="Doc", content="visible", score=0.8)

    response = client.post("/vector/rerank", json={"question": "query", "documents": [hit.model_dump(mode="json")], "top_r": 1})

    assert response.status_code == 200
    assert response.json()[0]["uid"] == "doc-1"
    assert (DocumentPermission.PROCESS, "doc-1") in rebac.calls
    assert service.calls == [{"question": "query", "top_r": 1}]


def test_direct_rerank_is_excluded_from_text_mcp_tool_tags(monkeypatch) -> None:
    client, _ = _build_client(monkeypatch, _FakeRebac(deny=False))

    route = client.app.openapi()["paths"]["/vector/rerank"]["post"]
    assert "Vector Search" not in route["tags"]


def test_direct_rerank_accepts_existing_large_request_shape(monkeypatch) -> None:
    client, service = _build_client(monkeypatch, _FakeRebac(deny=False))
    hit = VectorSearchHit(uid="doc-1", title="Doc", content="visible", score=0.8).model_dump(mode="json")

    response = client.post("/vector/rerank", json={"question": "query", "documents": [hit] * 101, "top_r": 101})

    assert response.status_code == 200
    assert len(response.json()) == 101
    assert service.calls == [{"question": "query", "top_r": 101}]


def test_direct_rerank_refuses_unreadable_document(monkeypatch) -> None:
    client, service = _build_client(monkeypatch, _FakeRebac(deny=True))
    hit = VectorSearchHit(uid="doc-1", title="Doc", content="hidden", score=0.8)

    response = client.post("/vector/rerank", json={"question": "query", "documents": [hit.model_dump(mode="json")], "top_r": 1})

    assert response.status_code == 403
    assert service.calls == []


def test_direct_rerank_reports_model_failure(monkeypatch) -> None:
    client, service = _build_client(monkeypatch, _FakeRebac(deny=False))
    hit = VectorSearchHit(uid="doc-1", title="Doc", content="visible", score=0.8)

    async def unavailable(*args):
        raise RerankerUnavailable("model down")

    service.rerank_documents = unavailable
    response = client.post("/vector/rerank", json={"question": "query", "documents": [hit.model_dump(mode="json")], "top_r": 1})

    assert response.status_code == 503
    assert response.json()["detail"] == "reranker_unavailable"
