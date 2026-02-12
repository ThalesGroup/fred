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

import fitz
from markitdown import MarkItDown

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
)

# Core idea:
# - Prefer MarkItDown for whole-PDF conversion (good quality, less code).
# - If callers ask for page-level control (page_range, per-page output, page headings),
#   switch to a page-wise path using PyMuPDF (fitz), which ships with markitdown.
# - Fall back gracefully if markitdown or fitz are unavailable.

logger = logging.getLogger(__name__)


# Optional imports guarded for runtime + Pylance friendliness


class LitePdfToMdProcessor(BaseLiteMdProcessor):
    """
    Lightweight PDF → Markdown.

    Fred rationale:
    - Use `markitdown` for "good-enough" Markdown with minimal maintenance.
    - Preserve Fred's page-oriented UX when needed via PyMuPDF page scans.
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

    # ---- page-wise extraction (PyMuPDF) -------------------------------------

    def _extract_pages_with_fitz(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        doc = fitz.open(str(file_path))
        page_count = doc.page_count

        start_p, end_p = self._safe_page_range(page_count, opts.page_range)
        pages_md: List[LitePageMarkdown] = []

        for pno in range(start_p, end_p + 1):
            page = doc.load_page(pno - 1)
            # Plain text is enough for the lightweight path; keeps speed & determinism.
            raw_text = page.get_text("text")
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
        combined, truncated = enforce_max_chars(combined, opts.max_chars)

        # If truncated and per-page requested, keep only fully contained pages
        if truncated and opts.return_per_page:
            kept: List[LitePageMarkdown] = []
            acc = 0
            for idx, p in enumerate(pages_md):
                # account for the "\n\n" separators between pages
                sep = 2 if idx > 0 else 0
                if acc + sep + len(p.markdown) > len(combined):
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
            extras={"engine": "pymupdf-pagewise"},
        )

    # ---- whole-document extraction (markitdown) ------------------------------

    def _extract_with_markitdown(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        if not self._md:
            raise RuntimeError("markitdown not available for PDF conversion")

        converted = self._md.convert(str(file_path))
        # Pylance sometimes flags `.text`; guard with getattr for static peace of mind.
        md = getattr(converted, "text", "") or ""
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
        """
        Strategy:
        - If caller wants page control: use PyMuPDF (fast, deterministic).
        - Else prefer markitdown (best quality/maintenance for whole-doc).
        - On failures, log and fall back to the other path when possible.
        """
        opts = options or LiteMarkdownOptions()

        # Page-wise needs trump markitdown (which doesn't expose page slicing)
        if self._needs_page_wise(opts):
            try:
                result = self._extract_pages_with_fitz(file_path, opts)
                logger.info(
                    "[LITE_MD][PDF][FITZ] file=%s pages=%s chars=%s truncated=%s",
                    file_path.name,
                    result.page_count,
                    result.total_chars,
                    result.truncated,
                )
                return result
            except Exception as e:
                logger.warning(f"Page-wise PDF extraction failed, trying markitdown: {e}")

            # Fall back to whole-doc if page-wise failed
            result = self._extract_with_markitdown(file_path, opts)
            logger.info(
                "[LITE_MD][PDF][FALLBACK_MARKITDOWN] file=%s pages=%s chars=%s truncated=%s",
                file_path.name,
                result.page_count,
                result.total_chars,
                result.truncated,
            )
            return result

        # Whole-document path first (simpler, better formatting when available)
        try:
            result = self._extract_with_markitdown(file_path, opts)
            logger.info(
                "[LITE_MD][PDF][MARKITDOWN] file=%s pages=%s chars=%s truncated=%s",
                file_path.name,
                result.page_count,
                result.total_chars,
                result.truncated,
            )
            # If markitdown produced nothing, fall back to page-wise extraction.
            if result.total_chars == 0:
                logger.warning(
                    "[LITE_MD][PDF][MARKITDOWN_EMPTY] file=%s — attempting fitz fallback",
                    file_path.name,
                )
                result = self._extract_pages_with_fitz(file_path, opts)
                logger.info(
                    "[LITE_MD][PDF][FALLBACK_FITZ_AFTER_MARKITDOWN] file=%s pages=%s chars=%s truncated=%s",
                    file_path.name,
                    result.page_count,
                    result.total_chars,
                    result.truncated,
                )
            return result
        except Exception as e:
            logger.warning(f"markitdown PDF conversion failed, trying page-wise fallback: {e}")

        # Fall back to page-wise text if markitdown fails
        result = self._extract_pages_with_fitz(file_path, opts)
        logger.info(
            "[LITE_MD][PDF][FALLBACK_FITZ] file=%s pages=%s chars=%s truncated=%s",
            file_path.name,
            result.page_count,
            result.total_chars,
            result.truncated,
        )
        return result


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
        """
        Basic validity check using PyMuPDF: the file must be a readable
        PDF with at least one page.
        """
        try:
            doc = fitz.open(str(file_path))
            if doc.page_count <= 0:
                logger.warning("LitePdfMarkdownProcessor: PDF %s has no pages.", file_path)
                return False
            return True
        except Exception as e:
            logger.error("LitePdfMarkdownProcessor: invalid PDF %s: %s", file_path, e)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Lightweight metadata extraction based on PyMuPDF.
        Returns only fields that are cheap to compute.
        """
        try:
            doc = fitz.open(str(file_path))
            info = doc.metadata or {}
            return {
                "title": info.get("title") or None,
                "author": info.get("author") or None,
                "document_name": file_path.name,
                "page_count": doc.page_count,
                "extras": {
                    "pdf.subject": info.get("subject") or None,
                    "pdf.producer": info.get("producer") or None,
                    "pdf.creator": info.get("creator") or None,
                },
            }
        except Exception as e:
            logger.error("LitePdfMarkdownProcessor: error extracting metadata from %s: %s", file_path, e)
            return {"document_name": file_path.name, "error": str(e)}

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
