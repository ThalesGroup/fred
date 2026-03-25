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


import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Type

import pypdf
from docling.backend.abstract_backend import AbstractDocumentBackend
from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import ImageRefMode
from pypdf.errors import PdfReadError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfMarkdownProcessor

logger = logging.getLogger(__name__)


class PdfComplexity(str, Enum):
    """Supported PDF families used by the document-aware routing logic."""

    DIGITALLY_BORN_TEXT_PDF = "digitally_born_text_pdf"
    SCANNED_PDF = "scanned_pdf"
    SCIENTIFIC_PDF = "scientific_pdf"
    TABLE_HEAVY = "table_heavy"
    SLIDE_LIKE = "slide_like"
    MULTICOLUMN = "multicolumn"


@dataclass(frozen=True)
class PdfComplexityStats:
    """
    Why:
        Keep PDF routing decisions explicit and testable before the expensive
        conversion step starts.

    How:
        Populate this structure from a lightweight PDF inspection pass, then feed
        it into `PdfMarkdownProcessor._classify_pdf_kind()`.
    """

    page_count: int
    total_text_chars: int
    pages_without_text: int
    pages_with_images: int

    @property
    def average_text_chars_per_page(self) -> float:
        """
        Why:
            Expose a stable density signal for distinguishing simple digital PDFs
            from scanned or layout-heavy documents.

        How:
            Read the computed average after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 0.0
        return self.total_text_chars / self.page_count

    @property
    def textless_page_ratio(self) -> float:
        """
        Why:
            Many scanned or image-heavy PDFs have little extractable text on a
            large share of pages.

        How:
            Read the computed ratio after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 1.0
        return self.pages_without_text / self.page_count

    @property
    def image_page_ratio(self) -> float:
        """
        Why:
            Different document families show very different image densities, which
            helps with early routing before full parsing.

        How:
            Read the computed ratio after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 0.0
        return self.pages_with_images / self.page_count


def _annotate_markdown_tables(md_content: str, tables_markdown: list[str]) -> str:
    """
    Why:
        Wrap exported Markdown tables with stable markers for downstream chunking
        without letting replacement logic reinterpret table text.

    How:
        Pass the full Markdown content and the ordered table Markdown exports.
        The first literal match of each table is wrapped with TABLE_START/TABLE_END
        markers and the updated Markdown string is returned.
    """
    for table_id, table_md in enumerate(tables_markdown):
        if not table_md:
            logger.warning("[PROCESSOR][PDF] Table export to markdown returned empty despite table having rows : ID %s", table_id)
            continue

        annotated_table = f"""<!-- TABLE_START:id={table_id} -->\n{table_md}\n<!-- TABLE_END -->"""
        if table_md not in md_content:
            logger.warning("[PROCESSOR][PDF] Table %s not found in Markdown content.", table_id)
            continue

        md_content = md_content.replace(table_md, annotated_table, 1)

    return md_content


class PdfMarkdownProcessor(BaseMarkdownProcessor):
    description = "Converts PDF documents to Markdown with optional image descriptions and table markers."

    _BACKEND_BY_NAME: dict[str, Type[AbstractDocumentBackend]] = {
        "dlparse_v4": DoclingParseV4DocumentBackend,
        "pypdfium2": PyPdfiumDocumentBackend,
        "docling_parse": DoclingParseDocumentBackend,
    }

    def __init__(self):
        super().__init__()
        self.image_describer = None
        self._warned_missing_vision_model = False
        self._lite_processor = LitePdfMarkdownProcessor()

    def _collect_pdf_complexity_stats(self, file_path: Path) -> PdfComplexityStats:
        """
        Why:
            Route PDFs to a lightweight or layout-aware pipeline based on the
            actual document shape instead of a caller-selected profile name.

        How:
            Call with a local PDF path. The method performs a best-effort,
            low-cost inspection with `pypdf` and returns the aggregated routing
            signals used by the conversion pipeline.
        """
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)
            total_text_chars = 0
            pages_without_text = 0
            pages_with_images = 0

            for page in reader.pages:
                try:
                    page_text = (page.extract_text() or "").strip()
                except Exception:
                    page_text = ""
                total_text_chars += len(page_text)
                if not page_text:
                    pages_without_text += 1

                try:
                    page_images = list(page.images)
                except Exception:
                    page_images = []
                if page_images:
                    pages_with_images += 1

        return PdfComplexityStats(
            page_count=page_count,
            total_text_chars=total_text_chars,
            pages_without_text=pages_without_text,
            pages_with_images=pages_with_images,
        )

    def _classify_pdf_kind(self, stats: PdfComplexityStats) -> PdfComplexity:
        """
        Why:
            Use document-family labels that match the parser tradeoffs we care
            about instead of a binary simple/complex split.

        How:
            Pass the stats from `_collect_pdf_complexity_stats()`. The returned
            label is one of the PDF families used by the document-aware router.
        """
        if stats.page_count <= 0:
            return PdfComplexity.SCANNED_PDF

        if stats.textless_page_ratio >= 0.30 or stats.total_text_chars < max(400, stats.page_count * 120):
            return PdfComplexity.SCANNED_PDF

        if stats.image_page_ratio >= 0.60 and stats.average_text_chars_per_page < 700:
            return PdfComplexity.SLIDE_LIKE

        if stats.image_page_ratio >= 0.50 and stats.average_text_chars_per_page < 1400:
            return PdfComplexity.TABLE_HEAVY

        if stats.page_count >= 4 and stats.average_text_chars_per_page >= 2200:
            return PdfComplexity.SCIENTIFIC_PDF

        if stats.page_count >= 2 and 900 <= stats.average_text_chars_per_page < 2200:
            return PdfComplexity.MULTICOLUMN

        return PdfComplexity.DIGITALLY_BORN_TEXT_PDF

    def _select_conversion_mode(self, document_kind: PdfComplexity) -> Literal["lite", "docling"]:
        """
        Why:
            Keep the routing outcome explicit so the fast digital-text path and
            the richer layout-aware path can evolve independently.

        How:
            Pass the result of `_classify_pdf_kind()`. The method returns the
            implementation family to execute for this PDF.
        """
        if document_kind == PdfComplexity.DIGITALLY_BORN_TEXT_PDF:
            return "lite"
        return "docling"

    def _resolve_complex_options(self) -> tuple[bool, str]:
        """
        Why:
            Keep one explicit, deterministic configuration baseline for complex
            PDFs while letting the active ingestion profile control image description.

        How:
            Call before Docling conversion. The return value contains whether
            image descriptions are enabled and which Docling backend to use.
        """
        from knowledge_flow_backend.common.processing_profile_context import get_current_processing_profile

        profile = get_current_processing_profile()
        profile_cfg = get_configuration().processing.get_profile_config(profile)
        return profile_cfg.process_images, "docling_parse"

    def _resolve_image_describer(self, process_images: bool):
        if not process_images:
            return None
        if self.image_describer is not None:
            return self.image_describer
        if not get_configuration().vision_model:
            if not self._warned_missing_vision_model:
                logger.warning("[PROCESSOR][PDF] Vision model configuration is missing while process_images is enabled.")
                self._warned_missing_vision_model = True
            return None
        self.image_describer = build_image_describer(get_configuration().vision_model)
        return self.image_describer

    def _resolve_pdf_backend(self, backend_name: str) -> Type[AbstractDocumentBackend]:
        try:
            return self._BACKEND_BY_NAME[backend_name]
        except KeyError as exc:
            allowed = ", ".join(sorted(self._BACKEND_BY_NAME))
            raise InputConversionError(f"Unsupported PDF backend '{backend_name}'. Allowed values: {allowed}") from exc

    def _convert_with_lite_pipeline(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Why:
            Reuse the existing lightweight PDF converter for digitally-born PDFs
            instead of duplicating its fast-path logic here.

        How:
            Call with the same arguments as `convert_file_to_markdown()`. The
            method delegates to `LitePdfMarkdownProcessor` and returns its
            standard output payload.
        """
        return self._lite_processor.convert_file_to_markdown(file_path, output_dir, document_uid)

    def _convert_with_docling_pipeline(self, file_path: Path, output_dir: Path) -> None:
        """
        Why:
            Centralize the layout-aware PDF conversion path used for complex or
            scanned PDFs.

        How:
            Call with the source PDF path and a writable output directory. The
            method writes `output.md` in place using Docling and post-processes
            tables and image placeholders.
        """
        output_markdown_path = output_dir / "output.md"
        process_images, backend_name = self._resolve_complex_options()
        image_describer = self._resolve_image_describer(process_images)
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = 2.0
        pipeline_options.generate_picture_images = process_images
        pipeline_options.generate_page_images = True
        pipeline_options.generate_table_images = False
        pipeline_options.do_table_structure = True
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = RapidOcrOptions()

        artifacts_dir = os.getenv("DOCLING_ARTIFACTS_PATH")
        if artifacts_dir:
            artifacts_path = Path(artifacts_dir).expanduser()
            pipeline_options.artifacts_path = artifacts_path
            logger.info("[PROCESSOR][PDF] Using Docling artifacts path: %s", artifacts_path)

        backend_cls = self._resolve_pdf_backend(backend_name)
        logger.info(
            "[PROCESSOR][PDF] Using document-aware complex pipeline backend=%s process_images=%s",
            backend_name,
            process_images,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=backend_cls,
                )
            }
        )

        result = converter.convert(file_path)
        doc = result.document

        pictures_desc = []
        if not doc.pictures:
            logger.info("[PROCESSOR][PDF] No pictures found in document.")
        elif process_images:
            for pic in doc.pictures:
                if not pic.image or not pic.image.uri:
                    pictures_desc.append("Image data not available.")
                    continue
                data_uri = str(pic.image.uri)
                if "," not in data_uri:
                    pictures_desc.append("Image data not available.")
                    continue
                base64 = data_uri.split(",", 1)[1]
                if image_describer:
                    try:
                        description = image_describer.describe(base64)
                    except Exception as e:
                        logger.warning(f"Image description failed: {e}")
                        description = "Image could not be described."
                else:
                    description = "Image description not available."
                pictures_desc.append(description)

        doc.save_as_markdown(output_markdown_path, image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="%%ANNOTATION%%")

        with open(output_markdown_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        if doc.tables:
            table_markdown = [table.export_to_markdown(doc=doc).strip() for table in doc.tables]
            md_content = _annotate_markdown_tables(md_content, table_markdown)

        for desc in pictures_desc:
            md_content = md_content.replace("%%ANNOTATION%%", desc, 1)

        with open(output_markdown_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    def check_file_validity(self, file_path: Path) -> bool:
        """Checks if the PDF is readable and contains at least one page."""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                if len(reader.pages) == 0:
                    logger.warning(f"The PDF file {file_path} is empty.")
                    return False
                return True
        except PdfReadError as e:
            logger.error(f"[PROCESSOR][PDF] Corrupted PDF file: {file_path} - {e}")
        except Exception as e:
            logger.error(f"[PROCESSOR][PDF] Unexpected error while validating {file_path}: {e}")
        return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """Extracts metadata from the PDF file."""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                info = reader.metadata or {}

                return {
                    "title": info.get("/Title") or None,
                    "author": info.get("/Author") or None,
                    "document_name": file_path.name,
                    "page_count": len(reader.pages),
                    "extras": {
                        "pdf.subject": info.get("/Subject") or None,
                        "pdf.producer": info.get("/Producer") or None,
                        "pdf.creator": info.get("/Creator") or None,
                    },
                }
        except Exception as e:
            logger.error(f"[PROCESSOR][PDF] Error extracting metadata from PDF: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Why:
            Convert an input PDF into the normalized Markdown artifact used by the
            ingestion pipeline while selecting the parsing strategy from the PDF
            itself instead of caller-facing profile names.

        How:
            Call with the source PDF path, a writable output directory, and the
            current document UID. The method writes `output.md` inside `output_dir`
            and returns paths for the generated artifacts.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            stats = self._collect_pdf_complexity_stats(file_path)
            document_kind = self._classify_pdf_kind(stats)
            conversion_mode = self._select_conversion_mode(document_kind)
            logger.info(
                "[PROCESSOR][PDF] Document-aware routing kind=%s mode=%s pages=%s total_text_chars=%s textless_pages=%s image_pages=%s avg_text_per_page=%.1f",
                document_kind.value,
                conversion_mode,
                stats.page_count,
                stats.total_text_chars,
                stats.pages_without_text,
                stats.pages_with_images,
                stats.average_text_chars_per_page,
            )

            if conversion_mode == "lite":
                return self._convert_with_lite_pipeline(file_path, output_dir, document_uid)

            self._convert_with_docling_pipeline(file_path, output_dir)

        except Exception as exc:
            logger.exception("[PROCESSOR][PDF] conversion failed for %s", file_path)
            raise InputConversionError(f"PdfMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": "Conversion to markdown succeeded.",
        }
