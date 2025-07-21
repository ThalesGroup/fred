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

from datetime import datetime
from app.common.structures import DocumentMetadata
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore
from fastapi.testclient import TestClient
from fastapi import status
import pytest


# ────────────────────────────────────
# Tell conftest.py which back-ends to use
# ────────────────────────────────────
@pytest.mark.metadata_storage_type(type="local")
@pytest.mark.vector_storage_type(type="in_memory")
@pytest.mark.content_storage_type(type="local")


@pytest.fixture
def document1():
    return DocumentMetadata(
            document_uid="doc-01",
            document_name="document.md",
            title="Example Document",
            author="Jane Doe",
            created=datetime.fromisoformat("2024-06-01T12:00:00+00:00"),
            modified=datetime.fromisoformat("2024-06-02T15:30:00+00:00"),
            retrievable=True,
    )

@pytest.fixture
def document2():
    return DocumentMetadata(
            document_uid="doc-02",
            document_name="ai_revolution.pdf",
            title="AI Revolution",
            author="Ada Lovelace",
            created=datetime.fromisoformat("2023-01-15T09:00:00+00:00"),
            modified=datetime.fromisoformat("2023-02-10T10:30:00+00:00"),
            retrievable=False,
    )

class TestMetadataController:
    """
    Integration tests for the MetadataController endpoints,
    using the *local* storage back-ends only.
    """

    # ──────────── Tests ────────────
    def test_delete_metadata_found(self, client_fixture: TestClient, 
                                   metadata_store: BaseMetadataStore, document1: DocumentMetadata):
        metadata_store.save_metadata(document1)
        resp = client_fixture.delete(f"/knowledge-flow/v1/document/{document1.document_uid}")
        assert resp.status_code == status.HTTP_200_OK


    def test_delete_metadata_not_found(self, client_fixture: TestClient):
        resp = client_fixture.delete("/knowledge-flow/v1/document/does_not_exist")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_documents_metadata(self, client_fixture, metadata_store: BaseMetadataStore, 
                                    document1: DocumentMetadata, document2: DocumentMetadata):
        metadata_store.save_metadata(document1)
        metadata_store.save_metadata(document2)

        resp = client_fixture.post("/knowledge-flow/v1/documents/metadata", json={})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["documents"]) == 2

    def test_get_documents_metadata_with_filters(self, client_fixture, 
                                                 metadata_store: BaseMetadataStore, 
                                                 document1: DocumentMetadata, 
                                                 document2: DocumentMetadata):
        metadata_store.save_metadata(document1)
        metadata_store.save_metadata(document2)

        resp = client_fixture.post(
            "/knowledge-flow/v1/documents/metadata",
            json={},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["documents"]) == 2

    def test_get_document_metadata(self, client_fixture, 
                                   metadata_store: BaseMetadataStore, 
                                   document1: DocumentMetadata):
        metadata_store.save_metadata(document1)

        resp = client_fixture.get(f"/knowledge-flow/v1/document/{document1.document_uid}")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["metadata"]["document_uid"] == document1.document_uid

    def test_update_document_retrievable(self, client_fixture, 
                                         metadata_store: BaseMetadataStore, document1: DocumentMetadata):
        metadata_store.save_metadata(document1)

        put = client_fixture.put(
            f"/knowledge-flow/v1/document/{document1.document_uid}",
            json={"retrievable": True},
        )
        assert put.status_code == status.HTTP_200_OK

        get_ = client_fixture.get(f"/knowledge-flow/v1/document/{document1.document_uid}")
        assert get_.status_code == status.HTTP_200_OK
        print(get_.json)
        assert get_.json()["metadata"]["retrievable"] is True

    def test_update_document_retrievable_failure(self, client_fixture):
        resp = client_fixture.put("/knowledge-flow/v1/document/does_not_exist", json={"retrievable": True})
        assert resp.status_code in (500, 422)
