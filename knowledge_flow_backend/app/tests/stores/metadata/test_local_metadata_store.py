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
"""

import pytest
from app.common.document_structures import DocumentMetadata, SourceType
from app.core.stores.metadata.duckdb_metadata_store import DuckdbMetadataStore


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def metadata_store(tmp_path):
    json_path = tmp_path / "tmp.db"
    return DuckdbMetadataStore(json_path)


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_save_and_get_metadata(metadata_store):
    metadata = DocumentMetadata(source_type=SourceType("push"), document_uid="doc1", document_name="Test Doc")
    metadata_store.save_metadata(metadata)
    result = metadata_store.get_metadata_by_uid("doc1")
    assert result == metadata


def test_update_metadata_field(metadata_store):
    metadata = DocumentMetadata(source_type=SourceType("push"), document_uid="doc2", document_name="Doc2", author="Old Author")
    metadata_store.save_metadata(metadata)

    updated = metadata_store.update_metadata_field("doc2", "author", "New Author")
    assert updated.author == "New Author"

    reloaded = metadata_store.get_metadata_by_uid("doc2")
    assert reloaded.author == "New Author"


def test_get_all_metadata_with_filter(metadata_store):
    metadata = DocumentMetadata(
        source_type=SourceType("push"),
        document_uid="doc3",
        document_name="Nested",
        title="X",
        keywords="Y",
        category="Z",
    )
    metadata_store.save_metadata(metadata)

    result = metadata_store.get_all_metadata({"title": "X"})
    assert len(result) == 1
    assert result[0].document_uid == "doc3"


# ----------------------------
# ❌ Error Cases
# ----------------------------


def test_save_metadata_missing_uid(metadata_store):
    with pytest.raises(ValueError):
        metadata_store.save_metadata(DocumentMetadata(source_type=SourceType("push"), document_uid=None, document_name="Missing"))


def test_update_metadata_uid_not_found(metadata_store):
    with pytest.raises(ValueError):
        metadata_store.update_metadata_field("missing", "title", "New Title")


def test_delete_metadata_uid_not_found(metadata_store):
    ghost = DocumentMetadata(source_type=SourceType("push"), document_uid="ghost", document_name="Ghost")
    with pytest.raises(ValueError):
        metadata_store.delete_metadata(ghost)


def test_delete_metadata_missing_uid(metadata_store):
    broken = DocumentMetadata(source_type=SourceType("push"), document_uid="", document_name="Broken")
    with pytest.raises(ValueError):
        metadata_store.delete_metadata(broken)


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_overwrite_existing_metadata(metadata_store):
    original = DocumentMetadata(source_type=SourceType("push"), document_uid="doc5", document_name="Original")
    updated = DocumentMetadata(source_type=SourceType("push"), document_uid="doc5", document_name="Updated")

    metadata_store.save_metadata(original)
    metadata_store.save_metadata(updated)

    result = metadata_store.get_metadata_by_uid("doc5")
    assert result.document_name == "Updated"


def test_delete_existing_metadata(metadata_store):
    doc = DocumentMetadata(source_type=SourceType("push"), document_uid="doc6", document_name="ToDelete")
    metadata_store.save_metadata(doc)
    metadata_store.delete_metadata(doc)

    assert metadata_store.get_metadata_by_uid("doc6") is None


def test_match_nested_with_value_mismatch(metadata_store):
    metadata = DocumentMetadata(source_type=SourceType("push"), document_uid="doc8", document_name="Mismatch", author="bob")
    metadata_store.save_metadata(metadata)

    result = metadata_store.get_all_metadata({"author": "alice"})
    assert result == []


def test_load_returns_empty_if_file_missing(tmp_path):
    json_path = tmp_path / "missing.json"
    store = DuckdbMetadataStore(json_path)

    if json_path.exists():
        json_path.unlink()

    assert store.get_all_metadata({}) == []
