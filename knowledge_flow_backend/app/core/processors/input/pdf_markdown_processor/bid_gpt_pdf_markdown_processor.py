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
from pathlib import Path

import pypdf
from pypdf.errors import PdfReadError

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor

logger = logging.getLogger(__name__)

class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    PDF processor using BaseMarkdownProcessor (and BaseInputProcessor).
    Provides: file validation, metadata extraction and Markdown conversion.
    """

    def __init__(self):
        super().__init__()

    def check_file_validity(self, file_path: Path) -> bool:
        """
        Check if the PDF is readable and contains at least one page.

        Args:
            file_path: Path to the PDF file.

        Returns:
            True if the file is a valid, non-empty PDF, otherwise False.
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
        Extract metadata from the PDF as a flat dictionary.

        Keys can include: title, author, page_count, extras.

        Args:
            file_path: Path to the PDF file.

        Returns:
            A dictionary containing discovered metadata, or an error field if extraction fails.
        """
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
            logger.error(f"Error extracting metadata from PDF: {e}")
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(
        self,
        file_path: Path,
        output_dir: Path,
        document_uid: str | None
    ) -> dict:
        """
        Convert the PDF to a simple Markdown file using pypdf text extraction.

        Each page’s text is written as a section in the markdown file.

        Args:
            file_path: Path to the PDF file.
            output_dir: Directory where the Markdown file will be saved.
            document_uid: Optional unique document identifier.

        Returns:
            A dictionary containing:
            - doc_dir: path to the output directory
            - md_file: path to the generated Markdown file (or None on failure)
            - status: "success" or "error"
            - message: status message or error details
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        try:
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))
            with md_path.open("w", encoding="utf-8") as md:
                for i, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    md.write(f"# Page {i}\n\n{text}\n\n")

        except Exception as e:
            logger.error(f"Failed to convert PDF to Markdown: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": None,
                "status": "error",
                "message": str(e),
            }

        return {
            "doc_dir": str(output_dir),
            "md_file": str(md_path),
            "status": "success",
            "message": "PDF to Markdown conversion completed using pypdf.",
        }
