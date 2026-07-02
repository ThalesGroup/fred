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

"""Ingestion processor for OpenDocument ``.odt`` text files.

Fred rationale:
- ``.odt`` (OpenDocument Text) is an ODF ZIP package, not OOXML, so instead of
  duplicating extraction logic we convert ``.odt`` -> ``.docx`` once with headless
  LibreOffice and then delegate to the existing, well-tested
  ``DocxMarkdownProcessor``.
- The processor is intentionally stateless: each public method converts into its
  own temporary directory and delegates. This keeps it safe under the concurrent
  ingestion workers that share a single processor instance, at the cost of a few
  extra LibreOffice runs per document (acceptable for corpus ingestion, which is
  not latency sensitive).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from knowledge_flow_backend.core.processors.input.common.legacy_office import ODT_MIMETYPE, convert_odt_to_docx, looks_like_odf
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import DocxMarkdownProcessor

logger = logging.getLogger(__name__)


class OdtMarkdownProcessor(DocxMarkdownProcessor):
    description = "Converts OpenDocument ODT files to Markdown by upgrading them to DOCX (LibreOffice) and reusing the DOCX extractor."

    def check_file_validity(self, file_path: Path) -> bool:
        """Validate that the input is a non-empty OpenDocument ``.odt`` package.

        Cheap structural check only: we do not spawn LibreOffice here, conversion
        happens lazily in the extraction methods below.
        """
        try:
            if file_path.stat().st_size <= 0:
                logger.warning("[ODT] %s is empty.", file_path)
                return False
        except OSError as exc:
            logger.error("[ODT] Cannot stat %s: %s", file_path, exc)
            return False

        if not looks_like_odf(file_path, ODT_MIMETYPE):
            logger.error("[ODT] %s is not a valid OpenDocument .odt package.", file_path)
            return False
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        with tempfile.TemporaryDirectory(prefix="odt2docx_") as tmp:
            docx_path = convert_odt_to_docx(file_path, Path(tmp))
            return super().extract_file_metadata(docx_path)

    def extract_guardrail_text(self, file_path: Path) -> str | None:
        with tempfile.TemporaryDirectory(prefix="odt2docx_") as tmp:
            docx_path = convert_odt_to_docx(file_path, Path(tmp))
            return super().extract_guardrail_text(docx_path)

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        with tempfile.TemporaryDirectory(prefix="odt2docx_") as tmp:
            docx_path = convert_odt_to_docx(file_path, Path(tmp))
            return super().convert_file_to_markdown(docx_path, output_dir, document_uid)
