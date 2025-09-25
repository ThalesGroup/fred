import logging
import re
from pathlib import Path
from typing import Optional

import pypdf
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, DictionaryObject

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor as DoclingProcessor,
)

logger = logging.getLogger(__name__)

class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    Fast PDF→Markdown processor.

    • First attempts a quick extraction using pypdf.
    • If no text is detected (pure image scan),
      it automatically falls back to PdfMarkdownProcessor (Docling + torch)
      to perform OCR and include images/tables.
    """

    def __init__(self):
        super().__init__()
        self._docling_fallback: Optional[DoclingProcessor] = None

    # ------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------ #

    def _extract_inline_images(self, page) -> list[str]:
        """Return a list of image names embedded in a page."""
        images = []
        try:
            xobjects = page["/Resources"].get("/XObject")
            if isinstance(xobjects, DictionaryObject):
                for name, obj in xobjects.items():
                    if isinstance(obj.get_object(), DictionaryObject):
                        subtype = obj.get_object().get("/Subtype")
                        if subtype == NameObject("/Image"):
                            images.append(str(name))
        except Exception:
            pass
        return images

    def _guess_tables(self, text: str) -> list[str]:
        """
        Naively detect table-like blocks by looking for lines
        with multiple consecutive spaces or tabs.
        """
        tables = []
        lines = text.splitlines()
        block = []
        for line in lines:
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
        """
        Verify that the file is a valid, non-empty PDF.
        """
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
        """
        Extract metadata and detect if the PDF contains extractable text.
        """
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                info = reader.metadata or {}

                # Detect presence of text
                text_found = any(
                    (page.extract_text() or "").strip()
                    for page in reader.pages
                )

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
        Convert the PDF to Markdown using pypdf when possible.
        If no extractable text is found, fall back to the Docling OCR processor.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        # First pass: quick text extraction
        try:
            reader = pypdf.PdfReader(str(file_path))

            any_text = False
            with md_path.open("w", encoding="utf-8") as md:
                for i, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        any_text = True
                    images = self._extract_inline_images(page)
                    tables = self._guess_tables(text)

                    md.write(f"# Page {i}\n\n")

                    # Annotate detected tables
                    for idx, tbl in enumerate(tables):
                        md.write(
                            f"<!-- TABLE_START:id={i}-{idx} -->\n{tbl}\n<!-- TABLE_END -->\n\n"
                        )

                    md.write(text + "\n\n")

                    for img in images:
                        md.write(f"![Embedded image: {img}]\n\n")

            if any_text:
                return {
                    "doc_dir": str(output_dir),
                    "md_file": str(md_path),
                    "status": "success",
                    "message": "PDF to Markdown conversion completed using pypdf.",
                }

            # ------------------------------------------------------------------
            # Fallback to Docling if no text
            # ------------------------------------------------------------------
            logger.info("No extractable text detected. Falling back to Docling OCR processor...")
            if self._docling_fallback is None:
                self._docling_fallback = DoclingProcessor()
            return self._docling_fallback.convert_file_to_markdown(
                file_path, output_dir, document_uid
            )

        except Exception as e:
            logger.error(f"Fast conversion failed: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": None,
                "status": "error",
                "message": str(e),
            }
