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

"""
Test suite for MetadataService in metadata_service.py.

Covers:
- Retrieving all documents metadata
- Retrieving single document metadata
- Deleting metadata
- Updating 'retrievable' field

Error handling is tested for missing UIDs and unexpected exceptions.
Mocks are used to simulate metadata_store behavior.
"""

# pylint: disable=redefined-outer-name

from types import SimpleNamespace
from fastapi import HTTPException
from app.features.metadata.service import MetadataService
import pytest


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def dummy_update():
    """
    Fixture: provides a mock update payload with 'retrievable=True'.
    """
    return SimpleNamespace(retrievable=True)


@pytest.fixture
def service():
    """
    Fixture: returns a fresh instance of MetadataService.
    """
    return MetadataService()


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_get_documents_metadata(service, monkeypatch):
    """
    Test: returns documents when metadata_store provides results.
    """
    dummy_docs = [{"uid": "1"}, {"uid": "2"}]
    monkeypatch.setattr(service.metadata_store, "get_all_metadata", lambda filters: dummy_docs)

    result = service.get_documents_metadata({"author": "john"})
    assert result["status"] == "success"
    assert result["documents"] == dummy_docs


def test_delete_document_metadata(service, monkeypatch):
    """
    Test: deletes metadata when UID is found in store.
    """
    dummy_metadata = {"uid": "doc1"}
    monkeypatch.setattr(service.metadata_store, "get_metadata_by_uid", lambda uid: dummy_metadata)
    monkeypatch.setattr(service.metadata_store, "delete_metadata", lambda m: True)

    result = service.delete_document_metadata("doc1")
    assert result is None


def test_get_document_metadata(service, monkeypatch):
    """
    Test: retrieves document metadata for a valid UID.
    """
    monkeypatch.setattr(service.metadata_store, "get_metadata_by_uid", lambda uid: {"title": "doc"})

    result = service.get_document_metadata("doc1")
    assert result["status"] == "success"
    assert result["metadata"]["title"] == "doc"


def test_update_document_retrievable(service, monkeypatch, dummy_update):
    """
    Test: updates retrievable flag and returns success response.
    """
    monkeypatch.setattr(service.metadata_store, "update_metadata_field", lambda **kwargs: "OK")

    result = service.update_document_retrievable("doc1", dummy_update)
    assert result["status"] == "success"
    assert result["response"] == "OK"


# ----------------------------
# ❌ Failure Cases
# ----------------------------


def test_delete_document_metadata_not_found(service, monkeypatch):
    """
    Test: raises ValueError when UID does not exist.
    """
    monkeypatch.setattr(service.metadata_store, "get_metadata_by_uid", lambda uid: None)

    with pytest.raises(ValueError, match="No document found with UID"):
        service.delete_document_metadata("invalid_uid")


def test_get_document_metadata_empty_uid(service):
    """
    Test: raises ValueError when UID is empty.
    """
    with pytest.raises(ValueError, match="cannot be empty"):
        service.get_document_metadata("")


def test_get_document_metadata_exception(service, monkeypatch):
    """
    Test: converts unexpected internal error into HTTP 500.
    """

    def faulty_method(uid):
        raise ZeroDivisionError()

    monkeypatch.setattr(service.metadata_store, "get_metadata_by_uid", faulty_method)

    with pytest.raises(HTTPException) as exc:
        service.get_document_metadata("doc1")
    assert exc.value.status_code == 500


def test_update_document_retrievable_empty_uid(service, dummy_update):
    """
    Test: raises ValueError when UID is empty.
    """
    with pytest.raises(ValueError, match="cannot be empty"):
        service.update_document_retrievable("", dummy_update)


def test_update_document_retrievable_exception(service, monkeypatch, dummy_update):
    """
    Test: converts internal update exception into HTTP 500.
    """

    def faulty_update(**kwargs):
        raise ZeroDivisionError()

    monkeypatch.setattr(service.metadata_store, "update_metadata_field", faulty_update)

    with pytest.raises(HTTPException) as exc:
        service.update_document_retrievable("doc1", dummy_update)
    assert exc.value.status_code == 500


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_get_documents_metadata_empty_filter(service, monkeypatch):
    """
    Test: handles empty result from metadata_store with empty filter.
    """
    monkeypatch.setattr(service.metadata_store, "get_all_metadata", lambda filters: [])

    result = service.get_documents_metadata({})
    assert result["documents"] == []
    assert result["status"] == "success"
