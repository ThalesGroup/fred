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
Tests for OutputProcessorService.

This test suite includes:
- Success cases using processed PDF/DOCX files
- Failure scenarios based on invalid/missing output structures
- Edge conditions like empty files and unsupported formats
"""

# pylint: disable=redefined-outer-name

import shutil
from pathlib import Path
import pytest
from app.features.wip.input_processor_service import InputProcessorService
from app.features.wip.output_processor_service import OutputProcessorService
from app.features.wip import output_processor_service
from app.common.structures import OutputProcessorResponse


# ----------------------------
# ⚙️ Fixtures
# ----------------------------
@pytest.fixture
def prepared_pdf_dir(tmp_path, monkeypatch):
    """Prepare a temporary PDF file and run input processing on it."""

    def mock_describe(*args, **kwargs):
        return "This is a test image description"

    monkeypatch.setattr(
        "app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.PdfMarkdownProcessor._describe_picture",
        mock_describe,
    )

    source_file = Path("app/tests/assets/sample.pdf")
    target_file = tmp_path / source_file.name
    shutil.copy(source_file, target_file)
    input_service = InputProcessorService()
    input_service.process(tmp_path, target_file.name, {"origin": "test"})
    return tmp_path


@pytest.fixture
def prepared_docx_dir(tmp_path):
    """Prepare a temporary DOCX file and run input processing on it."""
    source_file = Path("app/tests/assets/sample.docx")
    target_file = tmp_path / source_file.name
    shutil.copy(source_file, target_file)
    input_service = InputProcessorService()
    input_service.process(tmp_path, target_file.name, {"origin": "test"})
    return tmp_path


class DummyProcessor:
    """Mock processor returning dummy vectorization response."""

    def process(self, path, metadata):
        return OutputProcessorResponse(chunks=1, vectors=[], metadata=metadata)


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_process_real_pdf_success(prepared_pdf_dir):
    """Test output processing on a real processed PDF."""

    service = OutputProcessorService()
    result = service.process(prepared_pdf_dir, "sample.pdf", {"meta": "pdf", "document_uid": "uid-123"})
    assert isinstance(result, OutputProcessorResponse)


def test_process_real_docx_success(prepared_docx_dir):
    """Test output processing on a real processed DOCX."""
    service = OutputProcessorService()
    result = service.process(prepared_docx_dir, "sample.docx", {"meta": "docx", "document_uid": "uid-456"})
    assert isinstance(result, OutputProcessorResponse)


# ----------------------------
# ❌ Failure Cases
# ----------------------------


def test_output_processor_missing_output_dir(tmp_path):
    """Ensure an error is raised when the output directory does not exist."""
    service = OutputProcessorService()
    with pytest.raises(ValueError, match="does not exist"):
        service.process(tmp_path, "fake.pdf", {})


@pytest.mark.parametrize(
    "file_name, create_file, content",
    [
        ("not_a_dir", False, None),
        ("output/no_output_file", True, None),
        ("output/output.txt", True, ""),
        ("output/output.md", True, ""),
    ],
)
def test_output_processor_error_cases(tmp_path, file_name, create_file, content):
    """Test structural and content-based failure conditions in output directory."""
    output_path = tmp_path / file_name
    if create_file:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content or "")
    elif "not_a_dir" in file_name:
        (tmp_path / "output").write_text("this is not a directory")
    service = OutputProcessorService()
    with pytest.raises(ValueError):
        service.process(tmp_path, "test.md", {"document_uid": "fail-case"})


def test_output_processor_rejects_non_markdown_csv(monkeypatch, tmp_path):
    """Ensure unsupported file types (e.g., .xlsx) raise ValueError."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    wrong_file = output_dir / "output.xlsx"
    wrong_file.write_text("fake content")

    class DummyContext:
        def get_output_processor_instance(self, ext):
            return DummyProcessor()

    monkeypatch.setattr(output_processor_service.ApplicationContext, "get_instance", DummyContext)
    service = OutputProcessorService()
    with pytest.raises(ValueError, match="is not a markdown or csv file"):
        service.process(tmp_path, "sample.xlsx", {"document_uid": "bad-ext"})


def test_output_processor_empty_output_file(tmp_path):
    """Ensure that an empty output.md file raises a ValueError."""
    doc_path = tmp_path / "sample.pdf"
    output_dir = doc_path / "output"
    output_dir.mkdir(parents=True)
    empty_file = output_dir / "output.md"
    empty_file.touch()
    service = OutputProcessorService()
    with pytest.raises(ValueError, match="does not exist"):
        service.process(tmp_path, "sample.pdf", {})
