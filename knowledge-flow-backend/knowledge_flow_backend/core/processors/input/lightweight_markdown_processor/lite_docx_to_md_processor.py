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

from markitdown import MarkItDown

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

    def __init__(self) -> None:
        # Single MarkItDown instance is cheap and reusable.
        self._md = MarkItDown()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        # MarkItDown auto-detects file type and returns .text markdown
        converted = self._md.convert(str(file_path))
        md = getattr(converted, "text", "")

        # Fred post-processing guarantees -------------------------------------
        if opts.normalize_whitespace:
            md = collapse_whitespace(md)

        # Enforce global character budget (protects downstream token budgets)
        md, truncated = enforce_max_chars(md, opts.max_chars)

        # We don't have true "pages" for DOCX; preserve the API by returning one page if requested
        pages = [LitePageMarkdown(page_no=1, markdown=md, char_count=len(md))] if opts.return_per_page else []

        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=None,  # DOCX has no stable page model here
            total_chars=len(md),
            truncated=truncated,
            markdown=md,
            pages=pages,
            extras={"engine": "markitdown"},
        )
