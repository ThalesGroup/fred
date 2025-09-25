import logging
import re
import base64
from pathlib import Path
from typing import Optional

import pypdf
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, DictionaryObject

from app.application_context import get_configuration
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from app.core.processors.input.common.image_describer import build_image_describer
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor as DoclingProcessor

logger = logging.getLogger(__name__)

class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    Fast PDF→Markdown processor.

    • Tries quick extraction using pypdf.
    • Falls back to Docling OCR if no text is detected (image-only PDF).
    • Inline images are described and inserted as %%ANNOTATION%% blocks.
    """

    def __init__(self):
        super().__init__()
        cfg = get_configuration()
        self.process_images = cfg.processing.process_images
        self.image_describer = build_image_describer(cfg.vision) if self.process_images and cfg.vision else None
        self._docling_fallback: Optional[DoclingProcessor] = None

    # ------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------ #

    def _extract_inline_images(self, page) -> list[bytes]:
        images: list[bytes] = []
        try:
            xobjects = page["/Resources"].get("/XObject")
            if isinstance(xobjects, DictionaryObject):
                for name, obj in xobjects.items():
                    xobj = obj.get_object()
                    if isinstance(xobj, DictionaryObject) and xobj.get("/Subtype") == NameObject("/Image"):
                        data = xobj.get_data()
                        if data:
                            images.append(data)
        except Exception as e:
            logger.warning(f"Image extraction failed on page: {e}")
        return images

    def _guess_tables(self, text: str) -> list[str]:
        tables, block = [], []
        for line in text.splitlines():
            if re.search(r"\s{2,}", line) or "\t" in line:
                block.append(line)
            else:
                if len(block) >= 2:
                    tables.append("\n".join(block))
                block = []
        if len(block) >= 2:
            tables.append("\n".join(block))
        return tables

    # ------------------------------------------------------------ #
    # BaseInputProcessor required methods
    # ------------------------------------------------------------ #

    def check_file_validity(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                if len(reader.pages) == 0:
                    logger.warning(f"The PDF file {file_path} is empty.")
                    return False
                return True
        except PdfReadError as e:
            logger.error(f"Corrupted PDF file: {file_path} - {e}")
        except Exception as e:
            logger.error(f"Unexpected error while validating {file_path}: {e}")
        return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                info = reader.metadata or {}
                text_found = any((page.extract_text() or "").strip() for page in reader.pages)

                return {
                    "title": info.get("/Title") or None,
                    "author": info.get("/Author") or None,
                    "document_name": file_path.name,
                    "page_count": len(reader.pages),
                    "extras": {
                        "pdf.subject": info.get("/Subject") or None,
                        "pdf.producer": info.get("/Producer") or None,
                        "pdf.creator": info.get("/Creator") or None,
                        "is_image_only": not text_found,
                    },
                }
        except Exception as e:
            logger.error(f"Error extracting metadata from PDF: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(
        self,
        file_path: Path,
        output_dir: Path,
        document_uid: str | None
    ) -> dict:
        """
        Convert to Markdown using pypdf and fallback to Docling OCR.
        Preserves page breaks, tables, and inline %%ANNOTATION%% for images.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        try:
            reader = pypdf.PdfReader(str(file_path))
            any_text = False
            annotations: list[str] = []

            with md_path.open("w", encoding="utf-8") as md:
                for i, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        any_text = True

                    tables = self._guess_tables(text)
                    images = self._extract_inline_images(page)

                    # Write page header
                    md.write(f"{text.strip()}\n\n")  # Preserve original line breaks
                    for tbl_idx, tbl in enumerate(tables):
                        md.write(f"<!-- TABLE_START:id={i}-{tbl_idx} -->\n{tbl}\n<!-- TABLE_END -->\n\n")

                    for raw_img in images:
                        desc = "Image description not available."
                        if self.image_describer:
                            try:
                                b64 = base64.b64encode(raw_img).decode("ascii")
                                desc = self.image_describer.describe(b64)
                            except Exception as e:
                                logger.warning(f"Image description failed: {e}")
                        annotations.append(desc)
                        md.write("%%ANNOTATION%%\n\n")  # preserve placeholder

            # Fallback to Docling OCR if no text found
            if not any_text:
                logger.info("No extractable text detected. Falling back to Docling OCR processor...")
                if self._docling_fallback is None:
                    self._docling_fallback = DoclingProcessor()
                return self._docling_fallback.convert_file_to_markdown(file_path, output_dir, document_uid)

            # Replace %%ANNOTATION%% with descriptions
            if annotations:
                content = md_path.read_text(encoding="utf-8")
                for desc in annotations:
                    content = content.replace("%%ANNOTATION%%", desc, 1)
                md_path.write_text(content, encoding="utf-8")

            return {
                "doc_dir": str(output_dir),
                "md_file": str(md_path),
                "status": "success",
                "message": "PDF to Markdown conversion completed with page-wise layout and image annotations.",
            }

        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": None,
                "status": "error",
                "message": str(e),
            }
