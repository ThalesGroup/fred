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
from typing import List, Tuple

from markitdown import MarkItDown
from pypdf import PdfReader

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
    strip_surrogates,
)

# Core idea:
# - Prefer MarkItDown for whole-PDF conversion (good quality, less code).
# - If callers ask for page-level control (page_range, per-page output, page headings),
#   switch to a page-wise path using pypdf.
# - Keep page-aware failures explicit rather than discard page structure.

logger = logging.getLogger(__name__)


# Optional imports guarded for runtime + Pylance friendliness


class LitePdfToMdProcessor(BaseLiteMdProcessor):
    """
    Lightweight PDF → Markdown.

    Fred rationale:
    - Use `markitdown` for "good-enough" Markdown with minimal maintenance.
    - Preserve Fred's page-oriented UX when needed via pypdf page scans.
    - Keep token budgets predictable via normalization + max_chars cap.
    """

    description = "Fast PDF-to-Markdown converter optimized for lightweight, page-aware extraction."

    def __init__(self) -> None:
        self._md = MarkItDown() if MarkItDown else None

    # ---- helpers -------------------------------------------------------------

    def _needs_page_wise(self, opts: LiteMarkdownOptions) -> bool:
        """Return True if caller requested page-range or page-structured output."""
        return bool(opts.page_range or opts.return_per_page or opts.add_page_headings)

    def _normalize(self, s: str, opts: LiteMarkdownOptions) -> str:
        s = strip_surrogates(s)
        return collapse_whitespace(s) if opts.normalize_whitespace else s

    def _safe_page_range(self, page_count: int, page_range: Tuple[int, int] | None) -> Tuple[int, int]:
        """
        Ensures a valid, 1-based inclusive page range within the PDF's total page count.

        Fred rationale:
        - Keeps downstream iteration deterministic.
        - Clamps values silently so agents never raise IndexError on out-of-bounds pages.
        """
        if not page_range:
            return (1, page_count)

        start_p, end_p = page_range
        start_p = max(1, min(start_p, page_count))
        end_p = max(start_p, min(end_p, page_count))  # ensures end ≥ start

        return (start_p, end_p)

    # ---- page-wise extraction (pypdf) -------------------------------------

    def _extract_pages_with_pypdf(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        with file_path.open("rb") as stream:
            doc = PdfReader(stream)
            page_count = len(doc.pages)

            start_p, end_p = self._safe_page_range(page_count, opts.page_range)
            pages_md: List[LitePageMarkdown] = []

            for pno in range(start_p, end_p + 1):
                page = doc.pages[pno - 1]
                # Plain text is enough for the lightweight path; keeps speed & determinism.
                raw_text = page.extract_text() or ""
                text: str = raw_text if isinstance(raw_text, str) else str(raw_text)
                text = self._normalize(text, opts).strip()

                if opts.add_page_headings:
                    if text:
                        body = f"## Page {pno}\n\n{text}"
                    else:
                        body = f"## Page {pno}"
                else:
                    body = text

                pages_md.append(LitePageMarkdown(page_no=pno, markdown=body, char_count=len(body)))

        combined = "\n\n".join(p.markdown for p in pages_md)
        retained_length = len(combined[: opts.max_chars].rstrip()) if opts.max_chars and opts.max_chars > 0 else len(combined)
        combined, truncated = enforce_max_chars(combined, opts.max_chars)

        # If truncated and per-page requested, keep only fully contained pages
        if truncated and opts.return_per_page:
            kept: List[LitePageMarkdown] = []
            acc = 0
            for idx, p in enumerate(pages_md):
                # account for the "\n\n" separators between pages
                sep = 2 if idx > 0 else 0
                if acc + sep + len(p.markdown) > retained_length:
                    break
                acc += sep + len(p.markdown)
                kept.append(p)
            pages_md = kept

        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=page_count,
            total_chars=len(combined),
            truncated=truncated,
            markdown=combined,
            pages=pages_md if opts.return_per_page else [],
            extras={"engine": "pypdf-pagewise"},
        )

    # ---- whole-document extraction (markitdown) ------------------------------

    def _extract_with_markitdown(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        if not self._md:
            raise RuntimeError("markitdown not available for PDF conversion")

        converted = self._md.convert(str(file_path))
        md = converted.markdown or ""
        md = self._normalize(md, opts)

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

    # ---- public API ----------------------------------------------------------

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        """Preserve page requests; use MarkItDown only for whole-document conversion."""
        opts = options or LiteMarkdownOptions()
        if self._needs_page_wise(opts):
            return self._extract_pages_with_pypdf(file_path, opts)
        try:
            result = self._extract_with_markitdown(file_path, opts)
            if result.total_chars:
                return result
        except Exception:
            logger.warning("MarkItDown PDF conversion failed; trying pypdf", exc_info=True)
        return self._extract_pages_with_pypdf(file_path, opts)


class LitePdfMarkdownProcessor(BaseMarkdownProcessor):
    """
    Adapter so the lightweight PDF processor can be used as a full
    ingestion-time BaseMarkdownProcessor (for the Temporal pipeline),
    while still reusing the same lightweight extraction engine.

    - check_file_validity / extract_file_metadata satisfy BaseInputProcessor.
    - convert_file_to_markdown writes an 'output.md' file, as expected by
      IngestionService.process_input and downstream processors.
    """

    description = "Lightweight PDF ingestion path that writes Markdown previews via a fast extractor."

    def __init__(self) -> None:
        super().__init__()
        self._lite = LitePdfToMdProcessor()

    def check_file_validity(self, file_path: Path) -> bool:
        """Accept a readable PDF with at least one page."""
        try:
            with file_path.open("rb") as stream:
                return len(PdfReader(stream).pages) > 0
        except Exception:
            logger.warning("Invalid PDF: %s", file_path, exc_info=True)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        try:
            with file_path.open("rb") as stream:
                doc = PdfReader(stream)
                info = doc.metadata or {}
                return {
                    "title": info.get("/Title") or None,
                    "author": info.get("/Author") or None,
                    "document_name": file_path.name,
                    "page_count": len(doc.pages),
                    "extras": {
                        "pdf.subject": info.get("/Subject") or None,
                        "pdf.producer": info.get("/Producer") or None,
                        "pdf.creator": info.get("/Creator") or None,
                    },
                }
        except Exception as exc:
            logger.warning("Cannot read PDF metadata: %s", file_path, exc_info=True)
            return {"document_name": file_path.name, "error": str(exc)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Use the lightweight extractor to generate Markdown and persist it
        to 'output.md' in the given output directory.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            result = self._lite.extract(file_path, LiteMarkdownOptions())
            markdown = result.markdown or ""
            output_dir.mkdir(parents=True, exist_ok=True)
            output_markdown_path.write_text(markdown, encoding="utf-8")

            engine = (result.extras or {}).get("engine") if isinstance(result.extras, dict) else None
            message = f"Lite PDF conversion succeeded (engine={engine})" if engine else "Lite PDF conversion succeeded."
        except Exception as exc:
            logger.exception("LitePdfMarkdownProcessor: conversion failed for %s", file_path)
            raise InputConversionError(f"LitePdfMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": message,
        }
