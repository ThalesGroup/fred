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
from pathlib import Path

import camelot
import pypdf
from pypdf.errors import PdfReadError

from app.application_context import get_configuration
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from app.core.processors.input.common.image_describer import build_image_describer

logger = logging.getLogger(__name__)


class PdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    PDF → Markdown processor using:
      • pypdf for text and metadata extraction
      • camelot-py for table detection and export to Markdown
    """

    def __init__(self):
        super().__init__()
        self.image_describer = None
        self.process_images = get_configuration().processing.process_images
        if self.process_images:
            if not get_configuration().vision:
                raise ValueError(
                    "Vision model configuration is missing but process_images is enabled."
                )
            self.image_describer = build_image_describer(get_configuration().vision)

    # --------------------------------------------------------------------- #
    # Validation & metadata
    # --------------------------------------------------------------------- #

    def check_file_validity(self, file_path: Path) -> bool:
        """Check if the PDF is readable and contains at least one page."""
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
        """Extract standard metadata from the PDF without reading all text."""
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

    # --------------------------------------------------------------------- #
    # Conversion to Markdown
    # --------------------------------------------------------------------- #

    def convert_file_to_markdown(
        self, file_path: Path, output_dir: Path, document_uid: str | None
    ) -> dict:
        """
        Convert the PDF to a Markdown file.
        * Extract all page text with pypdf
        * Extract tables with camelot-py and insert as Markdown
        * Optionally describe images if process_images is enabled
        """
        output_markdown_path = output_dir / "output.md"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # --- Extract plain text from all pages
            logger.info("Reading PDF text with pypdf...")
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                all_text = []
                for i, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    all_text.append(f"\n\n<!-- PAGE {i} START -->\n{text}\n<!-- PAGE {i} END -->")
            md_content = "\n".join(all_text)

            # --- Extract tables with Camelot
            logger.info("Extracting tables with Camelot...")
            # 'stream' works better for tables without clear cell borders
            tables = camelot.read_pdf(str(file_path), flavor="lattice", pages="all")
            # If lattice finds nothing, optionally fallback to stream
            if len(tables) == 0:
                tables = camelot.read_pdf(str(file_path), flavor="stream", pages="all")

            for i, table in enumerate(tables):
                # Convert table to GitHub-flavored Markdown
                table_md = table.df.to_markdown(index=False)
                annotated = f"<!-- TABLE_START:id={i} -->\n{table_md}\n<!-- TABLE_END -->"
                # Append at end of file (you could also attempt to place at page location)
                md_content += "\n\n" + annotated

            # --- Image description placeholders (if any)
            if self.process_images:
                # No direct image extraction with pypdf; you'd integrate pdf2image or similar.
                # Placeholder kept for compatibility.
                logger.info("process_images enabled, but direct image extraction "
                            "is not implemented in this version.")
                # If you later add image extraction, call self.image_describer.describe(base64)

            # --- Write final Markdown
            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            return {
                "doc_dir": str(output_dir),
                "md_file": str(output_markdown_path),
                "status": "success",
                "message": "PDF converted to Markdown with pypdf text and camelot tables.",
            }

        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return {
                "doc_dir": str(output_dir),
                "md_file": None,
                "status": "error",
                "message": str(e),
            }
