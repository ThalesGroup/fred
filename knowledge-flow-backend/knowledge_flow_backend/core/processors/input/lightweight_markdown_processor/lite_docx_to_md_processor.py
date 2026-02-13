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
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

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

logger = logging.getLogger(__name__)


class LiteDocxToMdProcessor(BaseLiteMdProcessor):
    """
    Lightweight DOCX → Markdown via markitdown.

    Fred rationale:
    - Delegate complex DOCX parsing to a maintained lib (less code, fewer bugs).
    - Keep Fred's guarantees: normalization, truncation, and (optionally) per-page-like API.
    - Same output contract as other lightweight extractors (in-memory strings only).
    """

    description = "Fast DOCX-to-Markdown converter using markitdown for lightweight agent workflows."

    def __init__(self) -> None:
        # Single MarkItDown instance is cheap and reusable.
        self._md = MarkItDown()
        try:
            md_ver = version("markitdown")
        except PackageNotFoundError:
            md_ver = "<unknown>"
        logger.info("LiteDocxToMdProcessor initialized | markitdown=%s", md_ver)

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        # ---- File preflight -------------------------------------------------
        try:
            stat = file_path.stat()
            logger.info(
                "DOCX lite extract start | name=%s size=%dB exists=%s suffix=%s",
                file_path.name,
                stat.st_size,
                file_path.exists(),
                file_path.suffix,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to stat input file %s: %s", file_path, e)

        # MarkItDown auto-detects file type and returns Markdown text.
        # Be defensive across versions: try common attributes, then fallback.
        converted = self._md.convert(str(file_path))
        md = ""
        engine = "markitdown"
        logger.debug(
            "MarkItDown.convert done | type=%s has_text=%s has_markdown=%s has_content=%s has_md=%s",
            type(converted).__name__,
            hasattr(converted, "text"),
            hasattr(converted, "markdown"),
            hasattr(converted, "content"),
            hasattr(converted, "md"),
        )

        selected_attr = None
        for attr in ("text", "markdown", "content", "md"):
            try:
                val = getattr(converted, attr, None)
                if isinstance(val, str) and val.strip():
                    md = val
                    logger.debug("Using MarkItDown attribute '%s' | length=%d", attr, len(md))
                    selected_attr = attr
                    break
            except Exception:
                logger.debug("Accessing unknown attribute '%s' on MarkItDown converted object failed", attr)
                # Accessing unknown attrs is safe; continue to next
                pass

        # Keep a copy of the raw markdown prior to normalization/truncation
        raw_md = md
        if raw_md is not None:
            logger.info(
                "Raw markdown (pre-normalization) | source_attr=%s len=%d",
                selected_attr or "<none>",
                len(raw_md),
            )
            if raw_md:
                logger.debug("----- BEGIN RAW MARKDOWN -----\n%s\n----- END RAW MARKDOWN -----", raw_md)

        if not md:
            logger.warning("MarkItDown returned empty text for DOCX; using python-docx fallback")
            try:
                md = self._fallback_docx_to_md(file_path)
                engine = "python-docx-fallback"
                logger.info("Fallback produced length=%d chars", len(md))
            except Exception as e:  # noqa: BLE001
                logger.error(f"DOCX fallback extraction failed: {e}")
                md = ""

        # Fred post-processing guarantees -------------------------------------
        if opts.normalize_whitespace:
            before = len(md)
            md = collapse_whitespace(md)
            logger.info("Whitespace normalization | before=%d after=%d", before, len(md))

        # Enforce global character budget (protects downstream token budgets)
        md, truncated = enforce_max_chars(md, opts.max_chars)
        if truncated:
            logger.info("Max chars enforced | limit=%d final=%d", opts.max_chars, len(md))

        # We don't have true "pages" for DOCX; preserve the API by returning one page if requested
        pages = [LitePageMarkdown(page_no=1, markdown=md, char_count=len(md))] if opts.return_per_page else []
        logger.info(
            "DOCX lite extract end | engine=%s final_len=%d pages=%d sample=%r",
            engine,
            len(md),
            len(pages),
            (md[:120].replace("\n", " ") if md else ""),
        )
        if md:
            logger.debug("----- BEGIN FINAL MARKDOWN -----\n%s\n----- END FINAL MARKDOWN -----", md)

        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=None,  # DOCX has no stable page model here
            total_chars=len(md),
            truncated=truncated,
            markdown=md,
            pages=pages,
            extras={"engine": engine},
        )

    def _fallback_docx_to_md(self, file_path: Path) -> str:
        """Very simple DOCX → Markdown fallback using python-docx.

        - Extracts paragraph text lines.
        - Extracts tables as pipe-delimited rows (no headers inference).
        """
        try:
            from docx import Document  # type: ignore
        except Exception as e:  # noqa: BLE001
            logger.error(f"python-docx not available for fallback: {e}")
            return ""

        doc = Document(str(file_path))
        lines: list[str] = []

        # Paragraphs
        non_empty_paras = 0
        for p in doc.paragraphs:
            txt = (p.text or "").strip()
            if txt:
                lines.append(txt)
                non_empty_paras += 1

        # Tables (best-effort, rows only)
        tbl_count = 0
        non_empty_rows = 0
        for table in getattr(doc, "tables", []):
            tbl_count += 1
            for row in getattr(table, "rows", []):
                cells = [c.text.replace("|", r"\|") if getattr(c, "text", None) else "" for c in row.cells]
                line = "| " + " | ".join(cells) + " |" if cells else "| |"
                # Only count as non-empty if any cell has text
                if any(c.strip() for c in cells):
                    non_empty_rows += 1
                lines.append(line)

        md = "\n\n".join(lines).strip()
        logger.info(
            "DOCX fallback summary | paragraphs=%d tables=%d non_empty_rows=%d md_len=%d sample=%r",
            non_empty_paras,
            tbl_count,
            non_empty_rows,
            len(md),
            (md[:120].replace("\n", " ") if md else ""),
        )
        return md


class LiteDocxMarkdownProcessor(BaseMarkdownProcessor):
    """
    Adapter so the lightweight DOCX processor can be used as a full
    ingestion-time BaseMarkdownProcessor while reusing LiteDocxToMdProcessor.
    """

    description = "Lightweight DOCX ingestion that saves Markdown previews using the lite extractor."

    def __init__(self) -> None:
        super().__init__()
        self._lite = LiteDocxToMdProcessor()

    def check_file_validity(self, file_path: Path) -> bool:
        try:
            stat = file_path.stat()
            if stat.st_size <= 0:
                logger.warning("LiteDocxMarkdownProcessor: DOCX %s is empty.", file_path)
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("LiteDocxMarkdownProcessor: invalid DOCX %s: %s", file_path, e)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Lightweight metadata extraction for DOCX.
        Only fields that are cheap to compute are returned.
        """
        try:
            # Avoid bringing in heavy dependencies; we only expose what we know.
            return {
                "document_name": file_path.name,
                "title": file_path.stem,
            }
        except Exception as e:  # noqa: BLE001
            logger.error("LiteDocxMarkdownProcessor: error extracting metadata from %s: %s", file_path, e)
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Use the lightweight extractor to generate Markdown for DOCX and save
        it to 'output.md' in the provided output directory.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            result = self._lite.extract(file_path, LiteMarkdownOptions())
            markdown = result.markdown or ""
            output_dir.mkdir(parents=True, exist_ok=True)
            output_markdown_path.write_text(markdown, encoding="utf-8")

            engine = (result.extras or {}).get("engine") if isinstance(result.extras, dict) else None
            message = f"Lite DOCX conversion succeeded (engine={engine})" if engine else "Lite DOCX conversion succeeded."
        except Exception as exc:  # noqa: BLE001
            logger.exception("LiteDocxMarkdownProcessor: conversion failed for %s", file_path)
            raise InputConversionError(f"LiteDocxMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": message,
        }
