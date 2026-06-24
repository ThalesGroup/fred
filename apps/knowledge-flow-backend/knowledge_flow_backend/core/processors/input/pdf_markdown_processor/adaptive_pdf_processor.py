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
Adaptive PDF Markdown processor — Issue #1191.

This module wraps PdfMarkdownProcessor with a pre-flight diagnostic phase.
Instead of blindly applying the profile's PDF pipeline configuration, it first
analyses the document structure and then overrides the PDF pipeline settings
to route the document to the most efficient backend.

Routing strategy
----------------
PdfNature.TEXT_NATIVE
    Born-digital, simple text flow.
    Override: disable OCR and table structure; enable high-speed programmatic
    mode.  Preserves tables=False and OCR=False for speed.

PdfNature.COMPLEX_LAYOUT
    Embedded text but rich typography or dense layout (tables, multi-column).
    Override: keep OCR disabled (text is selectable) but enable table
    structure extraction so Docling can parse tables accurately.

PdfNature.SCANNED
    No or very little extractable text — image-only pages dominate.
    Override: force OCR on every page (force_full_page_ocr=True) and
    enable table structure extraction.

In all cases the override only affects the PdfPipelineConfig; the active
ingestion profile's other settings (process_images, text splitter, etc.)
are unchanged.

Usage
-----
Wire the class in your processing profile's input_processors list::

    processing:
      profiles:
        medium:
          input_processors:
            - suffix: ".pdf"
              class_path: >
                knowledge_flow_backend.core.processors.input
                .pdf_markdown_processor.adaptive_pdf_processor
                .AdaptivePdfMarkdownProcessor

The processor is a drop-in replacement for PdfMarkdownProcessor and
requires no additional configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path

from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_document_analyzer import (
    PdfDocumentAnalyzer,
    PdfNature,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
)

logger = logging.getLogger(__name__)


def _build_text_native_config(base: ProcessingConfig.PdfPipelineConfig) -> ProcessingConfig.PdfPipelineConfig:
    """
    Return a copy of *base* tuned for born-digital, text-stream PDFs.

    Disables OCR and table-structure AI; enables Docling's force_backend_text
    shortcut (set implicitly by PdfMarkdownProcessor when both flags are off).
    """
    return base.model_copy(
        update={
            "do_ocr": False,
            "do_table_structure": False,
        }
    )


def _build_complex_layout_config(base: ProcessingConfig.PdfPipelineConfig) -> ProcessingConfig.PdfPipelineConfig:
    """
    Return a copy of *base* tuned for PDFs with tables or complex typography.

    Text is selectable so OCR is not required.  Table structure extraction is
    enabled so Docling can reconstruct table semantics accurately.
    """
    return base.model_copy(
        update={
            "do_ocr": False,
            "do_table_structure": True,
        }
    )


def _build_scanned_config(base: ProcessingConfig.PdfPipelineConfig) -> ProcessingConfig.PdfPipelineConfig:
    """
    Return a copy of *base* tuned for scanned / image-only PDFs.

    Enables OCR with force_full_page_ocr so every page is run through the OCR
    engine regardless of whether pypdf reports any embedded text.  Also enables
    table structure extraction because scanned documents often contain tables.
    """
    return base.model_copy(
        update={
            "do_ocr": True,
            "force_full_page_ocr": True,
            "do_table_structure": True,
        }
    )


_NATURE_CONFIG_BUILDERS = {
    PdfNature.TEXT_NATIVE: _build_text_native_config,
    PdfNature.COMPLEX_LAYOUT: _build_complex_layout_config,
    PdfNature.SCANNED: _build_scanned_config,
}


class AdaptivePdfMarkdownProcessor(PdfMarkdownProcessor):
    """
    PdfMarkdownProcessor with an automatic pre-flight diagnostic.

    Before converting a document this processor runs PdfDocumentAnalyzer to
    classify the document as TEXT_NATIVE, COMPLEX_LAYOUT, or SCANNED and
    then overrides the PdfPipelineConfig accordingly.  All other aspects of
    the active ingestion profile are preserved unchanged.

    The analysis overhead is negligible: only a handful of pages are sampled
    with pypdf (no rendering, no model inference).

    This class is a strict drop-in replacement for PdfMarkdownProcessor.
    """

    description = "Adaptive PDF-to-Markdown converter that auto-detects document type (text/scanned/complex) and routes to the optimal extraction backend."

    def __init__(self) -> None:
        super().__init__()
        self._analyzer = PdfDocumentAnalyzer()

    def _adapt_config(
        self,
        file_path: Path,
        active_profile: IngestionProcessingProfile,
        base_pdf_config: ProcessingConfig.PdfPipelineConfig,
    ) -> ProcessingConfig.PdfPipelineConfig:
        """
        Analyse *file_path* and return an overridden PdfPipelineConfig.

        Falls back gracefully to the base config when analysis fails so that
        existing behaviour is preserved in error scenarios.
        """
        try:
            result = self._analyzer.analyze(file_path)
        except Exception as exc:
            logger.warning(
                "[PROCESSOR][PDF][ADAPTIVE] Pre-flight analysis failed for '%s'; using base config: %s",
                file_path.name,
                exc,
            )
            return base_pdf_config

        builder = _NATURE_CONFIG_BUILDERS[result.nature]
        adapted = builder(base_pdf_config)

        logger.info(
            "[PROCESSOR][PDF][ADAPTIVE] '%s' classified as %s "
            "(avg_chars=%.1f fonts=%d pages=%d) — profile=%s "
            "ocr=%s table_structure=%s",
            file_path.name,
            result.nature.value,
            result.avg_chars_per_page,
            result.unique_font_count,
            result.page_count,
            active_profile.value,
            adapted.do_ocr,
            adapted.do_table_structure,
        )
        return adapted

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Run the pre-flight diagnostic, patch the effective options, then
        delegate to PdfMarkdownProcessor.convert_file_to_markdown.

        The monkey-patching of _resolve_effective_options is intentional: it
        lets us reuse all parent logic (remote OCR, Docling pipeline setup,
        image description, table annotation) without duplicating it.
        """
        active_profile, process_images, base_pdf_config = self._resolve_effective_options()
        adapted_pdf_config = self._adapt_config(file_path, active_profile, base_pdf_config)

        original_resolve = self._resolve_effective_options

        def _patched_resolve() -> tuple[IngestionProcessingProfile, bool, ProcessingConfig.PdfPipelineConfig]:
            return active_profile, process_images, adapted_pdf_config

        self._resolve_effective_options = _patched_resolve  # type: ignore[method-assign]
        try:
            return super().convert_file_to_markdown(file_path, output_dir, document_uid)
        finally:
            self._resolve_effective_options = original_resolve  # type: ignore[method-assign]
