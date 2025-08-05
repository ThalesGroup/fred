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

from types import SimpleNamespace
import pytest
from app.common.document_structures import DocumentMetadata, SourceType
from app.features.metadata.service import (
    MetadataUpdateError,
    InvalidMetadataRequest,
    MetadataService,
)


@pytest.fixture
def dummy_update():
    return SimpleNamespace(retrievable=True)


class TestMetadataService:
    def setup_method(self):
        self.service = MetadataService()

    def test_get_documents_metadata(self, monkeypatch):
        dummy_docs = [
            DocumentMetadata(source_type=SourceType("push"), document_uid="1", document_name="doc1.md"),
            DocumentMetadata(source_type=SourceType("push"), document_uid="2", document_name="doc2.md"),
        ]
        monkeypatch.setattr(self.service.metadata_store, "get_all_metadata", lambda filters: dummy_docs)

        result = self.service.get_documents_metadata({"author": "john"})
        assert isinstance(result, list)
        assert result == dummy_docs

    def test_get_document_metadata(self, monkeypatch):
        doc = DocumentMetadata(source_type=SourceType("push"), document_uid="doc1", document_name="doc.md", title="doc")
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: doc)

        result = self.service.get_document_metadata("doc1")
        assert isinstance(result, DocumentMetadata)
        assert result.title == "doc"

    def test_get_document_metadata_empty_uid(self):
        with pytest.raises(InvalidMetadataRequest, match="cannot be empty"):
            self.service.get_document_metadata("")

    def test_get_document_metadata_exception(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: 1 / 0)

        with pytest.raises(MetadataUpdateError) as exc:
            self.service.get_document_metadata("doc1")
        assert "Failed to get metadata" in str(exc.value)

    def test_get_documents_metadata_empty_filter(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_all_metadata", lambda filters: [])

        result = self.service.get_documents_metadata({})
        assert isinstance(result, list)
        assert result == []
