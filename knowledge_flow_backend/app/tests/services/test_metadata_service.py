from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.features.metadata.service import (
    MetadataNotFound,
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
        dummy_docs = [{"uid": "1"}, {"uid": "2"}]
        monkeypatch.setattr(self.service.metadata_store, "get_all_metadata", lambda filters: dummy_docs)

        result = self.service.get_documents_metadata({"author": "john"})
        assert result.status == "success"
        assert result.documents == dummy_docs

    def test_delete_document_metadata(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: {"uid": "doc1"})
        monkeypatch.setattr(self.service.metadata_store, "delete_metadata", lambda m: True)

        result = self.service.delete_document_metadata("doc1")
        assert result is None

    def test_get_document_metadata(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: {"title": "doc"})

        result = self.service.get_document_metadata("doc1")
        assert result.status == "success"
        assert result.metadata["title"] == "doc"

    def test_update_document_retrievable(self, monkeypatch, dummy_update):
        monkeypatch.setattr(
            self.service.metadata_store,
            "update_metadata_field",
            lambda **kwargs: {"document_uid": "doc1", "retrievable": True}
        )

        result = self.service.update_document_retrievable("doc1", dummy_update)
        assert result.status == "success"

    def test_delete_document_metadata_not_found(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: None)

        with pytest.raises(MetadataNotFound, match="No document found with UID"):
            self.service.delete_document_metadata("invalid_uid")

    def test_get_document_metadata_empty_uid(self):
        with pytest.raises(InvalidMetadataRequest, match="cannot be empty"):
            self.service.get_document_metadata("")

    def test_get_document_metadata_exception(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_metadata_by_uid", lambda uid: 1 / 0)

        with pytest.raises(MetadataUpdateError) as exc:
            self.service.get_document_metadata("doc1")
        assert "Failed to get metadata" in str(exc.value)

    def test_update_document_retrievable_empty_uid(self, dummy_update):
        with pytest.raises(InvalidMetadataRequest, match="cannot be empty"):
            self.service.update_document_retrievable("", dummy_update)

    def test_update_document_retrievable_exception(self, monkeypatch, dummy_update):
        monkeypatch.setattr(self.service.metadata_store, "update_metadata_field", lambda **kwargs: 1 / 0)

        with pytest.raises(MetadataUpdateError) as exc:
            self.service.update_document_retrievable("doc1", dummy_update)
        assert "Failed to update retrievable" in str(exc.value)

    def test_get_documents_metadata_empty_filter(self, monkeypatch):
        monkeypatch.setattr(self.service.metadata_store, "get_all_metadata", lambda filters: [])

        result = self.service.get_documents_metadata({})
        assert result.documents == []
        assert result.status == "success"
