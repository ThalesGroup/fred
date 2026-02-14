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
import re
from pathlib import Path
from typing import Type

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

logger = logging.getLogger(__name__)


class PdfMarkdownProcessor(BaseMarkdownProcessor):
    description = "Converts PDF documents to Markdown with optional image descriptions and table markers."

    _BACKEND_BY_NAME: dict[str, Type[AbstractDocumentBackend]] = {
        "dlparse_v4": DoclingParseV4DocumentBackend,
        "pypdfium2": PyPdfiumDocumentBackend,
    }

    def __init__(self):
        super().__init__()
        self.image_describer = None
        self._warned_missing_vision_model = False

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
            # pipeline_options.do_picture_classification = True
            # pipeline_options.do_picture_description = True
            backend_cls = self._resolve_pdf_backend(pdf_options.backend)
            if not pdf_options.do_ocr and not pdf_options.do_table_structure:
                logger.info("[PROCESSOR][PDF] OCR and Table AI are disabled. Activating High-Speed Programmatic mode.")
                pipeline_options.do_formula_enrichment = False  # Pas de math IA
                pipeline_options.do_code_enrichment = False  # Pas de code IA
                pipeline_options.force_backend_text = True  # Utilise directement le flux PDF

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

            # Generate the markdown file with placeholders for images
            doc.save_as_markdown(output_markdown_path, image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="%%ANNOTATION%%")

            # Replace placeholders with picture descriptions in the markdown file
            with open(output_markdown_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            # Add comments to identify tables
            if doc.tables:
                for i, table in enumerate(doc.tables):
                    table_id = i
                    table_md = table.export_to_markdown(doc=doc).strip()
                    if not table_md:
                        logger.warning(f"[PROCESSOR][PDF] Table export to markdown returned empty despite table having rows : ID {table_id}")
                    else:
                        annotated_table = f"""<!-- TABLE_START:id={table_id} -->\n{table_md}\n<!-- TABLE_END -->"""
                        pattern = re.escape(table_md)
                        md_content, count = re.subn(pattern, annotated_table, md_content, count=1)
                        if count == 0:
                            logger.warning(f"[PROCESSOR][PDF] Table {table_id} not found in Markdown content.")

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
