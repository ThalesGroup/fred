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
Integration tests for ContentService using real LocalMetadataStore and LocalStorageBackend.

Covers:
- Document metadata retrieval
- Original content stream fetching
- Markdown preview access

Uses real filesystem, no mocks. Fast and reliable.
"""

from app.core.stores.content.filesystem_content_store import FileSystemContentStore
import pytest

from app.common.document_structures import DocumentMetadata
from app.features.content.service import ContentService
from app.core.stores.metadata.local_metadata_store import LocalMetadataStore


# ----------------------------
# ⚙️ Realistic Setup
# ----------------------------


@pytest.fixture
def service(tmp_path) -> ContentService:
    """Sets up a real ContentService with local stores and one valid document."""
    metadata_path = tmp_path / "metadata.json"
    content_dir = tmp_path / "content-store"

    service = ContentService()
    service.metadata_store = LocalMetadataStore(metadata_path)
    service.content_store = FileSystemContentStore(content_dir)

    # Valid doc setup
    uid = "valid"
    metadata = DocumentMetadata(source_type="push", document_uid=uid, document_name="test.txt")
    service.metadata_store.save_metadata(metadata)

    input_dir = content_dir / uid / "input"
    output_dir = content_dir / uid / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / "test.txt").write_bytes(b"hello world")
    (output_dir / "output.md").write_text("# Sample Markdown")

    return service


# ----------------------------
# ✅ Nominal
# ----------------------------


@pytest.mark.asyncio
async def test_get_original_content_success(service: ContentService):
    stream, name, ctype = await service.get_original_content("valid")
    assert stream.read() == b"hello world"
    assert name == "test.txt"
    assert ctype.startswith("text/")


@pytest.mark.asyncio
async def test_get_markdown_preview_success(service: ContentService):
    content = await service.get_markdown_preview("valid")
    assert "# Sample Markdown" in content


@pytest.mark.asyncio
async def test_get_document_metadata_success(service: ContentService):
    metadata = await service.get_document_metadata("valid")
    assert metadata.document_name == "test.txt"
    assert metadata.document_uid == "valid"


# ----------------------------
# ❌ Failure
# ----------------------------


@pytest.mark.asyncio
async def test_get_original_content_not_found(service: ContentService):
    with pytest.raises(FileNotFoundError):
        await service.get_original_content("missing")


@pytest.mark.asyncio
async def test_get_markdown_preview_not_found(service: ContentService):
    with pytest.raises(FileNotFoundError):
        await service.get_markdown_preview("missing")


@pytest.mark.asyncio
async def test_get_document_metadata_missing_uid(service: ContentService):
    with pytest.raises(ValueError):
        await service.get_document_metadata("")
