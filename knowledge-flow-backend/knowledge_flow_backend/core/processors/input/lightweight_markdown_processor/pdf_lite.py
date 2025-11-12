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
from typing import List

import pypdf

from knowledge_flow_backend.core.processors.input.common.base_input_processor import (
    BaseMarkdownProcessor,
)

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

                pages_md.append(LitePageMarkdown(page_no=pno, markdown=body, char_count=len(body)))

        combined = "\n\n".join(p.markdown for p in pages_md)
        truncated = False
        combined, truncated = enforce_max_chars(combined, opts.max_chars)

        # If truncated, optionally trim per-page details to reflect cut
        if truncated and opts.return_per_page:
            # remaining = len(combined)
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


class PdfLiteMarkdownProcessor(BaseMarkdownProcessor):
    """BaseMarkdownProcessor-compatible wrapper around the lightweight PDF extractor.

    Uses pypdf text extraction (no layout) and writes a single `output.md` in
    the provided `output_dir`, keeping the API homogeneous with other processors.
    """

    def __init__(self) -> None:
        super().__init__()
        self._extractor = PdfLiteMarkdownExtractor()

    def check_file_validity(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                return len(reader.pages) > 0
        except Exception as e:
            logger.error(f"Invalid or unreadable PDF file: {file_path} - {e}")
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        page_count = None
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                page_count = len(reader.pages)
        except Exception:
            logger.warning(f"Could not read PDF metadata for file: {file_path}")
            pass
        try:
            size = file_path.stat().st_size
        except Exception:
            size = None
        return {
            "document_name": file_path.name,
            "file_size_bytes": size,
            "suffix": file_path.suffix,
            "page_count": page_count,
        }

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        opts = LiteMarkdownOptions()
        result = self._extractor.extract(file_path, options=opts)
        md_path.write_text(result.markdown, encoding="utf-8")

        return {"doc_dir": str(output_dir), "md_file": str(md_path)}
