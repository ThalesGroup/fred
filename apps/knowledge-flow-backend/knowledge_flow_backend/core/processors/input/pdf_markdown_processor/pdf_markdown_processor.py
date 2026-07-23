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

from __future__ import annotations

import base64
import logging
import re
import shutil
import tempfile
from pathlib import Path

import pypdf
from markitdown import MarkItDown
from pypdf.errors import PdfReadError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.common.processing_profile_context import get_current_processing_profile
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.common.ocr.paddle_ocr import PaddleOCRmodel
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    collapse_whitespace,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.base_pdf_extractor import BasePdfExtractor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor import DoclingPdfExtractor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pymupdf_processor import PyMuPdfExtractor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import ImageTranscription
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.images_feature_extraction import calcul_canny, calcul_pourcentage_area

logger = logging.getLogger(__name__)

_EXTRACTORS: dict[str, type[BasePdfExtractor]] = {
    "docling": DoclingPdfExtractor,
    "pymupdf": PyMuPdfExtractor,
}


class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    PDF → Markdown processor with optional image transcription.

    Text extraction engine is selected via `processing.profiles.<profile>.pdf.extractor`:
    - 'pymupdf'  — fast, page-oriented, deterministic (default).
    - 'docling'  — layout-aware, table-structure, OCR-capable.

    Image transcription (when enabled by processing profile):
    - PaddleOCR detects text regions in images.
    - A VLM is called for images with low text coverage or significant visual content.
    """

    DESCRIPTION = "PDF-to-Markdown converter"
    BASE_FOLDER = "/tmp"

    def _remove_all_files(self, folder):
        shutil.rmtree(folder, ignore_errors=True)

    def _normalize_whitespace(self, text: str) -> str:
        return collapse_whitespace(text)

    def _extract_with_markitdown(self, file_path: Path) -> str:
        try:
            mark_it_down = MarkItDown()
            converted = mark_it_down.convert(str(file_path))
            md_text = converted.markdown
            md_text = self._normalize_whitespace(md_text)
            return md_text
        except Exception as e:
            raise RuntimeError("Markitdown not available for PDF conversion") from e

    def _use_ocr(self, ocr_model, images_transcription):
        try:
            image_paths = [str(it.image_path) for it in images_transcription]
            return ocr_model.predict(image_paths)
        except Exception as e:
            logger.warning("[PDF][PROCESSOR] Failed to use ocr model : %s | Error : ", ocr_model.backend_name, e)
            return []

    def _use_image_describer(self, image_describer, images_transcription: ImageTranscription, ocr_result) -> str:
        """
        Decide how to transcribe one image given its OCR result.

        - No detected boxes + large image with edges → VLM description.
        - High text coverage (>40 %) → OCR text only.
        - Low coverage but several boxes with edges → VLM description.
        - Otherwise → OCR text only.
        """
        try:
            extracted_text_by_ocr = " ".join(ocr_result["rec_texts"])

            image = ocr_result["doc_preprocessor_res"]["output_img"]
            img_shape = image.shape
            rec_boxes = ocr_result["rec_boxes"]

            number_boxes = len(rec_boxes)
            coverage_percentage = calcul_pourcentage_area(img_shape, rec_boxes)
            canny_percentage = calcul_canny(image, rec_boxes)

            extracted_text = ""
            if number_boxes == 0:
                if (img_shape[0] > 150 or img_shape[1] > 150) and canny_percentage > 4:
                    image_base64 = base64.b64encode(images_transcription.image_path.read_bytes()).decode("utf-8")
                    extracted_text = image_describer.describe(image_base64)
                else:
                    extracted_text = ""
            else:
                if coverage_percentage > 40:
                    extracted_text = extracted_text_by_ocr
                elif number_boxes > 3 and canny_percentage > 2:
                    image_base64 = base64.b64encode(images_transcription.image_path.read_bytes()).decode("utf-8")
                    extracted_text = image_describer.describe(image_base64)
                else:
                    extracted_text = extracted_text_by_ocr

            return extracted_text

        except Exception as e:
            raise RuntimeError(f"[PDF][PROCESSOR] Failed to use image describer : {get_configuration().vision_model}") from e

    def _build_extractor(self, extractor_name: str, docling_num_threads: int = 4) -> BasePdfExtractor:
        extractor_cls = _EXTRACTORS.get(extractor_name)
        if extractor_cls is None:
            logger.warning("[PROCESSOR][PDF] Unknown extractor '%s', falling back to 'pymupdf'", extractor_name)
            extractor_cls = PyMuPdfExtractor
        if extractor_cls is DoclingPdfExtractor:
            return DoclingPdfExtractor(num_threads=docling_num_threads)
        return extractor_cls()

    def _extract_md(self, file_path: Path, work_dir: str):
        """Orchestrate full extraction: configured extractor → optional OCR / VLM per image → final Markdown.

        `work_dir` must be exclusive to this call — the processor instance is a shared
        singleton (see application_context.get_input_processor_instance), and concurrent
        Temporal activities call this method in parallel. A shared work directory would
        let one activity's cleanup delete another's in-flight images (FileNotFoundError).
        """
        use_ocr = False
        use_image_describer = False

        processing = get_configuration().processing
        current_profile = get_current_processing_profile()
        active_profile = processing.normalize_profile(current_profile)
        profile_cfg = processing.get_profile_config(active_profile)

        if profile_cfg.process_images and get_configuration().vision_model:
            image_describer = build_image_describer(get_configuration().vision_model)
            use_image_describer = True
        if profile_cfg.pdf.do_ocr:
            use_ocr = True

        extractor_name = profile_cfg.pdf.extractor
        logger.info(
            "[PROCESSOR][PDF] extractor=%s | use_ocr=%s | use_image_describer=%s",
            extractor_name,
            use_ocr,
            use_image_describer,
        )

        extractor = self._build_extractor(extractor_name, profile_cfg.pdf.docling_num_threads)
        try:
            md_text, images_transcription = extractor.extract(file_path, work_dir)
        except Exception as e:
            raise RuntimeError(f"PDF extraction failed with extractor '{extractor_name}'") from e

        if images_transcription and use_ocr:
            ocr_model = PaddleOCRmodel()
            ocr_results = self._use_ocr(ocr_model, images_transcription)
            for image_transcription, ocr_result in zip(images_transcription, ocr_results):
                if use_image_describer:
                    image_transcription.transcription = self._use_image_describer(image_describer, image_transcription, ocr_result)
                else:
                    image_transcription.transcription = " ".join(ocr_result["rec_texts"])

        for image_transcription in images_transcription:
            md_text = re.sub(r"!\[.*?\]\(" + re.escape(str(image_transcription.image_path)) + r"\)", image_transcription.transcription, md_text)
        return md_text

    # ---- public API ----------------------------------------------------------

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
        output_markdown_path = output_dir / "output.md"

        # Primary extraction: configured extractor
        work_dir = tempfile.mkdtemp(dir=self.BASE_FOLDER)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            md_content = self._extract_md(file_path, work_dir)
            logger.info("[PROCESSOR][PDF] Extraction succeeded | file=%s", file_path.name)

            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            return {
                "doc_dir": str(output_dir),
                "md_file": str(output_markdown_path),
                "message": "Conversion to markdown succeeded.",
            }
        except Exception as e:
            logger.warning(f"PDF extraction failed, trying markitdown: {e}", exc_info=True)
        finally:
            self._remove_all_files(work_dir)

        # Fallback extraction: Markitdown
        try:
            md_content = self._extract_with_markitdown(file_path)
            logger.info("[PROCESSOR][PDF] Markitdown extraction | file=%s", file_path.name)

            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            return {
                "doc_dir": str(output_dir),
                "md_file": str(output_markdown_path),
                "message": "Conversion to markdown succeeded.",
            }
        except Exception as e:
            logger.warning(f"Markitdown PDF extraction failed: {e}")
            raise e
