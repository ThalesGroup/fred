import logging
import re
from pathlib import Path
from typing import Optional

from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.document_loaders.parsers import PyPDFParser, TesseractBlobParser
from langchain_core.documents.base import Blob

from app.application_context import get_configuration
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor as DoclingProcessor

logger = logging.getLogger(__name__)

class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    PDF→Markdown processor using PyPDFParser + TesseractBlobParser.

    • Extracts text (including OCR on images) in a single pass.
    • Detects hierarchical headings (#, ##, ###) via MarkdownHeaderTextSplitter.
    • Heuristically detects tables.
    """

    def __init__(self):
        super().__init__()
        cfg = get_configuration()
        self._docling_fallback: Optional[DoclingProcessor] = None

    # ------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------ #

    def blob_from_file(self, file_path: Path) -> Blob:
        """
        Create a Blob from a PDF file. Compatible with PyPDFParser.
        """
        return Blob.from_path(str(file_path))

    def _guess_tables(self, text: str) -> list[str]:
        """
        Heuristically detect tables based on whitespace or tabs in lines.
        """
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
        """
        Check if the PDF can be parsed without errors.
        """
        try:
            parser = PyPDFParser(mode="single", pages_delimiter="\n\f")
            blob = self.blob_from_file(file_path)
            _ = parser.parse(blob)
            return True
        except Exception as e:
            logger.error(f"PDF validation failed for {file_path}: {e}")
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Extract basic metadata from the PDF.
        """
        try:
            parser = PyPDFParser(mode="single", pages_delimiter="\n\f")
            blob = self.blob_from_file(file_path)
            docs = parser.parse(blob)
            page_count = len(docs)
            text_found = any((d.page_content or "").strip() for d in docs)
            return {
                "title": None,
                "author": None,
                "document_name": file_path.name,
                "page_count": page_count,
                "extras": {
                    "is_image_only": not text_found,
                },
            }
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(
        self,
        file_path: Path,
        output_dir: Path,
        document_uid: str | None
    ) -> dict:
        """
        Convert PDF to structured Markdown (headings, tables, OCR images)
        using a MarkdownHeaderTextSplitter for consistent heading hierarchy.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        try:
            parser = PyPDFParser(
                mode="single",
                pages_delimiter="\n\f",
                images_parser=TesseractBlobParser(),
            )
            blob = self.blob_from_file(file_path)
            docs = parser.parse(blob)

            full_text = ""
            images_metadata = []

            # Collect all text and OCR image metadata
            for doc in docs:
                text = doc.page_content or ""
                if text.strip():
                    full_text += text + "\n\n"
                for img_blob in doc.metadata.get("images", []):
                    images_metadata.append((doc.metadata.get("page", "?"), img_blob))

            # Split text by headings using MarkdownHeaderTextSplitter
            splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[("#", "H1"), ("##", "H2"), ("###", "H3")]
            )
            chunks = splitter.split_text(full_text)

            md_lines: list[str] = []
            for chunk in chunks:
                md_lines.append(chunk.page_content or "")
                md_lines.append("\n")

            # Detect tables heuristically across the whole text
            tables = self._guess_tables(full_text)
            for idx, tbl in enumerate(tables):
                md_lines.append(f"<!-- TABLE_START:id={idx} -->\n{tbl}\n<!-- TABLE_END -->\n\n")

            # Append OCR images
            for page_index, img_blob in images_metadata:
                img_path = img_blob.get("path")
                ocr_txt = img_blob.get("ocr_text", "")
                if img_path:
                    md_lines.append(f"![Page {page_index}]({img_path})\n\n")
                if ocr_txt:
                    md_lines.append(f"<!-- OCR_TEXT_START -->\n{ocr_txt}\n<!-- OCR_TEXT_END -->\n\n")

            md_path.write_text("\n".join(md_lines), encoding="utf-8")

            return {
                "doc_dir": str(output_dir),
                "md_file": str(md_path),
                "status": "success",
                "message": "PDF converted to Markdown with structured headings, tables, and OCR images via PyPDFParser + MarkdownHeaderTextSplitter.",
            }

        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": None,
                "status": "error",
                "message": str(e),
            }
