from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pypdf

from .lite_types import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    collapse_whitespace,
    enforce_max_chars,
)

logger = logging.getLogger(__name__)


class PdfLiteMarkdownExtractor:
    """Fast, dependency-light PDF → Markdown extraction.

    - Uses pypdf's text extraction per page (no layout reconstruction)
    - Injects optional '## Page N' markers for navigation
    - Skips image rendering; no VLM calls
    - No disk writes; returns strings only
    """

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)

            start_p, end_p = 1, page_count
            if opts.page_range:
                start_p, end_p = opts.page_range
                start_p = max(1, min(start_p, page_count))
                end_p = max(start_p, min(end_p, page_count))

            pages_md: List[LitePageMarkdown] = []

            for pno in range(start_p, end_p + 1):
                page = reader.pages[pno - 1]
                text = page.extract_text() or ""
                if opts.normalize_whitespace:
                    text = collapse_whitespace(text)

                if opts.add_page_headings:
                    body = f"## Page {pno}\n\n{text.strip()}" if text.strip() else f"## Page {pno}"
                else:
                    body = text

                pages_md.append(
                    LitePageMarkdown(page_no=pno, markdown=body, char_count=len(body))
                )

        combined = "\n\n".join(p.markdown for p in pages_md)
        truncated = False
        combined, truncated = enforce_max_chars(combined, opts.max_chars)

        # If truncated, optionally trim per-page details to reflect cut
        if truncated and opts.return_per_page:
            remaining = len(combined)
            # crude heuristic: keep pages while within the truncated combined text
            kept: List[LitePageMarkdown] = []
            acc = 0
            for p in pages_md:
                if acc + len(p.markdown) + (2 if kept else 0) > len(combined):
                    break
                kept.append(p)
                acc += len(p.markdown) + (2 if kept else 0)
            pages_md = kept

        result = LiteMarkdownResult(
            document_name=file_path.name,
            page_count=page_count,
            total_chars=len(combined),
            truncated=truncated,
            markdown=combined,
            pages=pages_md if opts.return_per_page else [],
            extras={},
        )
        return result

