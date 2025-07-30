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

# app/tests/services/test_output_processor_service.py

import shutil
from pathlib import Path
import pytest

from app.common.document_structures import DocumentMetadata
from app.common.structures import OutputProcessorResponse
from app.features.ingestion.service import IngestionService
from app.core.processors.input.common.base_image_describer import BaseImageDescriber
from app.application_context import ApplicationContext
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor


@pytest.fixture
def prepared_pdf_dir(tmp_path, monkeypatch):
    from shutil import copy

    # Set dummy describer in PDF processor
    class DummyDescriber(BaseImageDescriber):
        def describe(self, base64_image: str) -> str:
            return "This is a test image description"

    context = ApplicationContext.get_instance()
    monkeypatch.setattr(
        context,
        "get_input_processor_instance",
        lambda ext: PdfMarkdownProcessor(image_describer=DummyDescriber()) if ext == ".pdf" else None,
    )

    source_file = Path("app/tests/assets/sample.pdf")
    input_file = tmp_path / source_file.name
    copy(source_file, input_file)

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    IngestionService().process_input(input_file, output_dir, DocumentMetadata(source_type="push", document_name=source_file.name, document_uid="pdf-uid-123"))

    return tmp_path


class TestOutputProcessorService:
    @pytest.fixture
    def service(self):
        return IngestionService()

    @pytest.fixture
    def prepared_docx_dir(self, tmp_path):
        source = Path("app/tests/assets/sample.docx")
        input_file = tmp_path / source.name
        shutil.copy(source, input_file)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        IngestionService().process_input(input_file, output_dir, DocumentMetadata(source_type="push", document_name=source.name, document_uid="docx-uid-123"))

        return tmp_path

    # ✅ Nominal
    def test_process_real_pdf_success(self, service: IngestionService, prepared_pdf_dir):
        metadata = DocumentMetadata(source_type="push", document_name="sample.pdf", document_uid="pdf-uid-123")

        # 🔍 Find the actual output preview file (e.g. output.md or table.csv)
        output_dir = prepared_pdf_dir / "output"
        output_file = service.get_preview_file(metadata, output_dir)

        # ✅ Now process that real preview file (not a hardcoded .pdf)
        result = service.process_output(input_file_name=output_file.name, output_dir=output_dir, input_file_metadata=metadata)

        assert isinstance(result, OutputProcessorResponse)

    def test_process_real_docx_success(self, service: IngestionService, prepared_docx_dir):
        metadata = DocumentMetadata(source_type="push", document_name="sample.docx", document_uid="docx-uid-123")
        output_file = service.get_preview_file(metadata, prepared_docx_dir / "output")
        output_dir = prepared_docx_dir / "output"

        result = service.process_output(input_file_name=output_file.name, output_dir=output_dir, input_file_metadata=metadata)
        assert isinstance(result, OutputProcessorResponse)

    # ❌ Failure
    def test_output_processor_missing_output_dir(self, service: IngestionService, tmp_path):
        with pytest.raises(ValueError):
            service.process_output(tmp_path, "fake.pdf", DocumentMetadata(source_type="push", document_uid="missing"))

    @pytest.mark.parametrize(
        "file_name, create_file, content",
        [
            ("not_a_dir", False, None),
            ("output/no_output_file", True, None),
            ("output/output.txt", True, ""),
            ("output/output.md", True, ""),
        ],
    )
    def test_output_processor_error_cases(self, service: IngestionService, tmp_path, file_name, create_file, content):
        output_path = tmp_path / file_name
        if create_file:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content or "")
        elif "not_a_dir" in file_name:
            (tmp_path / "output").write_text("this is not a directory")

        with pytest.raises(ValueError):
            service.process_output(tmp_path, "test.md", DocumentMetadata(source_type="push", document_uid="unknown"))

    def test_output_processor_rejects_non_markdown_csv(self, monkeypatch, service: IngestionService, tmp_path):
        (tmp_path / "output").mkdir(parents=True)
        (tmp_path / "output" / "output.xlsx").write_text("fake content")

        with pytest.raises(ValueError):
            service.process_output(tmp_path, "sample.xlsx", DocumentMetadata(source_type="push", document_uid="bad-ext"))

    def test_output_processor_empty_output_file(self, service: IngestionService, tmp_path):
        doc_path = tmp_path / "sample.pdf"
        output_dir = doc_path / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "output.md").touch()

        with pytest.raises(ValueError):
            service.process_output(tmp_path, "sample.pdf", DocumentMetadata(source_type="push", document_name="sample.pdf", document_uid="docx-uid-123"))
