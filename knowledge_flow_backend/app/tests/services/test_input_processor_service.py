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

# app/tests/features/test_input_processor_service.py

import pytest
from app.features.ingestion.service import IngestionService
from app.common.document_structures import DocumentMetadata
from uuid import uuid4


class TestInputProcessorService:

    @pytest.fixture
    def service(self):
        return IngestionService()

    def test_extract_metadata_success(self, tmp_path, service: IngestionService):
        test_file = tmp_path / "test.md"
        test_file.write_text("dummy content")

        metadata = service.extract_metadata(test_file, [])
        assert metadata.document_uid
        assert metadata.title == "test-markdown"
        assert metadata.document_name == "test.md"

    def test_extract_metadata_missing_uid(self, tmp_path, service: IngestionService):
        # Should not raise because UID is now injected automatically by processor
        test_file = tmp_path / "test.md"
        test_file.write_text("dummy")
        metadata = service.extract_metadata(test_file, [])
        assert metadata.document_uid

    def test_process_markdown(self, tmp_path, service: IngestionService):
        input_file = tmp_path / "test.md"
        input_file.write_text("dummy")

        metadata = DocumentMetadata(
            document_name=input_file.name,
            document_uid="markdown-uid-001"
        )

        service.process_input(tmp_path, input_file.name, metadata)

        output_file = tmp_path / "output" / "file.md"
        assert output_file.exists()
        assert output_file.read_text() == "# Test Markdown Content"

    def test_process_tabular(self, tmp_path, service: IngestionService):
        input_file = tmp_path / "table.xlsx"
        input_file.write_text("dummy")

        metadata = DocumentMetadata(
            document_name=input_file.name,
            document_uid="tabular-uid-001"
        )

        service.process_input(tmp_path, input_file.name, metadata)

        output_file = tmp_path / "output" / "table.csv"
        assert output_file.exists()
        content = output_file.read_text()
        assert "col1" in content
        assert "1" in content
        assert "A" in content

    def test_process_unknown_processor(self, monkeypatch, tmp_path, service: IngestionService):
        class UnknownProcessor:
            pass

        monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: UnknownProcessor())

        input_file = tmp_path / "weird.bin"
        input_file.write_text("data")

        metadata = DocumentMetadata(
            document_name=input_file.name,
            document_uid=str(uuid4())
        )

        with pytest.raises(RuntimeError, match="Unknown processor type"):
            service.process_input(tmp_path, input_file.name, metadata)
