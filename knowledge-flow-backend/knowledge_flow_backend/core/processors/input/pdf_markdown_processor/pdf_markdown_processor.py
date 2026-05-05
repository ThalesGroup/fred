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


import base64
import logging
import os
from pathlib import Path
from typing import Type

import fitz
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
from knowledge_flow_backend.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.common.image_ocr import build_image_ocr

logger = logging.getLogger(__name__)

_REMOTE_OCR_NATIVE_TEXT_MIN_CHARS = 20


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
        self.image_ocr = None
        self._warned_missing_vision_model = False
        self._warned_remote_ocr_image_limit = False

    def _resolve_effective_options(self) -> tuple[IngestionProcessingProfile, bool, ProcessingConfig.PdfPipelineConfig]:
        """
        Why:
            Keep profile resolution in one place so every PDF conversion path
            uses the same runtime options.

        How:
            Call without arguments inside conversion methods to receive the
            normalized profile, the `process_images` flag, and a deep copy of
            the effective PDF options for that profile.
        """
        processing = get_configuration().processing
        current_profile = get_current_processing_profile()
        active_profile = processing.normalize_profile(current_profile)
        profile_cfg = processing.get_profile_config(active_profile)
        return active_profile, profile_cfg.process_images, profile_cfg.pdf.model_copy(deep=True)

    def _resolve_image_describer(self, process_images: bool):
        """
        Why:
            Lazily construct image-description support only when the profile
            requests it.

        How:
            Pass the effective `process_images` flag for the active profile.
            The method returns a cached describer instance or `None`.
        """
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

    def _resolve_image_ocr(self):
        """
        Why:
            Hide OCR-model lookup and adapter creation behind one cached helper.

        How:
            Call from the remote OCR path. Returns `None` when `ocr_model` is
            not configured in runtime settings.
        """
        if self.image_ocr is not None:
            return self.image_ocr
        self.image_ocr = build_image_ocr(get_configuration().ocr_model)
        return self.image_ocr

    def _resolve_pdf_backend(self, backend_name: str) -> Type[AbstractDocumentBackend]:
        """
        Why:
            Fail fast with a clear message when config references an unsupported
            Docling backend name.

        How:
            Pass the configured backend string and receive the matching Docling
            backend class.
        """
        try:
            return self._BACKEND_BY_NAME[backend_name]
        except KeyError as exc:
            allowed = ", ".join(sorted(self._BACKEND_BY_NAME))
            raise InputConversionError(f"Unsupported PDF backend '{backend_name}'. Allowed values: {allowed}") from exc

    def _should_use_remote_ocr(self, pdf_options: ProcessingConfig.PdfPipelineConfig) -> bool:
        """
        Why:
            Keep the remote/local OCR decision explicit and testable.

        How:
            Pass the effective PDF options. Returns `True` only when OCR is
            enabled for the profile and `ocr_model` is configured globally.
        """
        return bool(pdf_options.do_ocr and get_configuration().ocr_model)

    def _page_requires_remote_ocr(self, native_text: str, force_full_page_ocr: bool) -> bool:
        """
        Why:
            Avoid expensive remote OCR for born-digital pages that already
            expose enough native text.

        How:
            Pass the extracted native page text and the effective
            `force_full_page_ocr` flag. The method returns `True` when the page
            should be rasterized and sent to the remote OCR model.
        """
        if force_full_page_ocr:
            return True
        normalized = " ".join(native_text.split())
        return len(normalized) < _REMOTE_OCR_NATIVE_TEXT_MIN_CHARS

    def _render_page_to_base64(self, page: fitz.Page, scale: float) -> str:
        """
        Why:
            Remote OCR providers expect image payloads, not PDF page objects.

        How:
            Pass a PyMuPDF page and the configured PDF image scale. The page is
            rendered to PNG and returned as a base64 string.
        """
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return base64.b64encode(pixmap.tobytes("png")).decode("ascii")

    def _convert_with_remote_ocr(self, file_path: Path, pdf_options: ProcessingConfig.PdfPipelineConfig, process_images: bool) -> tuple[str, int]:
        """
        Why:
            Provide a low-CPU remote OCR path when local Docling OCR would
            overload shared worker kf.

        How:
            Call with the source PDF path, effective PDF options, and the
            active `process_images` flag. The method preserves native text when
            possible, OCRs only text-poor pages unless full-page OCR is forced,
            and returns `(markdown, remote_ocr_page_count)`.
        """
        image_ocr = self._resolve_image_ocr()
        if image_ocr is None:
            raise InputConversionError("Remote OCR was requested but no OCR model is configured.")

        if process_images and not self._warned_remote_ocr_image_limit:
            logger.warning("[PROCESSOR][PDF] Remote OCR path outputs readable page text but does not reconstruct Docling image annotations.")
            self._warned_remote_ocr_image_limit = True

        page_blocks: list[str] = []
        remote_ocr_pages = 0
        force_full_page_ocr = pdf_options.force_full_page_ocr is True

        with fitz.open(str(file_path)) as doc:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                raw_native_text = page.get_text("text")
                native_text = raw_native_text if isinstance(raw_native_text, str) else ""
                use_remote_ocr = self._page_requires_remote_ocr(native_text, force_full_page_ocr)
                page_text = native_text

                if use_remote_ocr:
                    page_image_base64 = self._render_page_to_base64(page, pdf_options.images_scale)
                    page_text = image_ocr.extract_text(page_image_base64)
                    remote_ocr_pages += 1

                page_text = page_text.strip()
                page_heading = f"## Page {page_index + 1}"
                page_blocks.append(f"{page_heading}\n\n{page_text}" if page_text else page_heading)

        return "\n\n".join(page_blocks).strip(), remote_ocr_pages

    def _convert_with_docling(self, file_path: Path, pdf_options: ProcessingConfig.PdfPipelineConfig, active_profile: IngestionProcessingProfile, process_images: bool) -> str:
        """
        Why:
            Keep the existing Docling-based conversion path intact for local OCR
            and structured extraction.

        How:
            Call with the source file and effective profile options. The method
            returns the final markdown string emitted by Docling.
        """
        image_describer = self._resolve_image_describer(process_images)
        pipeline_options = PdfPipelineOptions()

        pipeline_options.images_scale = pdf_options.images_scale
        pipeline_options.generate_picture_images = pdf_options.generate_picture_images
        pipeline_options.generate_page_images = pdf_options.generate_page_images
        pipeline_options.generate_table_images = pdf_options.generate_table_images
        pipeline_options.do_table_structure = pdf_options.do_table_structure
        pipeline_options.do_ocr = pdf_options.do_ocr
        rapid_ocr_options: RapidOcrOptions | None = None
        if pdf_options.do_ocr:
            rapid_ocr_options = RapidOcrOptions()
            if pdf_options.ocr_backend is not None:
                rapid_ocr_options.backend = pdf_options.ocr_backend
            if pdf_options.force_full_page_ocr is not None:
                rapid_ocr_options.force_full_page_ocr = pdf_options.force_full_page_ocr
            pipeline_options.ocr_options = rapid_ocr_options
        artifacts_dir = os.getenv("DOCLING_ARTIFACTS_PATH")
        if artifacts_dir:
            artifacts_path = Path(artifacts_dir).expanduser()
            pipeline_options.artifacts_path = artifacts_path
            logger.info("[PROCESSOR][PDF] Using Docling artifacts path: %s", artifacts_path)
        backend_cls = self._resolve_pdf_backend(pdf_options.backend)
        if not pdf_options.do_ocr and not pdf_options.do_table_structure:
            logger.info("[PROCESSOR][PDF] OCR and Table AI are disabled. Activating High-Speed Programmatic mode.")
            pipeline_options.do_formula_enrichment = False
            pipeline_options.do_code_enrichment = False
            pipeline_options.force_backend_text = True

        logger.info(
            "[PROCESSOR][PDF] Using profile=%s backend=%s process_images=%s ocr_mode=local ocr_backend=%s force_full_page_ocr=%s",
            active_profile.value,
            pdf_options.backend,
            process_images,
            getattr(rapid_ocr_options, "backend", None),
            getattr(rapid_ocr_options, "force_full_page_ocr", None),
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
                image_base64 = data_uri.split(",", 1)[1]
                if image_describer:
                    try:
                        description = image_describer.describe(image_base64)
                    except Exception as exc:
                        logger.warning("Image description failed: %s", exc)
                        description = "Image could not be described."
                else:
                    description = "Image description not available."
                pictures_desc.append(description)

        md_content = doc.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="%%ANNOTATION%%")
        if doc.tables:
            table_markdown = [table.export_to_markdown(doc=doc).strip() for table in doc.tables]
            md_content = _annotate_markdown_tables(md_content, table_markdown)

        for desc in pictures_desc:
            md_content = md_content.replace("%%ANNOTATION%%", desc, 1)

        return md_content

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
                    # Identity-level fields
                    "title": info.get("/Title") or None,
                    "author": info.get("/Author") or None,
                    "document_name": file_path.name,
                    # File-level fields
                    "page_count": len(reader.pages),
                    # Extras — preserved but not polluting core schema
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
            ingestion pipeline, including table and image annotations needed later.

        How:
            Call with the source PDF path, a writable output directory, and the
            current document UID. The method writes `output.md` inside `output_dir`
            and returns paths for the generated artifacts.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            active_profile, process_images, pdf_options = self._resolve_effective_options()
            output_dir.mkdir(parents=True, exist_ok=True)
            if self._should_use_remote_ocr(pdf_options):
                md_content, remote_ocr_pages = self._convert_with_remote_ocr(file_path, pdf_options, process_images)
                logger.info(
                    "[PROCESSOR][PDF] Using profile=%s backend=%s process_images=%s ocr_mode=remote remote_ocr_pages=%s force_full_page_ocr=%s",
                    active_profile.value,
                    pdf_options.backend,
                    process_images,
                    remote_ocr_pages,
                    pdf_options.force_full_page_ocr,
                )
            else:
                if pdf_options.do_ocr and not get_configuration().ocr_model:
                    logger.info("[PROCESSOR][PDF] Remote OCR model not configured; falling back to local OCR backend=%s", pdf_options.ocr_backend)
                md_content = self._convert_with_docling(file_path, pdf_options, active_profile, process_images)

            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

        except Exception as exc:
            logger.exception("[PROCESSOR][PDF] conversion failed for %s", file_path)
            raise InputConversionError(f"PdfMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": "Conversion to markdown succeeded.",
        }
