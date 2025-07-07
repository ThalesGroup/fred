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
Test suite for OpenSearchMetadataStore in opensearch_metadata_store.py.

Covers:
- Metadata read/write/update/delete operations
- Filters and existence checks
- Error handling when OpenSearch raises exceptions

Mocks OpenSearch client entirely to avoid real HTTP calls.
"""

# Disable many pylint rules as we need to redifined OpenSearch client classes and methods
# almost everywhere for mock purposes ...
#
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=redefined-builtin
# pylint: disable=too-few-public-methods
# pylint: disable=redefined-builtin

import pytest
from opensearchpy.exceptions import OpenSearchException

from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore
import knowledge_flow_app.core.stores.metadata.opensearch_metadata_store as oms


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def mock_opensearch(monkeypatch):
    """Fixture: patches OpenSearch class to return a mock client."""

    class MockIndices:
        def exists(self, index):
            return False

        def create(self, index):
            return {"acknowledged": True}

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()
            self.store = {}
            self.logs = []

        def get(self, index, id):
            return {"found": id in self.store, "_source": self.store.get(id, {})}

        def exists(self, index, id):
            return id in self.store

        def index(self, index, id, body):
            self.store[id] = body
            return {"result": "created"}

        def update(self, index, id, body):
            if id not in self.store:
                raise FileNotFoundError("Not found")
            self.store[id].update(body["doc"])
            return {"result": "updated"}

        def update_by_query(self, index, body):
            return {"updated": 1}

        def search(self, index, body, _source=None, size=None):
            return {"hits": {"hits": [{"_source": doc} for doc in self.store.values()]}}

        def delete(self, index, id):
            self.store.pop(id, None)

        def delete_by_query(self, index, body):
            return {"deleted": 1}

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    return MockClient()


@pytest.fixture
def metadata_store(mock_opensearch):
    """Fixture: returns a store instance with mocked client."""
    return OpenSearchMetadataStore(host="localhost", metadata_index_name="meta", vector_index_name="vec")


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_save_and_get_metadata(metadata_store):
    metadata = {"document_uid": "doc1", "front_metadata": {"x": 1}}
    metadata_store.save_metadata(metadata)
    result = metadata_store.get_metadata_by_uid("doc1")
    assert result["x"] == 1


def test_uid_exists_true(metadata_store):
    metadata = {"document_uid": "doc2"}
    metadata_store.save_metadata(metadata)
    assert metadata_store.uid_exists("doc2")


def test_update_metadata_field(metadata_store):
    metadata_store.save_metadata({"document_uid": "doc3", "field": "old"})
    result = metadata_store.update_metadata_field("doc3", "field", "new")
    assert result["metadata_index_response"]["result"] == "updated"


def test_get_all_metadata(metadata_store):
    metadata_store.save_metadata({"document_uid": "doc4", "front_metadata": {"author": "alice"}})
    results = metadata_store.get_all_metadata({"author": "alice"})
    assert len(results) >= 1


def test_delete_metadata(metadata_store):
    metadata_store.save_metadata({"document_uid": "doc5"})
    metadata_store.delete_metadata({"document_uid": "doc5"})
    assert not metadata_store.uid_exists("doc5")


def test_get_all_metadata_with_match_all(monkeypatch):
    """Test: get_all_metadata handles empty filter with match_all query."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def search(self, *args, **kwargs):
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "document_uid": "doc1",
                                "document_name": "doc.md",
                                "front_metadata": {"author": "alice"},
                            }
                        }
                    ]
                }
            }

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    result = store.get_all_metadata({})
    assert any(doc["author"] == "alice" for doc in result)


# ----------------------------
# ❌ Error Cases
# ----------------------------


def test_save_metadata_exception(monkeypatch, metadata_store):
    def failing_write(*args, **kwargs):
        raise OpenSearchException("failure")

    monkeypatch.setattr(metadata_store, "write_metadata", failing_write)

    with pytest.raises(ValueError):
        metadata_store.save_metadata({"document_uid": "fail"})


def test_delete_metadata_missing_uid(metadata_store):
    with pytest.raises(ValueError, match="document_uid"):
        metadata_store.delete_metadata({"not_uid": "oops"})


def test_write_metadata_opensearch_exception(monkeypatch):
    """Test: write_metadata raises ValueError on OpenSearchException."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def index(self, *args, **kwargs):
            raise OpenSearchException("fail")

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    with pytest.raises(ValueError, match="Failed to write metadata"):
        store.write_metadata("uid", {"some": "data"})


def test_update_metadata_field_exception(monkeypatch):
    """Test: update_metadata_field raises exception on failure."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def update(self, *a, **k):
            raise OpenSearchException("fail update")

        def update_by_query(self, *a, **k):
            return {}

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    with pytest.raises(Exception, match="fail update"):
        store.update_metadata_field("uid", "field", "val")


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_index_already_exists(monkeypatch):
    """Test: logs warning when index already exists."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

        def create(self, index):
            raise OpenSearchException("should not be called")

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

    monkeypatch.setattr(oms, "OpenSearch", MockClient)
    OpenSearchMetadataStore("localhost", "meta", "vec")


def test_get_metadata_by_uid_exception(monkeypatch):
    """Test: get_metadata_by_uid returns {} on exception."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def get(self, *args, **kwargs):
            raise OpenSearchException("fail")

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    assert store.get_metadata_by_uid("uid") == {}


def test_uid_exists_exception(monkeypatch):
    """Test: uid_exists returns False on exception."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def exists(self, *args, **kwargs):
            raise OpenSearchException("fail")

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    assert store.uid_exists("uid") is False


def test_get_all_metadata_exception(monkeypatch):
    """Test: get_all_metadata returns [] on OpenSearch failure."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def search(self, *args, **kwargs):
            raise OpenSearchException("boom")

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    assert not store.get_all_metadata({})


def test_get_metadata_by_uid_not_found(monkeypatch):
    """Test: get_metadata_by_uid returns {} if document is not found (found=False)."""

    class MockIndices:
        def exists(self, index=None, **kwargs):
            return True

    class MockClient:
        def __init__(self, *args, **kwargs):
            self.indices = MockIndices()

        def get(self, index, id):
            return {"found": False}

    monkeypatch.setattr("knowledge_flow_app.stores.metadata.opensearch_metadata_store.OpenSearch", MockClient)
    store = OpenSearchMetadataStore("localhost", "meta", "vec")
    assert store.get_metadata_by_uid("unknown") == {}
