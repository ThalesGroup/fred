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

"""HTTP-level tests for the label routes: the new canonical
`PATCH /documents/{document_uid}/labels` body transport, and backward
compatibility of the deprecated `POST`/`DELETE .../labels/{label}` routes.
Runs real HTTP requests through `TestClient` against a real SQLite-backed
store — the thing under test (URL path-segment character handling vs. JSON
body transport) is only meaningfully observable at the HTTP layer, not by
calling service methods directly in Python.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, RebacDisabledResult, get_current_user
from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.controller import MetadataController


class _FakeRebac:
    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        return None

    async def lookup_user_resources(self, user, permission):
        return RebacDisabledResult()


def _doc(uid: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid, modified=datetime.now(timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
    )


@pytest_asyncio.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'labels_controller.sqlite3'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    fake_context = SimpleNamespace(
        get_config=lambda: SimpleNamespace(),
        get_metadata_store=lambda: store,
        get_content_store=lambda: None,
        get_rebac_engine=lambda: _FakeRebac(),
        get_pg_async_engine=lambda: engine,
    )
    monkeypatch.setattr(ApplicationContext, "get_instance", staticmethod(lambda: fake_context))

    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    MetadataController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="u-1", username="u-1", email="u-1@localhost", roles=["admin"])

    with TestClient(app) as test_client:
        yield test_client


def test_patch_adds_and_removes_labels_in_one_request(client: TestClient) -> None:
    response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"add": ["DAT", "MEX"], "remove": []})

    assert response.status_code == 200
    assert response.json() == ["DAT", "MEX"]

    response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"add": [], "remove": ["DAT"]})
    assert response.status_code == 200
    assert response.json() == ["MEX"]


def test_patch_defaults_add_and_remove_to_empty_lists(client: TestClient) -> None:
    response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "label",
    ["a/b", "a#b", "a?b", "a%b", "with space", "café", "日本語"],
    ids=["slash", "hash", "question-mark", "percent", "space", "unicode-accent", "unicode-cjk"],
)
def test_patch_transports_characters_the_old_path_segment_route_could_not(client: TestClient, label: str) -> None:
    response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"add": [label]})

    assert response.status_code == 200
    assert response.json() == [label]


def test_deprecated_post_route_still_adds_a_label_it_could_already_transport(client: TestClient) -> None:
    response = client.post("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    assert response.status_code == 200
    assert response.json() == ["DAT"]


def test_deprecated_delete_route_still_removes_a_label(client: TestClient) -> None:
    client.post("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    response = client.delete("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    assert response.status_code == 200
    assert response.json() == []


def test_deprecated_routes_and_the_patch_route_share_one_stored_state(client: TestClient) -> None:
    """Proof they are adapters onto the same mutation, not a second
    implementation: a label added via the deprecated POST route is visible
    to, and removable via, the new PATCH route."""
    client.post("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"remove": ["DAT"], "add": ["MEX"]})

    assert response.status_code == 200
    assert response.json() == ["MEX"]


def test_deprecated_routes_are_marked_deprecated_in_the_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]["/knowledge-flow/v1/documents/{document_uid}/labels/{label}"]

    assert paths["post"].get("deprecated") is True
    assert paths["delete"].get("deprecated") is True
    assert schema["paths"]["/knowledge-flow/v1/documents/{document_uid}/labels"]["patch"].get("deprecated") is not True


def test_operation_ids_are_unchanged(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    label_path = schema["paths"]["/knowledge-flow/v1/documents/{document_uid}/labels/{label}"]

    assert label_path["post"]["operationId"] == "add_document_label"
    assert label_path["delete"]["operationId"] == "remove_document_label"
    assert schema["paths"]["/knowledge-flow/v1/documents/labels"]["get"]["operationId"] == "list_document_labels"
    assert schema["paths"]["/knowledge-flow/v1/documents/by-label/{label}"]["get"]["operationId"] == "list_documents_by_label"
    assert schema["paths"]["/knowledge-flow/v1/documents/{document_uid}/labels"]["patch"]["operationId"] == "mutate_document_labels"


def test_mutating_a_missing_document_returns_404(client: TestClient) -> None:
    response = client.patch("/knowledge-flow/v1/documents/does-not-exist/labels", json={"add": ["DAT"]})

    assert response.status_code == 404


def test_deprecated_post_adapter_updates_the_audit_trail(client: TestClient) -> None:
    before = client.get("/knowledge-flow/v1/documents/metadata/doc-1").json()

    client.post("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    after = client.get("/knowledge-flow/v1/documents/metadata/doc-1").json()
    assert after["identity"]["last_modified_by"] == "u-1"
    assert after["identity"]["modified"] != before["identity"]["modified"]


def test_patch_route_updates_the_audit_trail(client: TestClient) -> None:
    before = client.get("/knowledge-flow/v1/documents/metadata/doc-1").json()

    client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"add": ["DAT"]})

    after = client.get("/knowledge-flow/v1/documents/metadata/doc-1").json()
    assert after["identity"]["last_modified_by"] == "u-1"
    assert after["identity"]["modified"] != before["identity"]["modified"]


@pytest.mark.parametrize(
    "label",
    ["a/b", "a#b", "a?b", "a%b", "with space", "café", "日本語"],
    ids=["slash", "hash", "question-mark", "percent", "space", "unicode-accent", "unicode-cjk"],
)
def test_query_param_route_round_trips_a_label_the_path_segment_route_could_not(client: TestClient, label: str) -> None:
    """Full assign-then-resolve round trip: PATCH-assign the label (body
    transport, no character restriction), then resolve it back via the new
    query-parameter GET — proving the two are symmetric, not just that each
    transports the character individually."""
    patch_response = client.patch("/knowledge-flow/v1/documents/doc-1/labels", json={"add": [label]})
    assert patch_response.status_code == 200
    assert patch_response.json() == [label]

    resolve_response = client.get("/knowledge-flow/v1/documents/by-label", params={"label": label})

    assert resolve_response.status_code == 200
    body = resolve_response.json()
    assert body["total"] == 1
    assert body["documents"][0]["identity"]["document_uid"] == "doc-1"


def test_query_param_route_and_path_segment_route_resolve_through_the_same_lookup(client: TestClient) -> None:
    client.post("/knowledge-flow/v1/documents/doc-1/labels/DAT")

    by_path = client.get("/knowledge-flow/v1/documents/by-label/DAT")
    by_query = client.get("/knowledge-flow/v1/documents/by-label", params={"label": "DAT"})

    assert by_path.status_code == by_query.status_code == 200
    assert by_path.json() == by_query.json()


def test_query_param_route_has_its_own_operation_id(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/knowledge-flow/v1/documents/by-label"]["get"]["operationId"] == "resolve_documents_by_label"
    assert schema["paths"]["/knowledge-flow/v1/documents/by-label/{label}"]["get"]["operationId"] == "list_documents_by_label"
