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
import re
from pathlib import Path
from typing import List

from markitdown import MarkItDown

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
    normalize_repeated_chars,
    strip_surrogates,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfMarkdownProcessor as DefaultPdfMarkdownProcessor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.optional_pymupdf import require_pymupdf

logger = logging.getLogger(__name__)


class LitePdfToMdExtractor(BaseLiteMdProcessor):
    """
    Lightweight PDF → Markdown.

    Fred rationale:
    - Use `pymupdf4llm` as the primary extractor: fast, reliable, and page‑oriented.
    - Fall back to `markitdown` only when PyMuPDF4LLM extraction fails.
    - Preserve Fred's page-oriented UX when needed via PyMuPDF4LLM page scans.
    - Keep token budgets predictable via normalization + max_chars cap.
    """

    description = "Fast PDF-to-Markdown converter optimized for lightweight, page-aware extraction."

    def __init__(self) -> None:
        self._md = MarkItDown() if MarkItDown else None

    def _normalize_whitespace(self, text: str, opts: LiteMarkdownOptions) -> str:
        return collapse_whitespace(text) if opts.normalize_whitespace else text

    def _normalize_repeated_chars(self, text: str, opts: LiteMarkdownOptions) -> str:
        return normalize_repeated_chars(text) if opts.normalize_repeated_chars else text

    def _remove_additional_tags(self, text: str, opts: LiteMarkdownOptions) -> str:
        return re.sub(r"\*\*==> picture .* intentionally omitted <==\*\*\n?", "", text)

    def _extract_with_markitdown(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        if not self._md:
            raise RuntimeError("markitdown not available for PDF conversion")

        converted = self._md.convert(str(file_path))
        # Pylance sometimes flags `.text`; guard with getattr for static peace of mind.
        md = converted.markdown
        md = strip_surrogates(md)
        md = self._normalize_whitespace(md, opts)

        md, truncated = enforce_max_chars(md, opts.max_chars)

        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=None,  # markitdown abstracts away page structure
            total_chars=len(md),
            truncated=truncated,
            markdown=md,
            pages=[],  # no per-page in this path
            extras={"engine": "markitdown"},
        )

    def _extract_pymupdf4llm(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        """
        Extract Markdown using pymupdf4llm (primary engine).
        - Page‑wise extraction
        - Normalization + cleaning
        - max_chars truncation support
        """
        count_char: int = 0
        truncated: bool = False

        # Extract raw pages from pymupdf4llm. Open the fitz.Document ourselves
        # (instead of letting pymupdf4llm open it from the path) so we can guarantee
        # it's closed: pymupdf4llm.to_markdown() never closes a document it opens
        # internally, which leaks native MuPDF memory (pages, xref table) per file.
        fitz, pymupdf4llm = require_pymupdf(type(self).__name__)
        doc = fitz.open(file_path)
        try:
            pages = pymupdf4llm.to_markdown(doc, ignore_images=True, ignore_graphics=True, header=False, footer=False, page_chunks=True)
        finally:
            doc.close()

        # Normalize each page
        pages_md: List[LitePageMarkdown] = []
        for p in pages:
            if isinstance(p, dict):
                text = (p.get("text") or p.get("md") or "").strip()
                page_no = p.get("metadata", {}).get("page_number", -1)
            elif isinstance(p, str):
                text = p.strip()
                page_no = -1
            else:
                text = ""
                page_no = -1

            # Apply your normalization pipeline. strip_surrogates runs first and is not
            # opt-gated: unpaired surrogates from a malformed ToUnicode CMap are not a
            # style choice, they make the page impossible to encode as UTF-8 downstream.
            md_text = strip_surrogates(text)
            md_text = self._normalize_repeated_chars(md_text, opts)
            md_text = self._remove_additional_tags(md_text, opts)
            md_text = self._normalize_whitespace(md_text, opts)

            if opts.max_chars and count_char + len(md_text) > opts.max_chars:
                truncated = True
                continue

            count_char += len(md_text) + 1

            pages_md.append(LitePageMarkdown(page_no=page_no, markdown=md_text, char_count=len(md_text) + 1))

        md_text = "\n".join(p.markdown for p in pages_md)

        # Build final result in Markdown
        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=len(pages),
            total_chars=count_char - 1,
            truncated=truncated,
            markdown=md_text,
            pages=pages_md,
            extras={"engine": "pymupdf4llm"},
        )

    # ---- public API ----------------------------------------------------------

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        """
        Strategy:
        - If caller: use PyMuPDF4llm (best quality, deterministic).
        - Else prefer markitdown (fast/maintenance for whole-doc).
        - On failures, log and fall back to the other path when possible.
        """
        opts = options or LiteMarkdownOptions()

        require_pymupdf(type(self).__name__)

        # Primary extraction: PyMuPDF4LLM
        try:
            result: LiteMarkdownResult = self._extract_pymupdf4llm(file_path, opts)
            logger.info(
                "[LITE_PDF][IMPLEM] Pymupdf4llm page-wise extraction | file=%s pages=%s chars=%s truncated=%s",
                file_path.name,
                result.page_count,
                result.total_chars,
                result.truncated,
            )
            return result
        except ImportError:
            raise
        except Exception as e:
            if opts.page_range or opts.return_per_page or opts.add_page_headings:
                raise
            logger.warning(f"Pymupdf4llm PDF extraction failed, trying markitdown: {e}")

        # Fallback extraction: Markitdown
        try:
            result = self._extract_with_markitdown(file_path, opts)
            logger.info(
                "[LITE_PDF][IMPLEM] Markitdown extraction | file=%s pages=%s chars=%s truncated=%s",
                file_path.name,
                result.page_count,
                result.total_chars,
                result.truncated,
            )
            return result
        except Exception as e:
            logger.warning(f"Markitdown PDF extraction failed: {e}")
            raise e


class LitePdfMarkdownProcessor(DefaultPdfMarkdownProcessor):
    """Explicit PyMuPDF ingestion adapter, sharing validation and metadata with pypdf."""

    def __init__(self) -> None:
        super().__init__()
        self._lite = LitePdfToMdExtractor()
