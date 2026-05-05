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

# tests/test_pdf_processor.py

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import load_dotenv
from fred_core.common import ModelConfiguration

import knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor as pdf_module
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
    _annotate_markdown_tables,
)

dotenv_path = os.getenv("ENV_FILE", "./config/.env")
load_dotenv(dotenv_path)


@pytest.fixture
def processor():
    return PdfMarkdownProcessor()


@pytest.fixture
def sample_pdf_file():
    return Path(__file__).parent / "assets" / "sample.pdf"


def test_annotate_markdown_tables_treats_backslash_digits_as_literal_text():
    markdown = "| col |\n| --- |\n| \\6 |\n"

    annotated = _annotate_markdown_tables(markdown, ["| col |\n| --- |\n| \\6 |"])

    assert "<!-- TABLE_START:id=0 -->" in annotated
    assert "| \\6 |" in annotated
    assert "<!-- TABLE_END -->" in annotated


def test_pdf_processor_remote_ocr_disabled_when_profile_ocr_is_off():
    """
    Ensure remote OCR is never selected when the profile disables OCR.

    Why this exists:
    - The new `ocr_model` must not change existing `do_ocr: false` behavior.

    How to use:
    - Build a profile config with `do_ocr=False` and assert the processor keeps
      remote OCR disabled even if an OCR model exists globally.
    """

    processor = PdfMarkdownProcessor()

    assert processor._should_use_remote_ocr(pdf_module.ProcessingConfig.PdfPipelineConfig(do_ocr=False)) is False


def test_pdf_processor_uses_local_fallback_when_ocr_model_missing(monkeypatch, tmp_path):
    """
    Ensure the processor keeps the existing local OCR path when no remote OCR
    model is configured.

    Why this exists:
    - `ocr_model` is optional and should not be required for current
      installations.

    How to use:
    - Patch the local Docling conversion helper, disable `ocr_model`, and assert
      the local path is used.
    """

    processor = PdfMarkdownProcessor()
    output_dir = tmp_path / "out"
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n%stub")

    monkeypatch.setattr(
        processor,
        "_resolve_effective_options",
        lambda: (
            pdf_module.IngestionProcessingProfile.MEDIUM,
            False,
            pdf_module.ProcessingConfig.PdfPipelineConfig(do_ocr=True),
        ),
    )
    monkeypatch.setattr(pdf_module, "get_configuration", lambda: SimpleNamespace(ocr_model=None))
    monkeypatch.setattr(
        processor,
        "_convert_with_docling",
        lambda file_path, pdf_options, active_profile, process_images: "local markdown",
    )

    result = processor.convert_file_to_markdown(sample_pdf, output_dir, None)

    assert Path(result["md_file"]).read_text(encoding="utf-8") == "local markdown"


def test_pdf_processor_uses_remote_ocr_when_model_configured(monkeypatch, tmp_path):
    """
    Ensure the processor switches to the remote OCR branch when configured.

    Why this exists:
    - The new feature should take priority over local OCR for OCR-enabled PDF
      profiles.

    How to use:
    - Patch the remote OCR helper, set `ocr_model`, and assert the produced
      markdown comes from the remote branch.
    """

    processor = PdfMarkdownProcessor()
    output_dir = tmp_path / "out"
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n%stub")

    monkeypatch.setattr(
        processor,
        "_resolve_effective_options",
        lambda: (
            pdf_module.IngestionProcessingProfile.RICH,
            False,
            pdf_module.ProcessingConfig.PdfPipelineConfig(do_ocr=True),
        ),
    )
    monkeypatch.setattr(
        pdf_module,
        "get_configuration",
        lambda: SimpleNamespace(ocr_model=ModelConfiguration(provider="openai", name="gpt-4o-mini", settings={})),
    )
    monkeypatch.setattr(
        processor,
        "_convert_with_remote_ocr",
        lambda file_path, pdf_options, process_images: ("remote markdown", 2),
    )

    result = processor.convert_file_to_markdown(sample_pdf, output_dir, None)

    assert Path(result["md_file"]).read_text(encoding="utf-8") == "remote markdown"


def test_pdf_processor_force_full_page_ocr_marks_every_page_for_remote_ocr():
    """
    Ensure full-page OCR bypasses native-text heuristics.

    Why this exists:
    - The per-profile `force_full_page_ocr` flag must keep its meaning on the
      remote OCR path.

    How to use:
    - Pass readable native text and `force_full_page_ocr=True`; the helper
      should still request OCR.
    """

    processor = PdfMarkdownProcessor()

    assert processor._page_requires_remote_ocr("This page already has text.", True) is True


def test_pdf_processor_keeps_native_text_when_sufficient():
    """
    Ensure born-digital pages avoid unnecessary remote OCR calls.

    Why this exists:
    - Remote OCR should only be used for empty or nearly empty pages by
      default.

    How to use:
    - Pass a page with enough native text and assert the heuristic keeps OCR
      disabled.
    """

    processor = PdfMarkdownProcessor()

    assert processor._page_requires_remote_ocr("This page already has enough native text to skip OCR.", False) is False


@pytest.mark.integration
def test_pdf_processor_end_to_end(processor: PdfMarkdownProcessor, sample_pdf_file):
    output_dir = Path("/tmp/knowledge_flow/test/output")
    output_dir.mkdir(exist_ok=True, parents=True)

    assert processor.check_file_validity(sample_pdf_file)

    metadata = processor.process_metadata(sample_pdf_file, [], "uploads")

    assert metadata.document_name == "sample.pdf"
    # assert metadata.num_pages == 2
    assert metadata.document_uid

    result = processor.convert_file_to_markdown(sample_pdf_file, output_dir, metadata.document_uid)

    md_file = Path(result["md_file"])
    assert md_file.exists()
    md_content = md_file.read_text(encoding="utf-8").strip()
    assert md_content != ""
