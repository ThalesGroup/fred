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
import re
from pathlib import Path
from typing import Optional, Type

import pypdf
from docling.backend.abstract_backend import AbstractDocumentBackend
from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import RapidOcrOptions, ThreadedPdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import ImageRefMode
from fred_core.common import ModelConfiguration
from pypdf.errors import PdfReadError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.common.ocr.base_pdf_ocr_extractor import RemotePdfOcrResult
from knowledge_flow_backend.core.processors.input.common.ocr.pdf_ocr_factory import build_pdf_ocr_extractor

logger = logging.getLogger(__name__)
_MARKDOWN_IMAGE_REFERENCE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


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
        self._warned_unsupported_ocr_model = False

    def _resolve_effective_options(self) -> tuple[IngestionProcessingProfile, bool, ProcessingConfig.PdfPipelineConfig]:
        processing = get_configuration().processing
        current_profile = get_current_processing_profile()
        active_profile = processing.normalize_profile(current_profile)
        profile_cfg = processing.get_profile_config(active_profile)
        return active_profile, profile_cfg.process_images, profile_cfg.pdf.model_copy(deep=True)

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

    def _select_boundary_lines(self, text: str, *, head: int = 8, tail: int = 8) -> tuple[list[str], list[str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[:head], lines[-tail:] if len(lines) > tail else []

    def extract_guardrail_text(self, file_path: Path) -> str | None:
        try:
            reader = pypdf.PdfReader(str(file_path))
        except Exception as e:
            logger.warning("[PDF][GUARDRAIL] Failed to open %s: %s", file_path, e)
            return None

        page_count = len(reader.pages)
        if page_count == 0:
            return None

        page_indexes: list[int] = [0]
        if page_count > 1:
            page_indexes.append(page_count - 1)

        parts: list[str] = []

        for page_index in page_indexes:
            try:
                text = reader.pages[page_index].extract_text() or ""
            except Exception as e:
                logger.warning("[PDF][GUARDRAIL] Failed to extract page %s from %s: %s", page_index + 1, file_path, e)
                continue

            head_lines, tail_lines = self._select_boundary_lines(text, head=8, tail=8)

            if head_lines:
                if parts:
                    parts.append("")
                parts.append(f"PAGE_{page_index + 1}_TOP:")
                parts.extend(head_lines)

            if tail_lines:
                if parts:
                    parts.append("")
                parts.append(f"PAGE_{page_index + 1}_BOTTOM:")
                parts.extend(tail_lines)

        result = "\n".join(parts).strip()
        if result:
            logger.info(
                "[PDF][GUARDRAIL] Extracted guardrail text for %s:\n%s",
                file_path.name,
                result,
            )
        return result or None

    def _resolve_ocr_model_config(self) -> Optional["ModelConfiguration"]:
        """
        Why:
            Keep remote OCR lookup resilient in standalone benchmark/test paths
            where no global ApplicationContext is available.

        How:
            Call before attempting remote OCR. The method returns the configured
            OCR model when available, otherwise `None`.
        """
        try:
            return get_configuration().ocr_model
        except Exception:
            return None

    def _describe_remote_ocr_images(
        self,
        ocr_result: RemotePdfOcrResult,
        image_describer,
    ) -> str:
        """
        Why:
            Replace remote OCR image references such as `img-12.jpeg` with
            `vision_model` descriptions so the remote OCR path preserves the
            same image-enrichment behavior as the local Docling path.

        How:
            Pass the structured OCR result and an initialized image describer.
            The helper matches markdown image targets against OCR image IDs and
            substitutes each reference with the generated description.

        Example:
            `markdown = self._describe_remote_ocr_images(result, image_describer)`
        """
        markdown = ocr_result.to_markdown()
        images_by_id = {image.image_id: image.image_base64 for page in ocr_result.pages for image in page.images if image.image_id and image.image_base64}
        if not images_by_id:
            return markdown

        def replace_image(match: re.Match[str]) -> str:
            image_ref = match.group(1).strip()
            image_base64 = images_by_id.get(image_ref)
            if not image_base64:
                return match.group(0)
            try:
                return image_describer.describe(image_base64)
            except Exception as exc:
                logger.warning("[PROCESSOR][PDF] Remote OCR image description failed for %s: %s", image_ref, exc)
                return "Image could not be described."

        return _MARKDOWN_IMAGE_REFERENCE_PATTERN.sub(replace_image, markdown)

    def _convert_with_remote_ocr(self, file_path: Path, output_markdown_path: Path, image_describer) -> bool:
        """
        Why:
            Offload PDF OCR to a remote API model when one is configured, so
            constrained worker pods can avoid the heaviest local OCR path.

        How:
            Call with the source PDF path and target markdown path. The method
            returns `True` when remote OCR succeeded and wrote the markdown,
            otherwise `False` so the caller can fall back to local Docling OCR.

        Example:
            `self._convert_with_remote_ocr(pdf_path, output_md, image_describer)`
        """
        ocr_cfg = self._resolve_ocr_model_config()
        extractor = build_pdf_ocr_extractor(ocr_cfg)
        if extractor is None:
            if ocr_cfg and not self._warned_unsupported_ocr_model:
                logger.warning(
                    "[PROCESSOR][PDF] OCR model '%s' is configured but not supported for remote OCR; falling back to local Docling OCR.",
                    ocr_cfg.name,
                )
                self._warned_unsupported_ocr_model = True
            return False
        assert ocr_cfg is not None

        logger.info(
            "[PROCESSOR][PDF] Using remote OCR model provider=%s name=%s for %s",
            ocr_cfg.provider,
            ocr_cfg.name,
            file_path.name,
        )
        ocr_result = extractor.extract_pdf_result(file_path, include_images=image_describer is not None)
        markdown = ocr_result.to_markdown()
        if image_describer is not None:
            markdown = self._describe_remote_ocr_images(ocr_result, image_describer)
        output_markdown_path.write_text(markdown, encoding="utf-8")
        return True

    def _resolve_pdf_backend(self, backend_name: str) -> Type[AbstractDocumentBackend]:
        try:
            return self._BACKEND_BY_NAME[backend_name]
        except KeyError as exc:
            allowed = ", ".join(sorted(self._BACKEND_BY_NAME))
            raise InputConversionError(f"Unsupported PDF backend '{backend_name}'. Allowed values: {allowed}") from exc

    def _build_pipeline_options(
        self,
        pdf_options: ProcessingConfig.PdfPipelineConfig,
    ) -> tuple[ThreadedPdfPipelineOptions, RapidOcrOptions | None]:
        """
        Why:
            Centralize Docling pipeline construction so Fred can tune the
            threaded PDF pipeline in one place and keep conversion behavior
            stable across profiles and benchmarks.

        How:
            Pass the resolved per-profile PDF config. The helper returns a
            fully populated `ThreadedPdfPipelineOptions` plus the effective
            RapidOCR options used for logging.
        """
        pipeline_options = ThreadedPdfPipelineOptions()
        pipeline_options.images_scale = pdf_options.images_scale
        pipeline_options.generate_picture_images = pdf_options.generate_picture_images
        pipeline_options.generate_page_images = pdf_options.generate_page_images
        pipeline_options.generate_table_images = pdf_options.generate_table_images
        pipeline_options.do_table_structure = pdf_options.do_table_structure
        pipeline_options.do_ocr = pdf_options.do_ocr
        pipeline_options.ocr_batch_size = pdf_options.ocr_batch_size
        pipeline_options.layout_batch_size = pdf_options.layout_batch_size
        pipeline_options.table_batch_size = pdf_options.table_batch_size
        pipeline_options.batch_polling_interval_seconds = pdf_options.batch_polling_interval_seconds
        pipeline_options.queue_max_size = pdf_options.queue_max_size

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

        return pipeline_options, rapid_ocr_options

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
            image_describer = self._resolve_image_describer(process_images)
            output_dir.mkdir(parents=True, exist_ok=True)
            if pdf_options.do_ocr:
                try:
                    if self._convert_with_remote_ocr(file_path, output_markdown_path, image_describer):
                        return {
                            "doc_dir": str(output_dir),
                            "md_file": str(output_markdown_path),
                            "message": "Remote OCR conversion to markdown succeeded.",
                        }
                except Exception as exc:
                    logger.warning(
                        "[PROCESSOR][PDF] Remote OCR failed for %s; falling back to local Docling OCR: %s",
                        file_path.name,
                        exc,
                    )
            pipeline_options, rapid_ocr_options = self._build_pipeline_options(pdf_options)
            # pipeline_options.do_picture_classification = True
            # pipeline_options.do_picture_description = True
            backend_cls = self._resolve_pdf_backend(pdf_options.backend)
            if not pdf_options.do_ocr and not pdf_options.do_table_structure:
                logger.info("[PROCESSOR][PDF] OCR and Table AI are disabled. Activating High-Speed Programmatic mode.")
                pipeline_options.do_formula_enrichment = False  # Pas de math IA
                pipeline_options.do_code_enrichment = False  # Pas de code IA
                pipeline_options.force_backend_text = True  # Utilise directement le flux PDF

            logger.info(
                "[PROCESSOR][PDF] Using profile=%s backend=%s process_images=%s ocr_backend=%s force_full_page_ocr=%s ocr_batch_size=%s layout_batch_size=%s table_batch_size=%s queue_max_size=%s batch_polling_interval_seconds=%s",
                active_profile.value,
                pdf_options.backend,
                process_images,
                getattr(rapid_ocr_options, "backend", None),
                getattr(rapid_ocr_options, "force_full_page_ocr", None),
                pipeline_options.ocr_batch_size,
                pipeline_options.layout_batch_size,
                pipeline_options.table_batch_size,
                pipeline_options.queue_max_size,
                pipeline_options.batch_polling_interval_seconds,
            )
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                        backend=backend_cls,
                    )
                }
            )

            # Convert the PDF document to a Document object
            result = converter.convert(file_path)
            doc = result.document

            # Extract the pictures descriptions from the document
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
                    base64 = data_uri.split(",", 1)[1]  # Extract base64 part from the data URI
                    if image_describer:
                        try:
                            description = image_describer.describe(base64)
                        except Exception as e:
                            logger.warning(f"Image description failed: {e}")
                            description = "Image could not be described."
                    else:
                        description = "Image description not available."
                    pictures_desc.append(description)

            md_content = doc.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="%%ANNOTATION%%")

            # Add comments to identify tables
            if doc.tables:
                table_markdown = [table.export_to_markdown(doc=doc).strip() for table in doc.tables]
                md_content = _annotate_markdown_tables(md_content, table_markdown)

            for desc in pictures_desc:
                md_content = md_content.replace("%%ANNOTATION%%", desc, 1)

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
