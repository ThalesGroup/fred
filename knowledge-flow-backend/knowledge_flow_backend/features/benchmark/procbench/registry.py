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

from typing import Dict, List

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import (
    DocxMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import (
    LiteDocxMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import (
    LitePdfMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.markdown_markdown_processor.markdown_markdown_processor import (
    MarkdownMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.pptx_markdown_processor import PptxMarkdownProcessor
from knowledge_flow_backend.core.processors.input.text_markdown_processor.text_markdown_processor import TextMarkdownProcessor

from .runner import ProcessorSpec

# Standalone PDF pipeline configs for each profile (mirrors configuration_bench.yaml).
# These let _ProfiledPdfMarkdownProcessor run without ApplicationContext.
_MEDIUM_PDF_CONFIG = ProcessingConfig.PdfPipelineConfig(
    backend="docling_parse",
    images_scale=1.5,
    generate_picture_images=False,
    generate_page_images=False,
    generate_table_images=False,
    do_table_structure=True,
    do_ocr=True,
    ocr_backend="openvino",
    force_full_page_ocr=True,
)

# Same as MEDIUM but OCR only fires on image regions, not on text that's already embedded.
# Tests whether force_full_page_ocr=True is causing garbling on born-digital PDFs.
_MEDIUM_SELECTIVE_OCR_CONFIG = ProcessingConfig.PdfPipelineConfig(
    backend="docling_parse",
    images_scale=1.5,
    generate_picture_images=False,
    generate_page_images=False,
    generate_table_images=False,
    do_table_structure=True,
    do_ocr=True,
    ocr_backend="openvino",
    force_full_page_ocr=False,
)

_RICH_PDF_CONFIG = ProcessingConfig.PdfPipelineConfig(
    backend="docling_parse",
    images_scale=2.0,
    generate_picture_images=True,
    generate_page_images=False,
    generate_table_images=False,
    do_table_structure=True,
    do_ocr=True,
    ocr_backend="openvino",
    force_full_page_ocr=True,
)


class _ProfiledPdfMarkdownProcessor(PdfMarkdownProcessor):
    """
    PdfMarkdownProcessor with a pinned profile config — no ApplicationContext required.

    Why: PdfMarkdownProcessor resolves backend, OCR settings, and image-description
    options via get_configuration() at convert-time, which requires a live
    ApplicationContext. This wrapper supplies those options directly so the benchmark
    can compare MEDIUM vs RICH without spinning up the full server stack.
    Image description (RICH process_images) is skipped — no vision model in bench.
    """

    def __init__(self, profile: IngestionProcessingProfile, pdf_config: ProcessingConfig.PdfPipelineConfig, process_images: bool = False) -> None:
        super().__init__()
        self._pinned_profile = profile
        self._pinned_pdf_config = pdf_config
        self._pinned_process_images = process_images

    def _resolve_effective_options(self) -> tuple[IngestionProcessingProfile, bool, ProcessingConfig.PdfPipelineConfig]:
        return self._pinned_profile, self._pinned_process_images, self._pinned_pdf_config.model_copy(deep=True)

    def _resolve_image_describer(self, process_images: bool):
        # Vision model not available in standalone bench mode; skip image description.
        return None


def default_registry() -> Dict[str, ProcessorSpec]:
    specs: List[ProcessorSpec] = [
        # ── PDF ────────────────────────────────────────────────────────────────
        ProcessorSpec(
            id="pdf_fast_lite",
            kind="standard",
            factory=LitePdfMarkdownProcessor,
            display_name="PDF → MD (FAST / lite pypdfium)",
            file_types=[".pdf"],
        ),
        ProcessorSpec(
            id="pdf_medium_docling",
            kind="standard",
            factory=lambda: _ProfiledPdfMarkdownProcessor(IngestionProcessingProfile.MEDIUM, _MEDIUM_PDF_CONFIG, process_images=False),
            display_name="PDF → MD (MEDIUM / force_full_page_ocr=ON)",
            file_types=[".pdf"],
        ),
        ProcessorSpec(
            id="pdf_medium_selective_ocr",
            kind="standard",
            factory=lambda: _ProfiledPdfMarkdownProcessor(IngestionProcessingProfile.MEDIUM, _MEDIUM_SELECTIVE_OCR_CONFIG, process_images=False),
            display_name="PDF → MD (MEDIUM / force_full_page_ocr=OFF)",
            file_types=[".pdf"],
        ),
        ProcessorSpec(
            id="pdf_rich_docling",
            kind="standard",
            factory=lambda: _ProfiledPdfMarkdownProcessor(IngestionProcessingProfile.RICH, _RICH_PDF_CONFIG, process_images=False),
            display_name="PDF → MD (RICH / Docling + OCR + images)",
            file_types=[".pdf"],
        ),
        # ── DOCX ───────────────────────────────────────────────────────────────
        ProcessorSpec(
            id="docx_fast_lite",
            kind="standard",
            factory=LiteDocxMarkdownProcessor,
            display_name="DOCX → MD (FAST / lite)",
            file_types=[".docx"],
        ),
        ProcessorSpec(
            id="docx_standard_pandoc",
            kind="standard",
            factory=DocxMarkdownProcessor,
            display_name="DOCX → MD (MEDIUM+RICH / Pandoc)",
            file_types=[".docx"],
        ),
        # ── Other formats ──────────────────────────────────────────────────────
        ProcessorSpec(
            id="pptx_standard_pandoc",
            kind="standard",
            factory=PptxMarkdownProcessor,
            display_name="PPTX → MD (Standard/Pandoc)",
            file_types=[".pptx"],
        ),
        ProcessorSpec(
            id="text_standard_plain",
            kind="standard",
            factory=TextMarkdownProcessor,
            display_name="Text → MD (Standard)",
            file_types=[".txt"],
        ),
        ProcessorSpec(
            id="markdown_standard_passthrough",
            kind="standard",
            factory=MarkdownMarkdownProcessor,
            display_name="Markdown → MD (Standard)",
            file_types=[".md"],
        ),
    ]

    return {s.id: s for s in specs}
