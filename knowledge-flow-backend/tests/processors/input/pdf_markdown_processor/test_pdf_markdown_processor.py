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
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import ThreadedPdfPipelineOptions
from dotenv import load_dotenv
from fred_core.common import ModelConfiguration

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.common.ocr.base_pdf_ocr_extractor import (
    RemotePdfOcrImage,
    RemotePdfOcrPage,
    RemotePdfOcrResult,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
    _annotate_markdown_tables,
)

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


def test_pdf_processor_uses_threaded_pipeline_options(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    class FakeDocument:
        pictures = []
        tables = []

        def export_to_markdown(self, image_mode=None, image_placeholder=None) -> str:
            return "# ok\n"

    captured: dict[str, object] = {}

    class FakeDocumentConverter:
        def __init__(self, *, format_options):
            captured["format_options"] = format_options

        def convert(self, file_path: Path):
            captured["file_path"] = file_path
            return type("FakeResult", (), {"document": FakeDocument()})()

    pdf_config = ProcessingConfig.PdfPipelineConfig(
        backend="docling_parse",
        images_scale=1.0,
        generate_picture_images=True,
        generate_page_images=False,
        generate_table_images=False,
        do_table_structure=True,
        do_ocr=True,
        ocr_backend="openvino",
        force_full_page_ocr=False,
        ocr_batch_size=1,
        layout_batch_size=2,
        table_batch_size=3,
        batch_polling_interval_seconds=0.25,
        queue_max_size=7,
    )

    monkeypatch.setattr(
        processor,
        "_resolve_effective_options",
        lambda: (IngestionProcessingProfile.RICH, False, pdf_config),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
        FakeDocumentConverter,
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-123")

    assert Path(result["md_file"]).exists()
    format_options = captured["format_options"]
    pdf_format_option = format_options[InputFormat.PDF]
    pipeline_options = pdf_format_option.pipeline_options
    assert isinstance(pipeline_options, ThreadedPdfPipelineOptions)
    assert pipeline_options.images_scale == 1.0
    assert pipeline_options.ocr_batch_size == 1
    assert pipeline_options.layout_batch_size == 2
    assert pipeline_options.table_batch_size == 3
    assert pipeline_options.batch_polling_interval_seconds == 0.25
    assert pipeline_options.queue_max_size == 7
    assert pipeline_options.ocr_options.backend == "openvino"
    assert pipeline_options.ocr_options.force_full_page_ocr is False


def test_pdf_processor_uses_remote_ocr_when_model_is_configured(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    pdf_config = ProcessingConfig.PdfPipelineConfig(
        backend="docling_parse",
        images_scale=2.0,
        generate_picture_images=True,
        generate_page_images=False,
        generate_table_images=False,
        do_table_structure=True,
        do_ocr=True,
        ocr_backend="openvino",
        force_full_page_ocr=False,
    )

    class FakeExtractor:
        def extract_pdf_result(self, file_path: Path, *, include_images: bool = False) -> RemotePdfOcrResult:
            assert include_images is False
            return RemotePdfOcrResult(pages=[RemotePdfOcrPage(markdown="# OCR markdown")])

    monkeypatch.setattr(
        processor,
        "_resolve_effective_options",
        lambda: (IngestionProcessingProfile.RICH, False, pdf_config),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=None,
            ocr_model=ModelConfiguration(
                provider="openai",
                name="mistral-ocr-latest",
                settings={"base_url": "https://api.mistral.ai/v1"},
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.build_pdf_ocr_extractor",
        lambda cfg: FakeExtractor(),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local Docling OCR should not run")),
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-ocr")

    md_path = Path(result["md_file"])
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8") == "# OCR markdown"
    assert result["message"] == "Remote OCR conversion to markdown succeeded."


def test_pdf_processor_describes_remote_ocr_images_with_vision_model(
    monkeypatch: pytest.MonkeyPatch,
    processor: PdfMarkdownProcessor,
    sample_pdf_file: Path,
    tmp_path: Path,
):
    pdf_config = ProcessingConfig.PdfPipelineConfig(
        backend="docling_parse",
        images_scale=2.0,
        generate_picture_images=True,
        generate_page_images=False,
        generate_table_images=False,
        do_table_structure=True,
        do_ocr=True,
        ocr_backend="openvino",
        force_full_page_ocr=False,
    )

    class FakeExtractor:
        def extract_pdf_result(self, file_path: Path, *, include_images: bool = False) -> RemotePdfOcrResult:
            assert include_images is True
            return RemotePdfOcrResult(
                pages=[
                    RemotePdfOcrPage(
                        markdown="Before\n\n![](img-1.jpeg)\n\nAfter",
                        images=[RemotePdfOcrImage(image_id="img-1.jpeg", image_base64="ZmFrZQ==")],
                    )
                ]
            )

    monkeypatch.setattr(
        processor,
        "_resolve_effective_options",
        lambda: (IngestionProcessingProfile.RICH, True, pdf_config),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=ModelConfiguration(
                provider="openai",
                name="mistral-medium",
                settings={"base_url": "https://api.example.test"},
            ),
            ocr_model=ModelConfiguration(
                provider="openai",
                name="mistral-ocr-latest",
                settings={"base_url": "https://api.mistral.ai/v1"},
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.build_image_describer",
        lambda cfg: MockImageDescriber(),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.build_pdf_ocr_extractor",
        lambda cfg: FakeExtractor(),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.DocumentConverter",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local Docling OCR should not run")),
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-ocr-images")

    md_path = Path(result["md_file"])
    assert md_path.exists()
    assert "img-1.jpeg" not in md_path.read_text(encoding="utf-8")
    assert "There is an image showing a mocked description." in md_path.read_text(encoding="utf-8")
    assert result["message"] == "Remote OCR conversion to markdown succeeded."


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
