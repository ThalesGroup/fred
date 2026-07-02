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

"""Ingestion processor for legacy binary ``.doc`` Word files.

Fred rationale:
- ``.doc`` (legacy OLE binary) is not readable by pandoc/python-docx, so instead
  of duplicating extraction logic we convert ``.doc`` -> ``.docx`` once with
  headless LibreOffice and then delegate to the existing, well-tested
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

from knowledge_flow_backend.core.processors.input.common.legacy_office import convert_doc_to_docx, looks_like_ole_binary
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import DocxMarkdownProcessor

logger = logging.getLogger(__name__)


class DocMarkdownProcessor(DocxMarkdownProcessor):
    description = "Converts legacy binary DOC files to Markdown by upgrading them to DOCX (LibreOffice) and reusing the DOCX extractor."

    def check_file_validity(self, file_path: Path) -> bool:
        """Validate that the input is a non-empty legacy OLE ``.doc`` file.

        Cheap structural check only: we do not spawn LibreOffice here, conversion
        happens lazily in the extraction methods below.
        """
        try:
            if file_path.stat().st_size <= 0:
                logger.warning("[DOC] %s is empty.", file_path)
                return False
        except OSError as exc:
            logger.error("[DOC] Cannot stat %s: %s", file_path, exc)
            return False

        if not looks_like_ole_binary(file_path):
            logger.error("[DOC] %s is not a valid legacy OLE .doc file.", file_path)
            return False
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        with tempfile.TemporaryDirectory(prefix="doc2docx_") as tmp:
            docx_path = convert_doc_to_docx(file_path, Path(tmp))
            return super().extract_file_metadata(docx_path)

    def extract_guardrail_text(self, file_path: Path) -> str | None:
        with tempfile.TemporaryDirectory(prefix="doc2docx_") as tmp:
            docx_path = convert_doc_to_docx(file_path, Path(tmp))
            return super().extract_guardrail_text(docx_path)

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        with tempfile.TemporaryDirectory(prefix="doc2docx_") as tmp:
            docx_path = convert_doc_to_docx(file_path, Path(tmp))
            return super().convert_file_to_markdown(docx_path, output_dir, document_uid)
