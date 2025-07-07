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

from fastapi.testclient import TestClient
from fastapi import status
import pytest
from opensearchpy import OpenSearch


@pytest.mark.content_storage_type(type="minio")
@pytest.mark.metadata_storage_type(type="opensearch")
class TestMetadataController:
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """Create test Markdown files in temporary directories.
        This fixture creates test Markdown files with sample content in both input and output directories
        under a randomly generated document UID.

        Args:
            tmp_path (Path): Temporary directory path provided by pytest fixture
        Returns:
            dict: Contains:
                - document_uid (str): Unique identifier for the document
                - document_dir (Path): Path to the document's root directory
        """

        document_uid = "doc-01"
        target_input_dir = tmp_path / document_uid / "input"
        target_output_dir = tmp_path / document_uid / "output"
        target_input_dir.mkdir(parents=True, exist_ok=True)
        target_output_dir.mkdir(parents=True, exist_ok=True)
        markdown_content = """
        # Main Title

        This is a dummy Markdown file for testing purposes.

        ## Subtitle

        - Item 1
        - Item 2
        - Item 3

        **Bold text** and *italic text*.

        [A link](https://example.com)

        > This is a blockquote.

        """
        file_output_path = target_output_dir / "output.md"
        with open(file_output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        file_input_path = target_input_dir / "document.md"
        with open(file_input_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        return {"document_uid": document_uid, "document_dir": tmp_path / document_uid}

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
            "document_name": "document.md",
            "front_metadata": {"agent_name": "Georges"},
            "retrievable": True,
            "date_added_to_kb": "2025-05-23T14:36:31.362872",
        }

    def test_get_markdown_preview(self, client: TestClient, markdown_file, safe_minio_content_store):
        """Test the markdown preview endpoint functionality.
        This test verifies that the /knowledge/v1/markdown/{document_uid} endpoint correctly
        returns the content of a markdown file stored in MinIO.

        Args:
            client (TestClient): FastAPI test client instance
            markdown_file (dict): Fixture containing markdown file metadata
            minio_content_store (MinioContentStore): Fixture for MinIO content store operations
        """

        safe_minio_content_store.save_content(document_uid=markdown_file.get("document_uid"), document_dir=markdown_file.get("document_dir"))
        response = client.get(
            f"/knowledge/v1/markdown/{markdown_file.get('document_uid')}",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("content") is not None
        assert "# Main Title" in data.get("content")
        assert "This is a dummy Markdown file for testing purposes." in data.get("content")

    def test_get_markdown_preview_not_found(self, client: TestClient):
        """
        Test GET endpoint for markdown preview with non-existent UID.
        Tests that the /knowledge/v1/markdown/{uid} endpoint returns a 404 HTTP status
        when requesting a preview for a non-existent markdown document.
        Args:
            client (TestClient): FastAPI test client fixture
        """

        response = client.get(
            "/knowledge/v1/markdown/non_existent_uid",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_markdown_preview_failure(self, client: TestClient, monkeypatch):
        """
        Test the failure case of markdown preview endpoint.
        This test verifies that the endpoint properly handles and returns errors when the markdown
        preview service fails. It uses monkeypatch to simulate a service failure.

        Args:
            client (TestClient): The test client instance used for making HTTP requests
            monkeypatch: Pytest fixture for modifying objects during testing
        """

        def raise_exc(*args, **kwargs):
            raise Exception("Internal server error")

        monkeypatch.setattr(
            "knowledge_flow_app.services.content_service.ContentService.get_markdown_preview",
            raise_exc,
        )
        response = client.get("/knowledge/v1/markdown/test")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Internal server error" in response.json()["detail"]

    def test_get_markdown_preview_value_error(self, client: TestClient, monkeypatch):
        """Test the behavior of markdown preview endpoint when a ValueError occurs.
        This test ensures that when the ContentService.get_markdown_preview method raises
        a ValueError, the API endpoint properly handles it and returns a 400 Bad Request
        response with the appropriate error message.

        Args:
            client (TestClient): FastAPI test client instance
            monkeypatch: Pytest fixture for mocking/patching objects

        """

        def raise_exc(*args, **kwargs):
            raise ValueError("Value error")

        monkeypatch.setattr(
            "knowledge_flow_app.services.content_service.ContentService.get_markdown_preview",
            raise_exc,
        )
        response = client.get("/knowledge/v1/markdown/test")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json().get("detail") == "Value error"

    def test_download_document_success(self, client: TestClient, markdown_file, minio_content_store, opensearch_metadata_store, document1):
        """Test successful document download functionality.
        This test verifies that a document can be successfully downloaded through the API endpoint.

        Args:
            client (TestClient): FastAPI test client instance
            markdown_file (dict): Fixture containing markdown file details
            minio_content_store (MinioContentStore): MinIO storage interface
            opensearch_metadata_store (OpenSearchMetadataStore): OpenSearch metadata storage interface
            document1 (dict): Fixture containing document metadata
        """

        minio_content_store.save_content(document_uid=markdown_file.get("document_uid"), document_dir=markdown_file.get("document_dir"))
        opensearch_metadata_store.save_metadata(document1)

        response = client.get(f"/knowledge/v1/raw_content/{markdown_file.get('document_uid')}")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert response.headers["content-disposition"] == 'attachment; filename="document.md"'
        assert isinstance(response.content, bytes)

    def test_download_document_not_found(self, client: TestClient):
        """
        Test the behavior when attempting to download a non-existent document.
        This test verifies that the API returns a 404 Not Found status code
        when trying to access a document with an invalid UID.

        Args:
            client (TestClient): FastAPI test client instance
        """

        response = client.get("/knowledge/v1/raw_content/non_existent_uid")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json().get("detail") == "No metadata found for document non_existent_uid"

    def test_download_document_value_error(self, client: TestClient, monkeypatch):
        """Test the download_document endpoint when a ValueError occurs.
        This test case verifies that when the content service raises a ValueError,
        the endpoint returns a 400 Bad Request status code with the error message.

        Args:
            client (TestClient): The FastAPI test client
            monkeypatch: Pytest fixture for mocking/patching functions
        """

        def raise_exc(*args, **kwargs):
            raise ValueError("Value error")

        monkeypatch.setattr(
            "knowledge_flow_app.services.content_service.ContentService.get_original_content",
            raise_exc,
        )
        response = client.get("/knowledge/v1/raw_content/test")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json().get("detail") == "Value error"

    def test_download_document_failure(self, client: TestClient, monkeypatch):
        """Test the failure case of document download endpoint.
        This test verifies that when an exception occurs during document download,
        the API returns a 500 Internal Server Error status code.

        Args:
            client (TestClient): FastAPI test client fixture
            monkeypatch: Pytest fixture for mocking/patching
        """

        def raise_exc(*args, **kwargs):
            raise Exception("Internal server error")

        monkeypatch.setattr(
            "knowledge_flow_app.services.content_service.ContentService.get_original_content",
            raise_exc,
        )
        response = client.get("/knowledge/v1/raw_content/test")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Internal server error" in response.json()["detail"]
