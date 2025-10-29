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


import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.features.ingestion.service import IngestionService


@pytest.fixture
def sample_docx(tmp_path):
    sample_path = tmp_path / "sample.docx"
    sample_path.write_bytes(b"Dummy DOCX content")
    return sample_path


@pytest.fixture
def output_dir(tmp_path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    return out_dir


@pytest.fixture
def test_user():
    return KeycloakUser(
        uid="test-user",
        username="testuser",
        email="testuser@localhost",
        roles=["admin"],
    )


async def test_extract_and_save_metadata(sample_docx, metadata_store, test_user):
    service = IngestionService()

    # 🔍 Extract metadata
    metadata = service.extract_metadata(test_user, sample_docx, tags=["test"], source_tag="uploads")
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.document_uid is not None
    assert metadata.tags == ["test"]
    assert metadata.source_tag == "uploads"

    # 💾 Save metadata and reload it
    await service.save_metadata(test_user, metadata)
    restored = await service.get_metadata(test_user, metadata.document_uid)
    assert restored is not None
    assert restored.document_uid == metadata.document_uid
    assert restored.tags == ["test"]


def test_process_input(sample_docx, output_dir, test_user):
    service = IngestionService()
    metadata = service.extract_metadata(test_user, sample_docx, tags=["test"], source_tag="fred")

    # ⚙️ Process the file into output directory
    service.process_input(test_user, sample_docx, output_dir, metadata)

    # ✅ Check expected output
    output_file = output_dir / "output.md"
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_process_input_then_output(sample_docx, output_dir, test_user):
    service = IngestionService()
    metadata = service.extract_metadata(test_user, sample_docx, tags=["test"], source_tag="fred")

    # First process input
    service.process_input(test_user, sample_docx, output_dir, metadata)

    # Then process output
    result = service.process_output(test_user, sample_docx.name, output_dir, metadata)
    assert result is not None


def test_get_preview_file_fallback(sample_docx, output_dir, test_user):
    service = IngestionService()
    metadata = service.extract_metadata(test_user, sample_docx, tags=["test"], source_tag="fred")

    # Write a dummy preview
    preview = output_dir / "table.csv"
    preview.write_text("a,b,c\n1,2,3", encoding="utf-8")

    found = service.get_preview_file(test_user, metadata, output_dir)
    assert found.name == "table.csv"
