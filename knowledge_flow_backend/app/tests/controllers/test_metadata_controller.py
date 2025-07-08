# Copyright Thales 2025
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

# app/tests/controllers/test_content_controller.py
# Copyright Thales 2025
# Licensed under the Apache License 2.0

from fastapi.testclient import TestClient
from fastapi import status
import pytest

from app.features.metadata.service import MetadataService


# ────────────────────────────────────
# Tell conftest.py which back-ends to use
# ────────────────────────────────────
@pytest.mark.metadata_storage_type(type="local")
@pytest.mark.vector_storage_type(type="in_memory")
@pytest.mark.content_storage_type(type="local")
class TestMetadataController:
    """
    Integration tests for the MetadataController endpoints,
    using the *local* storage back-ends only.
    """

    # ──────────── Fixtures ────────────
    @pytest.fixture
    def document1(self):
        return {
            "document_uid": "doc-01",
            "title": "Example Document",
            "author": "Jane Doe",
            "created": "2024-06-01T12:00:00Z",
            "modified": "2024-06-02T15:30:00Z",
            "document_name": "document.md",
            "front_metadata": {"agent_name": "Georges"},
            "retrievable": True,
        }

    @pytest.fixture
    def document2(self):
        return {
            "document_uid": "doc-02",
            "title": "AI Revolution",
            "author": "Ada Lovelace",
            "created": "2023-01-15T09:00:00Z",
            "modified": "2023-02-10T10:30:00Z",
            "document_name": "ai_revolution.pdf",
            "front_metadata": {"agent_name": "Marvin"},
            "retrievable": False,
        }

    # ──────────── Tests ────────────
    def test_delete_metadata_found(self, client: TestClient, metadata_store, document1, local_content_store):
        metadata_store.save_metadata(document1)
        resp = client.delete(f"/knowledge-flow/v1/document/{document1['document_uid']}")
        assert resp.status_code == status.HTTP_200_OK

    def test_delete_metadata_not_found(self, client: TestClient):
        resp = client.delete("/knowledge-flow/v1/document/does_not_exist")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_documents_metadata(self, client, metadata_store, document1, document2):
        metadata_store.save_metadata(document1)
        metadata_store.save_metadata(document2)

        resp = client.post("/knowledge-flow/v1/documents/metadata", json={})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["documents"]) == 2

    def test_get_documents_metadata_with_filters(self, client, metadata_store, document1, document2):
        metadata_store.save_metadata(document1)
        metadata_store.save_metadata(document2)

        resp = client.post("/knowledge-flow/v1/documents/metadata", json={"agent_name": "Georges"})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["documents"]) == 1

    def test_get_documents_metadata_failure(self, client, monkeypatch):
        def boom(*_, **__):
            raise Exception("DB error")

        monkeypatch.setattr(MetadataService, "get_documents_metadata", boom)

        resp = client.post("/knowledge-flow/v1/documents/metadata", json={})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_document_metadata(self, client, metadata_store, document1):
        metadata_store.save_metadata(document1)

        resp = client.get(f"/knowledge-flow/v1/document/{document1['document_uid']}")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["metadata"]["document_uid"] == document1["document_uid"]

    def test_update_document_retrievable(self, client, metadata_store, document1):
        metadata_store.save_metadata(document1)

        put = client.put(
            f"/knowledge-flow/v1/document/{document1['document_uid']}",
            json={"retrievable": True},
        )
        assert put.status_code == status.HTTP_200_OK

        get_ = client.get(f"/knowledge-flow/v1/document/{document1['document_uid']}")
        assert get_.json()["metadata"]["retrievable"] is True

    def test_update_document_retrievable_failure(self, client):
        resp = client.put("/knowledge-flow/v1/document/does_not_exist", json={"retrievable": True})
        assert resp.status_code in (500, 422)
