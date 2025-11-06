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

import csv
import logging
from pathlib import Path
from typing import List

from .lite_types import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    enforce_max_chars,
)

logger = logging.getLogger(__name__)


class CsvLiteMarkdownExtractor:
    """Very simple CSV → Markdown table extraction.

    - Reads CSV using Python's csv module
    - Emits a single pipe table, truncated to max rows/cols
    - No images or complex formatting
    """

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        try:
            with file_path.open("r", encoding="utf-8", newline="") as f:
                reader = list(csv.reader(f))
        except UnicodeDecodeError:
            # Fallback for odd encodings
            with file_path.open("r", encoding="latin1", newline="") as f:
                reader = list(csv.reader(f))

        if not reader:
            md = "*Empty CSV*\n"
            md, truncated = enforce_max_chars(md, opts.max_chars)
            return LiteMarkdownResult(
                document_name=file_path.name,
                page_count=None,
                total_chars=len(md),
                truncated=truncated,
                markdown=md,
                pages=[LitePageMarkdown(page_no=1, markdown=md, char_count=len(md))] if opts.return_per_page else [],
                extras={},
            )

        # Determine original dimensions
        original_rows = len(reader)
        original_cols = max((len(r) for r in reader), default=0)

        rows = min(original_rows, max(0, opts.max_table_rows))
        cols = min(original_cols, max(0, opts.max_table_cols))
        if rows == 0 or cols == 0:
            md = "*CSV has no visible rows/columns under current limits*\n"
            md, truncated = enforce_max_chars(md, opts.max_chars)
            return LiteMarkdownResult(
                document_name=file_path.name,
                page_count=None,
                total_chars=len(md),
                truncated=truncated,
                markdown=md,
                pages=[LitePageMarkdown(page_no=1, markdown=md, char_count=len(md))] if opts.return_per_page else [],
                extras={},
            )

        # Build a simple markdown table
        # Use the first row as header; pad/clip to 'cols'
        header_row = [(reader[0][c] if c < len(reader[0]) else "") for c in range(cols)]
        header_row = [(h if h else " ") for h in header_row]

        lines: List[str] = []
        lines.append(f"<!-- TABLE_START:rows={original_rows} cols={original_cols} -->")
        lines.append("| " + " | ".join(header_row) + " |")
        lines.append("| " + " | ".join(["---"] * cols) + " |")

        for r in range(1, rows):
            row = reader[r] if r < len(reader) else []
            cells = [(row[c] if c < len(row) else "") for c in range(cols)]
            cells = [(c if c else " ") for c in cells]
            lines.append("| " + " | ".join(cells) + " |")

        if rows < original_rows or cols < original_cols:
            lines.append("… (table truncated)")

        lines.append("<!-- TABLE_END -->")

        md = "\n".join(lines) + "\n"

        md, truncated = enforce_max_chars(md, opts.max_chars)
        return LiteMarkdownResult(
            document_name=file_path.name,
            page_count=None,
            total_chars=len(md),
            truncated=truncated,
            markdown=md,
            pages=[LitePageMarkdown(page_no=1, markdown=md, char_count=len(md))] if opts.return_per_page else [],
            extras={},
        )
