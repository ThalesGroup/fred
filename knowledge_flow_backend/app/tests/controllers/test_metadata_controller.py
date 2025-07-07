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

"""Test suite for the MetadataController API endpoints."""

from fastapi.testclient import TestClient
from fastapi import status
import pytest
from opensearchpy import OpenSearch

# pylint: disable=W0613
# pylint: disable=R0917
# pylint: disable=R0913


@pytest.mark.metadata_storage_type(type="opensearch")
@pytest.mark.vector_storage_type(type="opensearch")
@pytest.mark.content_storage_type(type="minio")
class TestMetadataController:
    """
    Test suite for the MetadataController API endpoints.
    This class contains integration tests for the document metadata management endpoints,
    including operations for retrieving, filtering, updating, and deleting document metadata
    in the knowledge base. The tests use fixtures for sample documents and OpenSearch
    integration, and verify correct API behavior and error handling for various scenarios.
    """

    @pytest.fixture
    def inject_refresh_in_index(self, monkeypatch):
        """
        Monkeypatches the OpenSearch.index method to always include 'refresh=True' in
        its keyword arguments.
        This is useful in tests to ensure that indexed documents are immediately available
        for search operations.

        Args:
            monkeypatch: The pytest monkeypatch fixture used to modify the behavior of
                         OpenSearch.index.
        """

        original_search = OpenSearch.index

        def patched_index(self, *args, **kwargs):
            kwargs.setdefault("refresh", True)
            return original_search(self, *args, **kwargs)

        monkeypatch.setattr(OpenSearch, "index", patched_index)

    @pytest.fixture
    def document1(self):
        """
        Returns a dictionary representing metadata for a sample document.

        Returns:
            dict: A dictionary containing metadata fields
        """

        return {
            "document_uid": "doc-01",
            "title": "Example Document",
            "author": "Jane Doe",
            "created": "2024-06-01T12:00:00Z",
            "modified": "2024-06-02T15:30:00Z",
            "last_modified_by": "None",
            "category": "None",
            "subject": "None",
            "keywords": "None",
            "document_name": "document.docx",
            "front_metadata": {"agent_name": "Georges"},
            "retrievable": True,
            "date_added_to_kb": "2025-05-23T14:36:31.362872",
        }

    @pytest.fixture
    def document2(self):
        """
        Returns a dictionary representing metadata for a sample document.

        Returns:
            dict: A dictionary containing metadata fields
        """

        return {
            "document_uid": "doc001",
            "title": "AI Revolution",
            "author": "Ada Lovelace",
            "created": "2023-01-15T09:00:00Z",
            "modified": "2023-02-10T10:30:00Z",
            "last_modified_by": "Alan Turing",
            "category": "Technology",
            "subject": "Artificial Intelligence",
            "keywords": "AI,ML,Deep Learning",
            "document_name": "ai_revolution.pdf",
            "front_metadata": {"agent_name": "Marvin"},
            "retrievable": False,
            "date_added_to_kb": "2023-03-01T12:00:00.000000",
        }

    def test_delete_metadata_found(self, client: TestClient, opensearch_metadata_store, document1, minio_content_store) -> None:
        """
        Test that deleting an existing metadata document returns a 200 OK status.
        This test saves a metadata document to the OpenSearch metadata store, then sends
        a DELETE request
        to the API endpoint for that document. It asserts that the response status code
        is 200, indicating
        successful deletion.

        Args:
            client (TestClient): The test client used to make HTTP requests to the API.
            opensearch_metadata_store: The metadata store fixture for interacting with OpenSearch.
            document1: The metadata document to be saved and then deleted.
        Asserts:
            The response status code is HTTP 200 OK after deletion.
        """

        opensearch_metadata_store.save_metadata(document1)
        response = client.delete(f"/knowledge/v1/document/{document1.get('document_uid')}")
        assert response.status_code == status.HTTP_200_OK

    def test_delete_metadata_not_found(self, client: TestClient, opensearch_metadata_store) -> None:
        """
        Test that attempting to delete metadata for a non-existent document returns a
        500 Internal Server Error.

        Args:
            client (TestClient): The test client used to make HTTP requests to the API.
            opensearch_metadata_store: The fixture or mock representing the metadata store
            backend.
        Asserts:
            The response status code is 500 (Internal Server Error) when the specified
            document is not found.
        """

        response = client.delete("/knowledge/v1/document/test")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_get_documents_metadata(
        self,
        client: TestClient,
        opensearch_metadata_store,
        inject_refresh_in_index,
        document1,
        document2,
    ):
        """
        Test the retrieval of document metadata via the API endpoint.
        This test saves two documents' metadata to the OpenSearch metadata store,
        then sends a POST request to the '/knowledge/v1/documents/metadata' endpoint.
        It asserts that the response status is 200 OK, the response status is 'success',
        and that the returned documents list contains exactly two documents.

        Args:
            client (TestClient): The test client for making API requests.
            opensearch_metadata_store: The metadata store for saving and retrieving
            document metadata.
            inject_refresh_in_index: Fixture to ensure index is refreshed after saving
            metadata.
            document1: The first document metadata to be saved.
            document2: The second document metadata to be saved.
        """

        opensearch_metadata_store.save_metadata(document1)
        opensearch_metadata_store.save_metadata(document2)
        response = client.post("/knowledge/v1/documents/metadata", json={})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert len(data["documents"]) == 2

    def test_get_documents_metadata_with_filters(
        self,
        client: TestClient,
        opensearch_metadata_store,
        inject_refresh_in_index,
        document1,
        document2,
    ):
        """
        Test the retrieval of document metadata with applied filters.
        This test saves two documents' metadata to the OpenSearch metadata store,
        applies a filter on the 'agent_name' field, and verifies that only the
        matching document is returned by the API endpoint.

        Args:
            client (TestClient): The test client for making HTTP requests.
            opensearch_metadata_store: The metadata store for saving and retrieving document
            metadata.
            inject_refresh_in_index: Fixture to ensure index refresh between operations.
            document1: The first document metadata to be saved.
            document2: The second document metadata to be saved.
        Asserts:
            - The response status code is HTTP 200 OK.
            - The response status is 'success'.
            - Only one document is returned matching the filter criteria.
        """

        opensearch_metadata_store.save_metadata(document1)
        opensearch_metadata_store.save_metadata(document2)
        filters = {"agent_name": "Georges"}
        response = client.post("/knowledge/v1/documents/metadata", json=filters)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert len(data["documents"]) == 1

    def test_get_documents_metadata_failure(self, client: TestClient, monkeypatch):
        """
        Test that the /knowledge/v1/documents/metadata endpoint returns a 500 Internal
        Server Errorand the appropriate error message when the
        MetadataService.get_documents_metadata methodnraises an exception.
        This test uses monkeypatch to simulate a database error and verifies that the
        API responds with the correct status code and error detail in the response.

        Args:
            client (TestClient): The test client for making API requests.
            monkeypatch: The pytest monkeypatch fixture for patching methods.

        Asserts:
            - The response status code is HTTP 500 Internal Server Error.
            - The response contains the expected error message in the "detail" field.
        """

        def raise_exc(*args, **kwargs):
            raise Exception("DB error")

        monkeypatch.setattr(
            "app.services.metadata_service.MetadataService.get_documents_metadata",
            raise_exc,
        )
        response = client.post("/knowledge/v1/documents/metadata", json={})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to fetch document metadata" in response.json()["detail"]

    def test_get_document_metadata(self, client: TestClient, opensearch_metadata_store, document1):
        """
        Test the retrieval of document metadata via the API endpoint.
        This test saves a sample document's metadata to the OpenSearch metadata store,
        then sends a GET request to the document metadata endpoint. It asserts that:
        - The response status code is 200 (OK).
        - The response JSON indicates success.
        - The returned metadata matches the expected document UID, title, author, and
        document name.

        Args:
            client (TestClient): The FastAPI test client used to make requests.
            opensearch_metadata_store: The metadata store fixture for saving and retrieving
            metadata.
            document1: The sample document metadata to be saved and retrieved.
        """

        opensearch_metadata_store.save_metadata(document1)
        response = client.get(f"/knowledge/v1/document/{document1.get('document_uid')}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["metadata"]["document_uid"] == f"{document1.get('document_uid')}"
        assert data["metadata"]["title"] == "Example Document"
        assert data["metadata"]["author"] == "Jane Doe"
        assert data["metadata"]["document_name"] == "document.docx"

    def test_update_document_retrievable(self, client: TestClient, opensearch_metadata_store, document1):
        """
        Test that updating a document's 'retrievable' metadata via the API works as expected.
        This test saves a document to the metadata store, updates its 'retrievable' field to
        True using a PUT request, and verifies that:
          - The response status code is 200 OK.
          - The response JSON indicates success.
          - A subsequent GET request returns the document with 'retrievable' set to True in
          its metadata.

        Args:
            client (TestClient): The test client for making API requests.
            opensearch_metadata_store: The metadata store fixture for saving and retrieving
            documents.
            document1: The document fixture to be used in the test.
        """

        opensearch_metadata_store.save_metadata(document1)
        response = client.put(
            f"/knowledge/v1/document/{document1.get('document_uid')}",
            json={"retrievable": True},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        get_resp = client.get(f"/knowledge/v1/document/{document1.get('document_uid')}")
        assert get_resp.json()["metadata"]["retrievable"] is True

    def test_update_document_retrievable_failure(self, client: TestClient):
        """
        Test that updating the 'retrievable' attribute of a non-existent document returns
        an error.
        This test sends a PUT request to update the 'retrievable' status of a document
        with an ID that does not exist.
        It asserts that the response status code is either 500 (Internal Server Error) or
        422 (Unprocessable Entity),
        indicating that the operation failed as expected.

        Args:
            client (TestClient): The test client used to send HTTP requests to the application.
        Assertions:
            - Sends a PUT request to update the 'retrievable' status of a document with an ID
            that does not exist.
            - Asserts that the response status code is either 500 (Internal Server Error) or
            422 (Unprocessable Entity),
        """

        response = client.put("/knowledge/v1/document/doesnotexist", json={"retrievable": True})
        assert response.status_code in (500, 422)
