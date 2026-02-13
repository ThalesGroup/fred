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
from pptx import Presentation

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


def _escape_pipes(s: str) -> str:
    return s.replace("|", r"\|")


class LitePptxToMdExtractor(BaseLiteMdProcessor):
    """
    Lightweight PPTX → Markdown.

    Fred rationale:
    - Whole-deck via `markitdown` keeps maintenance tiny and output “good enough.”
    - Slide-wise path via `python-pptx` preserves Fred controls:
        * per-slide pages
        * '## Slide n' headings
        * table row/col truncation
        * optional speaker notes extraction
    - Always enforce token discipline: normalize + max_chars cap.
    """

    description = "Fast PPTX-to-Markdown extractor supporting slide-wise or whole-deck paths."

    def __init__(self) -> None:
        self._md = MarkItDown()

    # ---------- public API ----------------------------------------------------

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        # If caller needs slide-structured output, go slide-wise
        if opts.return_per_page or opts.add_page_headings or opts.page_range:
            try:
                return self._extract_slidewise(file_path, opts)
            except Exception as e:
                logger.warning(f"Slide-wise PPTX extraction failed, trying markitdown: {e}")

        # Otherwise prefer markitdown
        if self._md:
            try:
                return self._extract_with_markitdown(file_path, opts)
            except Exception as e:
                logger.warning(f"markitdown PPTX conversion failed, trying slide-wise fallback: {e}")

        # Fallback if markitdown unavailable or failed
        return self._extract_slidewise(file_path, opts)

    # ---------- markitdown path ----------------------------------------------

    def _extract_with_markitdown(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        converted = self._md.convert(str(file_path))  # Pylance may not know .text; guard with getattr next line
        md = getattr(converted, "text", "") or ""
        if opts.normalize_whitespace:
            md = collapse_whitespace(md)
        md, truncated = enforce_max_chars(md, opts.max_chars)
        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=None,
            total_chars=len(md),
            truncated=truncated,
            markdown=md,
            pages=[],
            extras={"engine": "markitdown"},
        )

    # ---------- slide-wise path (python-pptx) --------------------------------

    def _extract_slidewise(self, file_path: Path, opts: LiteMarkdownOptions) -> LiteMarkdownResult:
        if Presentation is None:
            raise RuntimeError("python-pptx not available for slide-wise extraction")

        pres = Presentation(str(file_path))
        slide_count = len(pres.slides)

        start_s, end_s = self._safe_slide_range(slide_count, opts.page_range)
        pages: List[LitePageMarkdown] = []

        for s_idx in range(start_s, end_s + 1):
            slide = pres.slides[s_idx - 1]
            lines: List[str] = []

            # Slide heading (optional)
            if opts.add_page_headings:
                # Try to pick a title text if present; fallback to generic heading
                title_text = ""
                try:
                    if slide.shapes.title and slide.shapes.title.text:
                        title_text = slide.shapes.title.text.strip()
                except Exception:
                    title_text = ""
                heading = f"## Slide {s_idx}" + (f": {title_text}" if title_text else "")
                lines.append(heading)
                lines.append("")

            # Slide body: iterate shapes
            for shape in slide.shapes:
                try:
                    part = self._shape_to_markdown(shape, opts)
                    if part:
                        lines.append(part)
                except Exception as e:
                    logger.debug(f"Shape export skipped on slide {s_idx}: {e}")

            # Speaker notes (optional, only if slide-wise path is chosen)
            try:
                notes_text = self._extract_notes(slide)
                if notes_text:
                    lines.append("")
                    lines.append("> **Notes:**")
                    for note_line in notes_text.splitlines():
                        if note_line.strip():
                            lines.append(f"> {note_line}")
                        else:
                            lines.append(">")
            except Exception:
                logger.debug("No speaker notes found or extraction failed.")
                pass

            slide_md = "\n".join(line for line in lines if line is not None)
            if opts.normalize_whitespace:
                slide_md = collapse_whitespace(slide_md)
            pages.append(LitePageMarkdown(page_no=s_idx, markdown=slide_md, char_count=len(slide_md)))

        combined = "\n\n".join(p.markdown for p in pages)
        combined, truncated = enforce_max_chars(combined, opts.max_chars)

        if truncated and opts.return_per_page:
            # Keep only fully contained slides under the truncation budget
            kept: List[LitePageMarkdown] = []
            acc = 0
            for i, p in enumerate(pages):
                sep = 2 if i > 0 else 0
                if acc + sep + len(p.markdown) > len(combined):
                    break
                acc += sep + len(p.markdown)
                kept.append(p)
            pages = kept

        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=slide_count,
            total_chars=len(combined),
            truncated=truncated,
            markdown=combined,
            pages=pages if opts.return_per_page else [],
            extras={"engine": "python-pptx-slidewise"},
        )

    # ---------- helpers -------------------------------------------------------

    def _safe_slide_range(self, slide_count: int, page_range: Tuple[int, int] | None) -> Tuple[int, int]:
        if not page_range:
            return (1, slide_count)
        start_s, end_s = page_range
        start_s = max(1, min(start_s, slide_count))
        end_s = max(start_s, min(end_s, slide_count))
        return (start_s, end_s)

    def _shape_to_markdown(self, shape, opts: LiteMarkdownOptions) -> str:
        """
        Map a shape to minimal Markdown:
        - Text frames → paragraphs / bullets (with indentation by level)
        - Tables → pipe tables with row/col caps
        - Ignore images/graphics by design (lightweight path)
        """
        # Table
        if hasattr(shape, "has_table") and shape.has_table:
            return self._table_to_markdown(shape.table, opts)

        # Text
        if hasattr(shape, "has_text_frame") and shape.has_text_frame and shape.text_frame:
            return self._text_frame_to_markdown(shape.text_frame)

        # Titles sometimes aren’t marked as text_frame on older decks
        try:
            if getattr(shape, "text", None):
                return str(shape.text).strip()
        except Exception:
            logger.warning("Failed to extract text from shape.")
            pass

        return ""  # ignore images, charts, media, etc. (lightweight pass)

    def _text_frame_to_markdown(self, text_frame) -> str:
        """
        Convert text frame to Markdown paragraphs with bullets.
        PPTX paragraphs have a 'level' (indent) and may have bullet flags.
        """
        out: List[str] = []
        for para in text_frame.paragraphs:
            # Gather runs; fallback to paragraph.text if needed
            chunks: List[str] = []
            try:
                for run in para.runs:
                    if run.text:
                        chunks.append(run.text)
            except Exception:
                # Some paragraphs behave oddly; use the plain text
                if getattr(para, "text", None):
                    chunks.append(str(para.text))

            text = " ".join(c.strip() for c in chunks if c and str(c).strip())
            text = text.strip()

            if not text:
                continue

            # Indentation by paragraph level
            level = getattr(para, "level", 0) or 0
            indent = "  " * int(level)

            # Bullet detection: if the paragraph has a bullet or level>0, emit list item
            has_bullet = False
            try:
                if para.level and para.level > 0:
                    has_bullet = True
                elif para._p is not None and para._p.pPr is not None and getattr(para._p.pPr, "buNone", None) is None:
                    # heuristic: absence of 'no bullet' marking means it may be bulleted
                    has_bullet = True
            except Exception:
                logger.debug("Bullet detection failed for paragraph; assuming no bullet.")
                pass

            if has_bullet:
                out.append(f"{indent}- {text}")
            else:
                out.append(f"{indent}{text}")

        return "\n".join(out)

    def _table_to_markdown(self, table, opts: LiteMarkdownOptions) -> str:
        """
        Convert a python-pptx Table to a pipe Markdown table with truncation.
        """
        try:
            rows = len(table.rows)
            cols = len(table.columns)
        except Exception:
            return ""

        max_r = min(rows, max(0, opts.max_table_rows) + 1)  # +1 to keep header row
        max_c = min(cols, max(0, opts.max_table_cols))

        # Header (first row)
        def cell_text(r: int, c: int) -> str:
            try:
                cell = table.cell(r, c)
                # Join paragraphs with spaces, keep it light
                parts: List[str] = []
                for p in cell.text_frame.paragraphs:
                    if p.text:
                        parts.append(p.text.strip())
                return _escape_pipes(" ".join(parts).strip())
            except Exception:
                return ""

        lines: List[str] = []
        lines.append("")
        # Build header
        header = [cell_text(0, c) for c in range(max_c)]
        header = [h if h else " " for h in header]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * max_c) + " |")

        # Body rows
        for r in range(1, max_r):
            row_cells = [cell_text(r, c) for c in range(max_c)]
            row_cells = [v if v else " " for v in row_cells]
            lines.append("| " + " | ".join(row_cells) + " |")

        if max_r < rows or max_c < cols:
            lines.append("… (table truncated)")

        lines.append("")
        return "\n".join(lines)

    def _extract_notes(self, slide) -> str:
        """
        Extract speaker notes (if any) as plain text.
        """
        try:
            notes_slide = slide.notes_slide
            if notes_slide and notes_slide.notes_text_frame:
                raw = notes_slide.notes_text_frame.text or ""
                return raw.strip()
        except Exception:
            logger.debug("No speaker notes found or extraction failed.")
            pass
        return ""


class LitePptxMarkdownProcessor(BaseMarkdownProcessor):
    """
    Adapter so the lightweight PPTX extractor can be used as a full
    ingestion-time BaseMarkdownProcessor while reusing LitePptxToMdExtractor.
    """

    description = "Lightweight PPTX ingestion that converts slides to Markdown previews."

    def __init__(self) -> None:
        super().__init__()
        self._lite = LitePptxToMdExtractor()

    def check_file_validity(self, file_path: Path) -> bool:
        try:
            pres = Presentation(str(file_path))
            if len(pres.slides) == 0:
                logger.warning("LitePptxMarkdownProcessor: PPTX %s has no slides.", file_path)
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("LitePptxMarkdownProcessor: invalid PPTX %s: %s", file_path, e)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Lightweight metadata extraction for PPTX.
        """
        try:
            pres = Presentation(str(file_path))
            slide_count = len(pres.slides)
            return {
                "document_name": file_path.name,
                "title": file_path.stem,
                "page_count": slide_count,
            }
        except Exception as e:  # noqa: BLE001
            logger.error("LitePptxMarkdownProcessor: error extracting metadata from %s: %s", file_path, e)
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Use the lightweight extractor to generate Markdown for PPTX and save
        it to 'output.md' in the provided output directory.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            result = self._lite.extract(file_path, LiteMarkdownOptions())
            markdown = result.markdown or ""
            output_dir.mkdir(parents=True, exist_ok=True)
            output_markdown_path.write_text(markdown, encoding="utf-8")

            engine = (result.extras or {}).get("engine") if isinstance(result.extras, dict) else None
            message = f"Lite PPTX conversion succeeded (engine={engine})" if engine else "Lite PPTX conversion succeeded."
        except Exception as exc:  # noqa: BLE001
            logger.exception("LitePptxMarkdownProcessor: conversion failed for %s", file_path)
            raise InputConversionError(f"LitePptxMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": message,
        }
