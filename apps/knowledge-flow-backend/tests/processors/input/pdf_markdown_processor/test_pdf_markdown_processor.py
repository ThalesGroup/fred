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

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from dotenv import load_dotenv

from knowledge_flow_backend.common.structures import ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    ExtractorConfigurationError,
    PdfMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import (
    ImageTranscription,
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

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=None,
            processing=SimpleNamespace(
                normalize_profile=lambda p: p,
                get_profile_config=lambda p: SimpleNamespace(
                    process_images=False,
                    pdf=ProcessingConfig.PdfPipelineConfig(extractor="docling", do_ocr=False),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_current_processing_profile",
        lambda: "rich",
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor.get_configuration",
        lambda: SimpleNamespace(processing=SimpleNamespace(path_base_model="/tmp/fake-models")),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor.DocumentConverter",
        FakeDocumentConverter,
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-123")

    assert Path(result["md_file"]).exists()
    format_options = captured["format_options"]
    pdf_format_option = format_options[InputFormat.PDF]
    pipeline_options = pdf_format_option.pipeline_options
    assert isinstance(pipeline_options, PdfPipelineOptions)
    assert pipeline_options.generate_picture_images is True
    assert pipeline_options.do_table_structure is True
    assert pipeline_options.do_ocr is True
    assert pipeline_options.layout_batch_size == 16


def test_pdf_processor_transcribes_images_with_ocr(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    img_path = tmp_path / "img0.png"

    class FakeExtractor:
        def extract(self, file_path: Path, work_dir: str):
            return (f"Before\n\n![]({img_path})\n\nAfter", [ImageTranscription(image_path=img_path)])

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=None,
            processing=SimpleNamespace(
                normalize_profile=lambda p: p,
                get_profile_config=lambda p: SimpleNamespace(
                    process_images=False,
                    pdf=ProcessingConfig.PdfPipelineConfig(extractor="docling", do_ocr=True),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_current_processing_profile",
        lambda: "rich",
    )
    monkeypatch.setattr(processor, "_build_extractor", lambda *_: FakeExtractor())
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.PaddleOCRmodel",
        lambda: None,
    )
    monkeypatch.setattr(
        processor,
        "_use_ocr",
        lambda model, images: [{"rec_texts": ["OCR extracted text"]}],
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-ocr")

    md_text = Path(result["md_file"]).read_text(encoding="utf-8")
    assert "OCR extracted text" in md_text
    assert str(img_path) not in md_text


def test_pdf_processor_describes_images_with_vision_model(
    monkeypatch: pytest.MonkeyPatch,
    processor: PdfMarkdownProcessor,
    sample_pdf_file: Path,
    tmp_path: Path,
):
    img_path = tmp_path / "img0.png"

    class FakeExtractor:
        def extract(self, file_path: Path, work_dir: str):
            return (f"Before\n\n![]({img_path})\n\nAfter", [ImageTranscription(image_path=img_path)])

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=SimpleNamespace(name="fake-vision"),
            processing=SimpleNamespace(
                normalize_profile=lambda p: p,
                get_profile_config=lambda p: SimpleNamespace(
                    process_images=True,
                    pdf=ProcessingConfig.PdfPipelineConfig(extractor="docling", do_ocr=True),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_current_processing_profile",
        lambda: "rich",
    )
    monkeypatch.setattr(processor, "_build_extractor", lambda *_: FakeExtractor())
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.PaddleOCRmodel",
        lambda: None,
    )
    monkeypatch.setattr(
        processor,
        "_use_ocr",
        lambda model, images: [{"rec_texts": []}],
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.build_image_describer",
        lambda cfg: MockImageDescriber(),
    )
    monkeypatch.setattr(
        processor,
        "_use_image_describer",
        lambda describer, img_t, ocr_r: "There is an image showing a mocked description.",
    )

    result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-vision")

    md_text = Path(result["md_file"]).read_text(encoding="utf-8")
    assert "There is an image showing a mocked description." in md_text
    assert str(img_path) not in md_text


def test_build_extractor_raises_configuration_error_when_pymupdf_extra_missing(processor: PdfMarkdownProcessor):
    """LICENSE-01: extractor: pymupdf without the optional extra installed must fail
    with a clear, actionable error — not a bare ImportError, and not a silent
    fallback to a different engine. Environment-robust: if a developer has opted
    into the extra locally, _build_extractor should succeed instead — the point
    is that one of the two outcomes always holds, never a bare ImportError."""
    if importlib.util.find_spec("pymupdf4llm") is None:
        with pytest.raises(ExtractorConfigurationError, match="pymupdf"):
            processor._build_extractor("pymupdf")
    else:
        from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pymupdf_processor import PyMuPdfExtractor

        assert isinstance(processor._build_extractor("pymupdf"), PyMuPdfExtractor)


def test_convert_file_to_markdown_reraises_extractor_configuration_error(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    """LICENSE-01: a deployer misconfiguration must propagate to the caller, not be
    swallowed by the extraction-failure fallback and silently answered with
    markitdown output instead."""

    def _boom(*_args, **_kwargs):
        raise ExtractorConfigurationError("extractor: pymupdf but the extra isn't installed")

    monkeypatch.setattr(processor, "_extract_md", _boom)

    with pytest.raises(ExtractorConfigurationError):
        processor.convert_file_to_markdown(sample_pdf_file, tmp_path, "doc-misconfigured")


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
