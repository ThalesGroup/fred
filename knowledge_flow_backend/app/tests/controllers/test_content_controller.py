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
"""Integration‑tests for the Content/Metadata controllers **using only the local
storage back‑ends** (no MinIO, no OpenSearch).
"""

from fastapi.testclient import TestClient
from fastapi import status
import pytest

from app.features.content.service import ContentService


# Tell conftest.py which back‑ends to spin‑up
@pytest.mark.content_storage_type(type="local")
@pytest.mark.metadata_storage_type(type="local")
class TestContentController:
    """End‑to‑end tests with LocalContentStore + LocalMetadataStore."""

    # ─────────────────────────────── fixtures ──────────────────────────────
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """Create a tiny markdown *input/output* tree under a random tmp dir."""
        document_uid = "doc-01"
        doc_root = tmp_path / document_uid
        input_dir = doc_root / "input"
        output_dir = doc_root / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        md = (
            """
            # Main Title

            This is a dummy Markdown file for testing purposes.

            ## Subtitle
            - Item 1
            - Item 2
            - Item 3

            **Bold text** and *italic text*.
            """
        ).strip()

        (input_dir / "document.md").write_text(md, encoding="utf-8")
        (output_dir / "output.md").write_text(md, encoding="utf-8")

        return {"document_uid": document_uid, "document_dir": doc_root}

    @pytest.fixture
    def document1(self):
        """Sample metadata matching *markdown_file*."""
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

    # ─────────────────────────────── tests ────────────────────────────────
    def test_get_markdown_preview(self, client_fixture: TestClient, markdown_file, content_store):
        """The `/markdown/{uid}` endpoint should return the rendered markdown."""
        content_store.save_content(markdown_file["document_uid"], markdown_file["document_dir"])

        resp = client_fixture.get(f"/knowledge-flow/v1/markdown/{markdown_file['document_uid']}")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()["content"]
        assert "# Main Title" in body
        assert "dummy Markdown file" in body

    def test_get_markdown_preview_not_found(self, client_fixture: TestClient):
        resp = client_fixture.get("/knowledge-flow/v1/markdown/does_not_exist")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_markdown_preview_failure(self, client_fixture: TestClient, monkeypatch):
        monkeypatch.setattr(ContentService, "get_markdown_preview", lambda *_: (_ for _ in ()).throw(Exception("boom")))
        resp = client_fixture.get("/knowledge-flow/v1/markdown/whatever")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_get_markdown_preview_value_error(self, client_fixture: TestClient, monkeypatch):
        monkeypatch.setattr(ContentService, "get_markdown_preview", lambda *_: (_ for _ in ()).throw(ValueError("oops")))
        resp = client_fixture.get("/knowledge-flow/v1/markdown/whatever")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.json()["detail"] == "oops"

    def test_download_document_success(self, client_fixture, markdown_file, content_store, metadata_store, document1):
        """Happy‑path: raw download available from local stores."""
        content_store.save_content(markdown_file["document_uid"], markdown_file["document_dir"])
        metadata_store.save_metadata(document1)

        resp = client_fixture.get(f"/knowledge-flow/v1/raw_content/{markdown_file['document_uid']}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert resp.headers["content-disposition"].endswith('filename="document.md"')

    def test_download_document_not_found(self, client_fixture: TestClient):
        resp = client_fixture.get("/knowledge-flow/v1/raw_content/does_not_exist")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No metadata found" in resp.json()["detail"]

    def test_download_document_value_error(self, client_fixture: TestClient, monkeypatch):
        monkeypatch.setattr(ContentService, "get_original_content", lambda *_: (_ for _ in ()).throw(ValueError("bad")))
        resp = client_fixture.get("/knowledge-flow/v1/raw_content/whatever")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.json()["detail"] == "bad"

    def test_download_document_failure(self, client_fixture: TestClient, monkeypatch):
        monkeypatch.setattr(ContentService, "get_original_content", lambda *_: (_ for _ in ()).throw(Exception("boom")))
        resp = client_fixture.get("/knowledge-flow/v1/raw_content/whatever")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert resp.json()["detail"] == "Internal server error"
