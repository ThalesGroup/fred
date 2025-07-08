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
Test suite for LocalMetadataStore in local_metadata_store.py.

Covers:
- Saving, retrieving, updating, and deleting metadata entries.
- Error handling for missing or unknown document UIDs.
- Filter matching with nested structures.

All tests use a temporary JSON file in a clean temp directory.
"""

# pylint: disable=redefined-outer-name

import pytest

from app.core.stores.metadata.local_metadata_store import LocalMetadataStore


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def metadata_store(tmp_path):
    """Fixture: creates a LocalMetadataStore with a temporary JSON file."""
    json_path = tmp_path / "metadata.json"
    return LocalMetadataStore(json_path)


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_save_and_get_metadata(metadata_store):
    """Test: save and retrieve metadata by UID."""
    metadata = {"document_uid": "doc1", "name": "Test Doc"}
    metadata_store.save_metadata(metadata)
    result = metadata_store.get_metadata_by_uid("doc1")
    assert result == metadata


def test_update_metadata_field(metadata_store):
    """Test: update a single metadata field."""
    metadata_store.save_metadata({"document_uid": "doc2", "field1": "val1"})
    updated = metadata_store.update_metadata_field("doc2", "field1", "val2")
    assert updated["field1"] == "val2"
    reloaded = metadata_store.get_metadata_by_uid("doc2")
    assert reloaded["field1"] == "val2"


def test_get_all_metadata_with_filter(metadata_store):
    """Test: get all metadata matching nested filter."""
    metadata_store.save_metadata({"document_uid": "doc3", "frontend_metadata": {"agent_name": "alice"}})
    result = metadata_store.get_all_metadata({"frontend_metadata": {"agent_name": "alice"}})
    assert len(result) == 1
    assert result[0]["document_uid"] == "doc3"


# ----------------------------
# ❌ Error Cases
# ----------------------------


def test_save_metadata_missing_uid(metadata_store):
    """Test: raises ValueError if metadata has no document_uid."""
    with pytest.raises(ValueError, match="document_uid"):
        metadata_store.save_metadata({"name": "Missing UID"})


def test_update_metadata_uid_not_found(metadata_store):
    """Test: raises ValueError when updating non-existent UID."""
    with pytest.raises(ValueError, match="No document found"):
        metadata_store.update_metadata_field("missing", "field", "value")


def test_delete_metadata_uid_not_found(metadata_store):
    """Test: raises ValueError when deleting non-existent UID."""
    with pytest.raises(ValueError, match="No document found"):
        metadata_store.delete_metadata({"document_uid": "ghost"})


def test_delete_metadata_missing_uid(metadata_store):
    """Test: raises ValueError if document_uid is missing in deletion."""
    with pytest.raises(ValueError, match="document_uid"):
        metadata_store.delete_metadata({"name": "No UID"})


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_overwrite_existing_metadata(metadata_store):
    """Test: save_metadata replaces entry with same UID."""
    original = {"document_uid": "doc5", "x": 1}
    updated = {"document_uid": "doc5", "x": 2}
    metadata_store.save_metadata(original)
    metadata_store.save_metadata(updated)
    result = metadata_store.get_metadata_by_uid("doc5")
    assert result["x"] == 2


def test_delete_existing_metadata(metadata_store):
    """Test: delete_metadata removes correct document."""
    metadata_store.save_metadata({"document_uid": "doc6", "name": "ToDelete"})
    metadata_store.delete_metadata({"document_uid": "doc6"})
    assert metadata_store.get_metadata_by_uid("doc6") is None


def test_match_nested_with_non_dict(metadata_store):
    """Test: _match_nested returns False if nested filter expects a dict but finds another type."""
    metadata_store.save_metadata({"document_uid": "doc_nested_type", "frontend_metadata": "not-a-dict"})
    result = metadata_store.get_all_metadata({"frontend_metadata": {"agent_name": "alice"}})
    assert result == []


def test_match_nested_with_value_mismatch(metadata_store):
    """Test: _match_nested returns False if a final value does not match."""
    metadata_store.save_metadata({"document_uid": "doc_mismatch", "author": "bob"})
    result = metadata_store.get_all_metadata({"author": "alice"})
    assert result == []


def test_load_returns_empty_if_file_missing(tmp_path):
    """Test: _load returns empty list if the metadata file is missing."""
    json_path = tmp_path / "missing.json"
    store = LocalMetadataStore(json_path)
    json_path.unlink()
    assert store._load() == []
