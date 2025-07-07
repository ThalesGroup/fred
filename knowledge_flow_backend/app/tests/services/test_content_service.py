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
Test suite for ContentService in content_service.py.

Covers:
- Document metadata retrieval
- Original content stream fetching
- Markdown preview access

Each feature is tested with:
- Nominal inputs
- Invalid or missing inputs
- Fallback/default behaviors

Mocks are used to simulate metadata_store and content_store dependencies.
"""

# pylint: disable=redefined-outer-name

from io import BytesIO
import pytest
from knowledge_flow_app.features.content.service import ContentService


# ----------------------------
# ⚙️ Fixtures
# ----------------------------


@pytest.fixture
def service():
    """
    Fixture: provides a ContentService instance with mocked metadata and content stores.
    """
    service = ContentService()

    # Mock metadata store
    service.metadata_store = type(
        "MockMetadataStore",
        (),
        {"get_metadata_by_uid": lambda self, uid: {"document_name": "test.txt"} if uid == "valid" else {}},
    )()

    # Mock content store
    service.content_store = type(
        "MockContentStore",
        (),
        {
            "get_content": lambda self, uid: BytesIO(b"hello") if uid == "valid" else (_ for _ in ()).throw(FileNotFoundError()),
            "get_markdown": lambda self, uid: "# Markdown" if uid == "valid" else (_ for _ in ()).throw(FileNotFoundError()),
        },
    )()

    return service


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


@pytest.mark.asyncio
async def test_get_document_metadata_success(service):
    """
    Test: retrieves document metadata when UID is valid.
    """
    metadata = await service.get_document_metadata("valid")
    assert metadata["document_name"] == "test.txt"


@pytest.mark.asyncio
async def test_get_original_content_success(service):
    """
    Test: returns the input stream, file name, and content type for valid UID.
    """
    stream, name, ctype = await service.get_original_content("valid")
    assert stream.read() == b"hello"
    assert name == "test.txt"
    assert ctype == "text/plain"


@pytest.mark.asyncio
async def test_get_markdown_preview_success(service):
    """
    Test: returns markdown preview content for valid UID.
    """
    content = await service.get_markdown_preview("valid")
    assert content.startswith("# Markdown")


# ----------------------------
# ❌ Failure Cases
# ----------------------------


@pytest.mark.asyncio
async def test_get_document_metadata_no_uid(service):
    """
    Test: raises ValueError if no UID is provided.
    """
    with pytest.raises(ValueError, match="Document UID is required"):
        await service.get_document_metadata("")


@pytest.mark.asyncio
async def test_get_original_content_file_not_found(service):
    """
    Test: raises FileNotFoundError if content is missing.
    """
    with pytest.raises(FileNotFoundError, match="Original input file not found"):
        await service.get_original_content("invalid")


@pytest.mark.asyncio
async def test_get_markdown_preview_not_found(service):
    """
    Test: raises FileNotFoundError if markdown is not found.
    """
    with pytest.raises(FileNotFoundError, match="No markdown preview found"):
        await service.get_markdown_preview("invalid")


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


@pytest.mark.asyncio
async def test_get_document_metadata_missing_name(service, monkeypatch):
    """
    Test: falls back to default document name if 'document_name' is missing.
    """
    monkeypatch.setattr(service.metadata_store, "get_metadata_by_uid", lambda uid: {})
    metadata = await service.get_document_metadata("no-name")
    assert metadata["document_name"] == "no-name.xxx"
