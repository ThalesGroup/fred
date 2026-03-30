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

import pytest
from dotenv import load_dotenv
from docling.datamodel.pipeline_options import RapidOcrOptions

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
    _annotate_markdown_tables,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.structures import PdfComplexity, PdfComplexityStats

dotenv_path = os.getenv("ENV_FILE", "./config/.env")
load_dotenv(dotenv_path)


class MockImageDescriber(BaseImageDescriber):
    def describe(self, image_base64: str) -> str:
        return "There is an image showing a mocked description."


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


def test_select_conversion_mode_for_profile_fast_skips_complexity_inspection(
    processor: PdfMarkdownProcessor,
    sample_pdf_file: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        processor,
        "_collect_pdf_complexity_stats",
        lambda _: pytest.fail("fast profile must not inspect PDF complexity"),
    )

    mode = processor._select_conversion_mode_for_profile(
        sample_pdf_file,
        IngestionProcessingProfile.FAST,
    )

    assert mode == "lite"


def test_select_conversion_mode_for_profile_medium_uses_complexity_inspection(
    processor: PdfMarkdownProcessor,
    sample_pdf_file: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    stats = PdfComplexityStats(
        page_count=4,
        total_text_chars=9000,
        pages_without_text=0,
        pages_with_images=1,
    )

    monkeypatch.setattr(processor, "_collect_pdf_complexity_stats", lambda _: stats)
    monkeypatch.setattr(processor, "_classify_pdf_kind", lambda received: PdfComplexity.SCIENTIFIC_PDF if received == stats else None)
    monkeypatch.setattr(
        processor,
        "_select_conversion_mode",
        lambda document_kind: "docling" if document_kind == PdfComplexity.SCIENTIFIC_PDF else "lite",
    )

    mode = processor._select_conversion_mode_for_profile(
        sample_pdf_file,
        IngestionProcessingProfile.MEDIUM,
    )

    assert mode == "docling"


def test_select_conversion_mode_for_profile_rich_skips_complexity_inspection(
    processor: PdfMarkdownProcessor,
    sample_pdf_file: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        processor,
        "_collect_pdf_complexity_stats",
        lambda _: pytest.fail("rich profile must not inspect PDF complexity"),
    )

    mode = processor._select_conversion_mode_for_profile(
        sample_pdf_file,
        IngestionProcessingProfile.RICH,
    )

    assert mode == "docling"


def test_build_docling_pipeline_options_rich_enables_full_page_ocr(
    processor: PdfMarkdownProcessor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        processor,
        "_resolve_pdf_profile_options",
        lambda _profile: (
            False,
            ProcessingConfig.PdfPipelineConfig(
                backend="docling_parse",
                images_scale=2.0,
                generate_picture_images=True,
                generate_page_images=False,
                generate_table_images=False,
                do_table_structure=True,
                do_ocr=True,
                ocr_backend="openvino",
                force_full_page_ocr=True,
            ),
        ),
    )

    process_images, backend_name, pipeline_options = processor._build_docling_pipeline_options(
        IngestionProcessingProfile.RICH,
    )

    assert process_images is False
    assert backend_name == "docling_parse"
    assert pipeline_options.images_scale == 2.0
    assert pipeline_options.generate_picture_images is True
    assert pipeline_options.generate_page_images is False
    assert pipeline_options.do_table_structure is True
    assert pipeline_options.do_ocr is True
    assert pipeline_options.ocr_options is not None
    assert pipeline_options.ocr_options.backend == "openvino"
    assert pipeline_options.ocr_options.force_full_page_ocr is True


def test_build_docling_pipeline_options_medium_reads_ocr_backend_from_profile_config(
    processor: PdfMarkdownProcessor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        processor,
        "_resolve_pdf_profile_options",
        lambda _profile: (
            False,
            ProcessingConfig.PdfPipelineConfig(
                backend="docling_parse",
                images_scale=1.5,
                generate_picture_images=False,
                generate_page_images=False,
                generate_table_images=False,
                do_table_structure=True,
                do_ocr=True,
                ocr_backend="torch",
                force_full_page_ocr=False,
            ),
        ),
    )

    _process_images, backend_name, pipeline_options = processor._build_docling_pipeline_options(
        IngestionProcessingProfile.MEDIUM,
    )

    assert backend_name == "docling_parse"
    assert pipeline_options.ocr_options is not None
    assert pipeline_options.ocr_options.backend == "torch"
    assert pipeline_options.ocr_options.force_full_page_ocr is False


def test_build_docling_pipeline_options_skips_ocr_options_when_ocr_disabled(
    processor: PdfMarkdownProcessor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        processor,
        "_resolve_pdf_profile_options",
        lambda _profile: (
            False,
            ProcessingConfig.PdfPipelineConfig(
                backend="pypdfium2",
                images_scale=1.0,
                generate_picture_images=False,
                generate_page_images=False,
                generate_table_images=False,
                do_table_structure=False,
                do_ocr=False,
                ocr_backend="paddle",
                force_full_page_ocr=True,
            ),
        ),
    )

    _process_images, backend_name, pipeline_options = processor._build_docling_pipeline_options(
        IngestionProcessingProfile.RICH,
    )

    assert backend_name == "pypdfium2"
    assert pipeline_options.do_ocr is False
    assert not isinstance(pipeline_options.ocr_options, RapidOcrOptions)
    assert not hasattr(pipeline_options.ocr_options, "backend")


def test_processing_profile_config_accepts_pdf_pipeline_options():
    profile = ProcessingConfig.ProfileConfig(
        pdf=ProcessingConfig.PdfPipelineConfig(
            backend="docling_parse",
            images_scale=1.5,
            generate_picture_images=False,
            generate_page_images=False,
            generate_table_images=False,
            do_table_structure=True,
            do_ocr=True,
            ocr_backend="onnxruntime",
            force_full_page_ocr=False,
        ),
    )

    assert profile.pdf.backend == "docling_parse"
    assert profile.pdf.ocr_backend == "onnxruntime"
    assert profile.pdf.force_full_page_ocr is False


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
