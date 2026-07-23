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

import pypdf
from markitdown import MarkItDown

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
    normalize_repeated_chars,
)

logger = logging.getLogger(__name__)

try:
    import pymupdf4llm  # pyright: ignore[reportMissingImports]  # AGPL-3.0/Artifex-dual-licensed, optional (LICENSE-01)
except ImportError:
    pymupdf4llm = None


class LitePdfToMdExtractor(BaseLiteMdProcessor):
    """
    Lightweight PDF → Markdown.

    Fred rationale:
    - Use `markitdown` as the default extractor — no copyleft dependency required.
    - Opportunistically use `pymupdf4llm` (page‑oriented, often higher quality) when the
      optional `pymupdf` extra is installed; see LICENSE-01 in
      docs/swift/COPYLEFT-DEPENDENCIES.md. Never required for the default install.
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
        Extract Markdown using pymupdf4llm (opportunistic engine, only called when
        the optional `pymupdf` extra is installed — see `extract()`).
        - Page‑wise extraction
        - Normalization + cleaning
        - max_chars truncation support
        """
        assert pymupdf4llm is not None, "_extract_pymupdf4llm called without the optional 'pymupdf' extra installed"
        count_char: int = 0
        truncated: bool = False

        # Extract raw pages from pymupdf4llm
        pages = pymupdf4llm.to_markdown(file_path, ignore_images=True, ignore_graphics=True, header=False, footer=False, page_chunks=True)

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

            # Apply your normalization pipeline
            md_text = self._normalize_repeated_chars(text, opts)
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
        - Default: markitdown (no copyleft dependency required).
        - If the optional `pymupdf` extra is installed (LICENSE-01), prefer
          PyMuPDF4LLM instead — page-wise, deterministic, often higher quality.
        - On failures, log and fall back to the other path when possible.
        """
        opts = options or LiteMarkdownOptions()

        if pymupdf4llm is not None:
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
            except Exception as e:
                logger.warning(f"Pymupdf4llm PDF extraction failed, trying markitdown: {e}")

        # Default extraction: Markitdown
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
        self._lite = LitePdfToMdExtractor()

    def check_file_validity(self, file_path: Path) -> bool:
        """
        Basic validity check using pypdf: the file must be a readable
        PDF with at least one page.
        """
        try:
            reader = pypdf.PdfReader(str(file_path))
            if len(reader.pages) <= 0:
                logger.warning("LitePdfMarkdownProcessor: PDF %s has no pages.", file_path)
                return False
            return True
        except Exception as e:
            logger.error("LitePdfMarkdownProcessor: invalid PDF %s: %s", file_path, e)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Lightweight metadata extraction based on pypdf.
        Returns only fields that are cheap to compute.
        """
        try:
            reader = pypdf.PdfReader(str(file_path))
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
