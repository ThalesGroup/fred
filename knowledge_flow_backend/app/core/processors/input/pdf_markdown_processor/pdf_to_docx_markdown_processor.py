# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import subprocess
from pathlib import Path

import pypdf
from docx import Document
from pypdf.errors import PdfReadError

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from app.core.processors.input.docx_markdown_processor.docx_markdown_processor import DocxMarkdownProcessor
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor as PdfDoclingFallback

logger = logging.getLogger(__name__)

from docx import Document


def _normalize_docx_for_pandoc(docx_path: Path) -> Path:
    """
    Open the DOCX using python-docx and re-save it to ensure Pandoc compatibility.
    Returns the path of the normalized DOCX.
    """
    doc = Document(str(docx_path))
    normalized_path = docx_path.with_name(docx_path.stem + "_normalized.docx")
    doc.save(str(normalized_path))
    return normalized_path

class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    Main processor with layered fallbacks:
        1. Validate PDF and check for extractable text.
        2. If text present -> LibreOffice headless PDF->DOCX -> DocxMarkdownProcessor.
        3. If no text -> fallback to the Docling-based PdfMarkdownProcessor (OCR/docling).
    """

    def __init__(self):
        super().__init__()
        self.docx_processor = DocxMarkdownProcessor()
        self.fallback_processor = PdfDoclingFallback()

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _pdf_has_text(self, file_path: Path) -> bool:
        """Return True if at least one page contains actual text."""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt and txt.strip():
                        return True
        except PdfReadError as e:
            logger.error(f"PDF read error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while checking text: {e}")
        return False

    def _convert_pdf_to_docx(self, pdf_path: Path, out_dir: Path) -> Path:
        """
        Convert PDF to DOCX using LibreOffice headless.
        Returns the path of the generated DOCX file.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to", "docx:writer8",
            "--outdir", str(out_dir),
            str(pdf_path),
        ]
        logger.info("Running LibreOffice headless for PDF->DOCX...")
        subprocess.run(cmd, check=True)
        docx_path = out_dir / (pdf_path.stem + ".docx")
        if not docx_path.exists():
            raise FileNotFoundError(f"LibreOffice did not create {docx_path}")
        return docx_path

    # ------------------------------------------------------------
    # BaseMarkdownProcessor API
    # ------------------------------------------------------------

    def check_file_validity(self, file_path: Path) -> bool:
        """Quick sanity check: file is a readable PDF with at least one page."""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                return len(reader.pages) > 0
        except PdfReadError as e:
            logger.error(f"Corrupted PDF {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error validating {file_path}: {e}")
        return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """Pass-through metadata extraction using pypdf."""
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
            logger.error(f"Error extracting metadata: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(
        self, file_path: Path, output_dir: Path, document_uid: str | None
    ) -> dict:
        """
        Main PDF -> Markdown processor with fallback layers.
        The Markdown output is always at output_dir / "output.md".
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        try:
            if self._pdf_has_text(file_path):
                logger.info("PDF contains text; using LibreOffice + DocxMarkdownProcessor.")
                # Convert PDF to DOCX
                docx_path = _normalize_docx_for_pandoc(self._convert_pdf_to_docx(file_path, output_dir))
                # Convert DOCX to Markdown using existing processor
                result = self.docx_processor.convert_file_to_markdown(
                    docx_path, output_dir, document_uid
                )
                # Override the Markdown path to output.md
                if "md_file" in result and result["md_file"]:
                    result["md_file"] = str(md_path)
                return result

            else:
                logger.info("No extractable text; falling back to Docling/OCR pipeline.")
                result = self.fallback_processor.convert_file_to_markdown(
                    file_path, output_dir, document_uid
                )
                # Make sure output path is unified
                if "md_file" in result and result["md_file"]:
                    result["md_file"] = str(md_path)
                return result

        except Exception as e:
            logger.error(f"Full PDF conversion failed: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": str(md_path),
                "status": "error",
                "message": str(e),
            }
