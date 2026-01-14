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

import logging
from pathlib import Path

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_csv_to_md_processor import LiteCsvToMdProcesor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import LiteDocxToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pptx_to_md_processor import LitePptxToMdExtractor

logger = logging.getLogger(__name__)


class LiteMdError(Exception):
    """Erreur métier pour l'extraction Markdown légère."""


class LiteTypeNotSupportedError(LiteMdError):
    pass


class LiteExtractionFailed(LiteMdError):
    pass


class LiteMdProcessingService:
    """Facade to select the right lightweight extractor based on file suffix.

    Raises dedicated business exceptions for clearer error handling at controller level.
    """

    def __init__(self) -> None:
        self._pdf = LitePdfToMdProcessor()
        self._docx = LiteDocxToMdProcessor()
        self._csv = LiteCsvToMdProcesor()
        self._pptx = LitePptxToMdExtractor()

    @staticmethod
    def _trim_empty_lines(text: str) -> str:
        if not text:
            return text
        lines = text.split("\n")
        start = 0
        end = len(lines) - 1
        while start <= end and not lines[start].strip():
            start += 1
        while end >= start and not lines[end].strip():
            end -= 1
        if start > end:
            return ""
        return "\n".join(lines[start : end + 1])

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        ext = (file_path.suffix or "").lower()
        opts = options or LiteMarkdownOptions()
        try:
            if ext == ".pdf":
                return self._pdf.extract(file_path, opts)
            if ext == ".docx":
                return self._docx.extract(file_path, opts)
            if ext == ".csv":
                return self._csv.extract(file_path, opts)
            if ext == ".pptx":
                return self._pptx.extract(file_path, opts)
            if ext == ".md":
                # No extraction needed
                content = file_path.read_text(encoding="utf-8")
                if opts.normalize_whitespace:
                    content = collapse_whitespace(content)
                if opts.trim_empty_lines:
                    content = self._trim_empty_lines(content)
                content, truncated = enforce_max_chars(content, opts.max_chars)
                pages = [LitePageMarkdown(page_no=1, markdown=content, char_count=len(content))] if opts.return_per_page else []
                return LiteMarkdownResult(
                    document_name=file_path.name,
                    page_count=1,
                    total_chars=len(content),
                    truncated=truncated,
                    markdown=content,
                    pages=pages,
                )
        except Exception as e:
            logger.warning(f"Lightweight extraction failed for {file_path.name}: {e}")
            raise LiteExtractionFailed(f"Failed to extract lightweight Markdown from '{file_path.name}': {e}")

        raise LiteTypeNotSupportedError(f"Unsupported file type for lightweight extraction: '{ext}' (only .pdf, .docx, .csv, .pptx, .md are supported)")
