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

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Type

import pypdf
from docling.backend.abstract_backend import AbstractDocumentBackend
from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import ImageRefMode
from pypdf.errors import PdfReadError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfToMdProcessor

logger = logging.getLogger(__name__)


class PdfMarkdownProcessor(BaseMarkdownProcessor):
    description = "Converts PDF documents to Markdown with optional image descriptions, table markers, and a lightweight fallback."

    _IMAGE_PLACEHOLDER = "%%ANNOTATION%%"
    _MARKDOWN_PREVIEW_CHARS = 4000

    # Heuristics to decide whether Docling output is too text-poor (likely image-only)
    _MIN_TEXT_CHARS_FOR_RICH = 400
    _MIN_TEXT_WORDS_FOR_RICH = 80

    _BACKEND_BY_NAME: dict[str, Type[AbstractDocumentBackend]] = {
        "dlparse_v4": DoclingParseV4DocumentBackend,
        "pypdfium2": PyPdfiumDocumentBackend,
    }

    def __init__(self):
        super().__init__()
        self.image_describer = None
        self._warned_missing_vision_model = False
        self._lite_fallback = LitePdfToMdProcessor()

    # -----------------------------
    # Internal helpers
    # -----------------------------

    @classmethod
    def _markdown_text_stats(cls, md_content: str) -> tuple[int, int]:
        """
        Estimate textual richness of extracted markdown while ignoring placeholders and markdown images.
        Returns (chars_without_spaces, words).
        """
        text = md_content.replace(cls._IMAGE_PLACEHOLDER, " ")
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)  # drop markdown images
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return 0, 0
        words = len(text.split(" "))
        chars = len(re.sub(r"\s+", "", text))
        return chars, words

    @staticmethod
    def _has_markdown_images(md_content: str) -> bool:
        return bool(re.search(r"!\[[^\]]*\]\([^)]+\)", md_content))

    @staticmethod
    def _fallback_lite_options() -> LiteMarkdownOptions:
        """
        Keep fallback close to standard markdown rendering.
        """
        return LiteMarkdownOptions(
            max_chars=None,
            add_page_headings=False,
            return_per_page=False,
        )

    @classmethod
    def _should_use_lite_fallback(cls, *, md_content: str, picture_count: int) -> bool:
        """
        Trigger fallback when Docling output is text-poor.

        - If there is no text at all -> fallback.
        - Else, if the text is below thresholds and the output indicates "visual extraction"
          (placeholders/images/pictures) -> fallback.
        """
        chars, words = cls._markdown_text_stats(md_content)
        if chars == 0 and words == 0:
            return True

        has_visual_signal = (cls._IMAGE_PLACEHOLDER in md_content) or cls._has_markdown_images(md_content) or picture_count > 0
        if not has_visual_signal:
            return False

        return chars < cls._MIN_TEXT_CHARS_FOR_RICH and words < cls._MIN_TEXT_WORDS_FOR_RICH

    @staticmethod
    def _safe_model_dump(obj: Any) -> Any:
        """
        Best-effort JSON-serializable dump for pydantic-like / dataclass-like objects.
        """
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if hasattr(obj, "dict"):
            return obj.dict()
        try:
            return vars(obj)
        except Exception:
            return str(obj)

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

    def _resolve_pdf_backend(self, backend_name: str) -> Type[AbstractDocumentBackend]:
        try:
            return self._BACKEND_BY_NAME[backend_name]
        except KeyError as exc:
            allowed = ", ".join(sorted(self._BACKEND_BY_NAME))
            raise InputConversionError(f"Unsupported PDF backend '{backend_name}'. Allowed values: {allowed}") from exc

    # -----------------------------
    # Public API
    # -----------------------------

    def check_file_validity(self, file_path: Path) -> bool:
        """Checks if the PDF is readable and contains at least one page."""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                if len(reader.pages) == 0:
                    logger.warning("The PDF file %s is empty.", file_path)
                    return False
                return True
        except PdfReadError as e:
            logger.error("[PROCESSOR][PDF] Corrupted PDF file: %s - %s", file_path, e)
        except Exception as e:
            logger.error("[PROCESSOR][PDF] Unexpected error while validating %s: %s", file_path, e)
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
            logger.error("[PROCESSOR][PDF] Error extracting metadata from PDF: %s", e)
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        output_markdown_path = output_dir / "output.md"

        try:
            active_profile, process_images, pdf_options = self._resolve_effective_options()
            image_describer = self._resolve_image_describer(process_images)

            output_dir.mkdir(parents=True, exist_ok=True)

            # Initialize the DocumentConverter with PDF format options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.images_scale = pdf_options.images_scale
            pipeline_options.generate_picture_images = pdf_options.generate_picture_images
            pipeline_options.generate_page_images = pdf_options.generate_page_images
            pipeline_options.generate_table_images = pdf_options.generate_table_images
            pipeline_options.do_table_structure = pdf_options.do_table_structure
            pipeline_options.do_ocr = pdf_options.do_ocr

            artifacts_dir = os.getenv("DOCLING_ARTIFACTS_PATH")
            if artifacts_dir:
                artifacts_path = Path(artifacts_dir).expanduser()
                pipeline_options.artifacts_path = artifacts_path
                logger.info("[PROCESSOR][PDF] Using Docling artifacts path: %s", artifacts_path)

            backend_cls = self._resolve_pdf_backend(pdf_options.backend)

            # High-speed programmatic mode when no OCR and no table AI is requested
            if not pdf_options.do_ocr and not pdf_options.do_table_structure:
                logger.info("[PROCESSOR][PDF] OCR and Table AI are disabled. Activating High-Speed Programmatic mode.")
                pipeline_options.do_formula_enrichment = False
                pipeline_options.do_code_enrichment = False
                pipeline_options.force_backend_text = True

            logger.info(
                "[PROCESSOR][PDF] Using profile=%s backend=%s process_images=%s",
                active_profile.value,
                pdf_options.backend,
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

            # Decide markdown image mode based on process_images
            image_mode = ImageRefMode.PLACEHOLDER if process_images else ImageRefMode.REFERENCED
            lite_opts = self._fallback_lite_options()

            # Emit structured snapshot of effective conversion options
            effective_options_payload = {
                "document_uid": document_uid,
                "input_file": str(file_path),
                "output_markdown": str(output_markdown_path),
                "active_profile": active_profile.value,
                "profile_process_images": process_images,
                "image_describer_enabled": image_describer is not None,
                "vision_model_configured": bool(get_configuration().vision_model),
                "backend_requested": pdf_options.backend,
                "backend_resolved": backend_cls.__name__,
                "programmatic_high_speed_mode": (not pdf_options.do_ocr and not pdf_options.do_table_structure),
                "markdown_image_mode": getattr(image_mode, "value", str(image_mode)),
                "markdown_image_placeholder": self._IMAGE_PLACEHOLDER if process_images else None,
                "rich_fallback_thresholds": {
                    "min_text_chars": self._MIN_TEXT_CHARS_FOR_RICH,
                    "min_text_words": self._MIN_TEXT_WORDS_FOR_RICH,
                },
                "lite_fallback_options": self._safe_model_dump(lite_opts),
                "profile_pdf_options": self._safe_model_dump(pdf_options),
                "pipeline_options_effective": {
                    "images_scale": getattr(pipeline_options, "images_scale", None),
                    "generate_picture_images": getattr(pipeline_options, "generate_picture_images", None),
                    "generate_page_images": getattr(pipeline_options, "generate_page_images", None),
                    "generate_table_images": getattr(pipeline_options, "generate_table_images", None),
                    "do_table_structure": getattr(pipeline_options, "do_table_structure", None),
                    "do_ocr": getattr(pipeline_options, "do_ocr", None),
                    "do_formula_enrichment": getattr(pipeline_options, "do_formula_enrichment", None),
                    "do_code_enrichment": getattr(pipeline_options, "do_code_enrichment", None),
                    "force_backend_text": getattr(pipeline_options, "force_backend_text", None),
                    "artifacts_path": (str(getattr(pipeline_options, "artifacts_path", "")) or None),
                },
            }
            logger.info(
                "[PROCESSOR][PDF][CONVERT_OPTIONS] %s",
                json.dumps(effective_options_payload, ensure_ascii=False, sort_keys=True, default=str),
            )

            # Convert the PDF document to a Document object
            result = converter.convert(file_path)
            doc = result.document

            # Collect image descriptions (only if process_images)
            pictures_desc: list[str] = []
            if not doc.pictures:
                logger.info("[PROCESSOR][PDF] No pictures found in document.")
            elif process_images:
                for pic in doc.pictures:
                    if not pic.image or not pic.image.uri:
                        pictures_desc.append("Image description not available.")
                        continue
                    data_uri = str(pic.image.uri)
                    if "," not in data_uri:
                        pictures_desc.append("Image description not available.")
                        continue
                    base64 = data_uri.split(",", 1)[1]
                    if image_describer:
                        try:
                            description = image_describer.describe(base64)
                        except Exception as e:
                            logger.warning("[PROCESSOR][PDF] Image description failed: %s", e)
                            description = "Image could not be described."
                    else:
                        description = "Image description not available."
                    pictures_desc.append(description)

            # Save markdown
            doc.save_as_markdown(
                output_markdown_path,
                image_mode=image_mode,
                image_placeholder=self._IMAGE_PLACEHOLDER,
            )

            with open(output_markdown_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            if logger.isEnabledFor(logging.DEBUG):
                preview_chars = self._MARKDOWN_PREVIEW_CHARS
                markdown_preview = md_content[:preview_chars]
                if len(md_content) > preview_chars:
                    markdown_preview += "\n...[truncated]"

                # Lightweight fallback if Docling output is likely image-only / too text-poor
                logger.debug(
                    "[PROCESSOR][PDF][MARKDOWN_PRE_FALLBACK] file=%s preview_chars=%d total_chars=%d markdown_preview=\n%s",
                    file_path.name,
                    preview_chars,
                    len(md_content),
                    markdown_preview,
                )

            used_lite_fallback = False
            if self._should_use_lite_fallback(md_content=md_content, picture_count=len(doc.pictures or [])):
                logger.warning(
                    "[PROCESSOR][PDF] Docling output appears text-poor; falling back to lightweight PDF extractor for %s",
                    file_path.name,
                )
                try:
                    fallback_result = self._lite_fallback.extract(file_path, lite_opts)
                    fallback_markdown = (fallback_result.markdown or "").strip()
                    if fallback_markdown:
                        md_content = fallback_markdown
                        used_lite_fallback = True
                        logger.info(
                            "[PROCESSOR][PDF] Lightweight fallback succeeded for %s (chars=%d engine=%s)",
                            file_path.name,
                            len(fallback_markdown),
                            (fallback_result.extras or {}).get("engine"),
                        )
                except Exception as fallback_exc:
                    logger.warning(
                        "[PROCESSOR][PDF] Lightweight fallback failed for %s: %s",
                        file_path.name,
                        fallback_exc,
                    )

            # Annotate tables (Docling tables only; skip if fallback used)
            if not used_lite_fallback and doc.tables:
                for i, table in enumerate(doc.tables):
                    table_id = i
                    table_md = table.export_to_markdown(doc=doc).strip()
                    if not table_md:
                        logger.warning(
                            "[PROCESSOR][PDF] Table export to markdown returned empty despite table having rows: ID %s",
                            table_id,
                        )
                        continue
                    annotated_table = f"<!-- TABLE_START:id={table_id} -->\n{table_md}\n<!-- TABLE_END -->"
                    pattern = re.escape(table_md)
                    md_content, count = re.subn(pattern, annotated_table, md_content, count=1)
                    if count == 0:
                        logger.warning("[PROCESSOR][PDF] Table %s not found in Markdown content.", table_id)

            # Replace placeholders with descriptions only if:
            # - we did not fallback
            # - and process_images is enabled
            if not used_lite_fallback and process_images:
                for desc in pictures_desc:
                    md_content = md_content.replace(self._IMAGE_PLACEHOLDER, desc, 1)
                # Remove any remaining placeholders to avoid noisy repeated strings.
                md_content = md_content.replace(self._IMAGE_PLACEHOLDER, "")
            # In non-image mode, there should be no placeholders (REFERENCED), but keep it safe:
            elif not used_lite_fallback:
                md_content = md_content.replace(self._IMAGE_PLACEHOLDER, "")

            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

        except Exception as exc:
            logger.exception("[PROCESSOR][PDF] conversion failed for %s", file_path)
            raise InputConversionError(f"PdfMarkdownProcessorV2 failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": "Conversion to markdown succeeded.",
        }
