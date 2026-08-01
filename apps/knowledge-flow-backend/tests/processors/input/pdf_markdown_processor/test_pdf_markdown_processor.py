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

import asyncio
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from dotenv import load_dotenv
from temporalio import activity
from temporalio.testing import ActivityEnvironment

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import (
    ImageTranscription,
)
from knowledge_flow_backend.features.scheduler.activity_utils import to_thread_with_heartbeat

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


def test_pdf_processor_builds_extractor_only_once_per_config(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    """`_get_extractor` must reuse the same extractor instance across documents
    instead of calling `_build_extractor` (and, for docling, reloading its
    OCR/layout models) on every single file."""

    class FakeExtractor:
        def extract(self, file_path: Path, work_dir: str):
            return ("# ok\n", [])

    build_calls: list[tuple[str, int]] = []

    def fake_build_extractor(extractor_name: str, docling_num_threads: int = 4):
        build_calls.append((extractor_name, docling_num_threads))
        return FakeExtractor()

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=None,
            processing=SimpleNamespace(
                normalize_profile=lambda p: p,
                get_profile_config=lambda p: SimpleNamespace(
                    process_images=False,
                    pdf=ProcessingConfig.PdfPipelineConfig(extractor="docling", do_ocr=False, docling_num_threads=2),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_current_processing_profile",
        lambda: "rich",
    )
    monkeypatch.setattr(processor, "_build_extractor", fake_build_extractor)

    for i in range(3):
        result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path / f"out{i}", f"doc-{i}")
        assert Path(result["md_file"]).exists()

    assert build_calls == [("docling", 2)]


def test_pdf_processor_builds_ocr_model_only_once_across_documents(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    """`_get_ocr_model` must reuse the same PaddleOCRmodel instance across documents
    instead of rebuilding it (and reloading its two ONNX Runtime sessions) on every
    single file — the OCR-loop equivalent of `_get_extractor`'s caching above."""
    img_path = tmp_path / "img0.png"

    class FakeExtractor:
        def extract(self, file_path: Path, work_dir: str):
            return (f"Before\n\n![]({img_path})\n\nAfter", [ImageTranscription(image_path=img_path)])

    build_calls: list[None] = []

    class FakeOcrModel:
        def __init__(self):
            build_calls.append(None)

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
        FakeOcrModel,
    )
    monkeypatch.setattr(
        processor,
        "_use_ocr",
        lambda model, images: [{"rec_texts": ["OCR extracted text"]}],
    )

    for i in range(3):
        result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path / f"out{i}", f"doc-{i}")
        assert Path(result["md_file"]).exists()

    assert len(build_calls) == 1


def test_pdf_processor_builds_image_describer_only_once_across_documents(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, sample_pdf_file: Path, tmp_path: Path):
    """`_get_image_describer` must reuse the same describer instance across documents
    instead of rebuilding it (and reloading its vision-model client) on every single
    file — the image-describer equivalent of `_get_extractor`'s caching above."""
    img_path = tmp_path / "img0.png"

    class FakeExtractor:
        def extract(self, file_path: Path, work_dir: str):
            return (f"Before\n\n![]({img_path})\n\nAfter", [ImageTranscription(image_path=img_path)])

    build_calls: list[None] = []

    def fake_build_image_describer(cfg):
        build_calls.append(None)
        return MockImageDescriber()

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.get_configuration",
        lambda: SimpleNamespace(
            vision_model=SimpleNamespace(name="fake-vision"),
            processing=SimpleNamespace(
                normalize_profile=lambda p: p,
                get_profile_config=lambda p: SimpleNamespace(
                    process_images=True,
                    pdf=ProcessingConfig.PdfPipelineConfig(extractor="docling", do_ocr=False),
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
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor.build_image_describer",
        fake_build_image_describer,
    )
    monkeypatch.setattr(
        processor,
        "_use_image_describer",
        lambda describer, img_t, ocr_r: "described",
    )

    for i in range(3):
        result = processor.convert_file_to_markdown(sample_pdf_file, tmp_path / f"out{i}", f"doc-{i}")
        assert Path(result["md_file"]).exists()

    assert len(build_calls) == 1


def test_activity_in_activity_survives_to_thread_with_heartbeat():
    """`_extract_md` runs inside a Temporal activity but off the activity's own
    coroutine, via `to_thread_with_heartbeat` (asyncio.to_thread). `_pdf_kpi_timer`
    depends on `activity.in_activity()` still reporting True on that worker thread —
    confirm it empirically rather than assuming asyncio.to_thread propagates the
    Temporal contextvar, since a silent False would make the KPI calls no-op."""
    env = ActivityEnvironment()

    def check_in_activity() -> bool:
        return activity.in_activity()

    async def activity_body() -> bool:
        return await to_thread_with_heartbeat(check_in_activity)

    assert asyncio.run(env.run(activity_body)) is True


class _FakeKpiWriter:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def timer(self, name, *, dims=None, unit="ms", labels=None, actor=None):
        self.calls.append((name, dict(dims or {})))
        return nullcontext()


class _FakeAppContext:
    def __init__(self, writer):
        self._writer = writer

    def get_kpi_writer(self):
        return self._writer


def test_pdf_kpi_timer_emits_when_in_activity_context(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor):
    env = ActivityEnvironment()
    fake_writer = _FakeKpiWriter()
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: _FakeAppContext(fake_writer)))

    def call_timer() -> bool:
        with processor._pdf_kpi_timer("knowledge_flow.pdf.image_description_latency_ms", {"pdf_stage": "image_description", "model_name": "fake-vision"}):
            pass
        return True

    async def activity_body() -> bool:
        return await to_thread_with_heartbeat(call_timer)

    assert asyncio.run(env.run(activity_body)) is True
    assert fake_writer.calls == [("knowledge_flow.pdf.image_description_latency_ms", {"pdf_stage": "image_description", "model_name": "fake-vision"})]


def test_pdf_kpi_timer_noops_outside_activity_context(processor: PdfMarkdownProcessor):
    """Outside a Temporal activity (e.g. `procbench` or a plain unit test), the timer
    must no-op without ever touching ApplicationContext — which may not be initialized."""
    with processor._pdf_kpi_timer("knowledge_flow.pdf.image_loop_latency_ms", {"pdf_stage": "image_loop", "file_type": "pdf"}):
        pass


def test_pdf_kpi_timer_swallows_setup_failure(monkeypatch: pytest.MonkeyPatch, processor: PdfMarkdownProcessor, caplog: pytest.LogCaptureFixture):
    """KPI emission must never raise into the ingestion path, even if the KPI writer
    itself is unavailable or broken."""
    env = ActivityEnvironment()

    def boom(cls):
        raise RuntimeError("kpi backend unavailable")

    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(boom))

    def call_timer() -> bool:
        with processor._pdf_kpi_timer("knowledge_flow.pdf.image_loop_latency_ms", {"pdf_stage": "image_loop", "file_type": "pdf"}):
            pass
        return True

    async def activity_body() -> bool:
        return await to_thread_with_heartbeat(call_timer)

    with caplog.at_level("WARNING"):
        assert asyncio.run(env.run(activity_body)) is True
    assert any("Failed to start timer" in record.message for record in caplog.records)


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
