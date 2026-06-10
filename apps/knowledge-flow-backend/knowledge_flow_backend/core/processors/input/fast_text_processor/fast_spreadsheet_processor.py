# Copyright Thales 2026
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

from pathlib import Path
from typing import cast

import pandas as pd

from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastPageText,
    FastTextOptions,
    FastTextResult,
    collapse_whitespace,
    enforce_max_chars,
    trim_empty_lines,
)


class FastSpreadsheetProcessor(BaseFastTextProcessor):
    """Fast extractor for Excel attachments."""

    @staticmethod
    def _fallback_text(file_path: Path) -> str:
        return (
            f"Spreadsheet attachment: {file_path.name}\n"
            f"Format: {file_path.suffix.lower().lstrip('.') or 'unknown'}\n"
            "Workbook content could not be expanded, but the file remains attached to the conversation."
        )

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        opts = options or FastTextOptions()
        max_rows = max(1, opts.max_table_rows)
        max_cols = max(1, opts.max_table_cols)
        pages: list[FastPageText] = []
        sections: list[str] = []

        try:
            workbook = pd.ExcelFile(file_path)
            for index, sheet_name in enumerate(workbook.sheet_names, start=1):
                frame = (
                    cast(
                        pd.DataFrame,
                        workbook.parse(sheet_name=str(sheet_name), nrows=max_rows),
                    )
                    .iloc[:, :max_cols]
                    .fillna("")
                )
                preview = frame.to_markdown(index=False) if not frame.empty else "_(empty sheet)_"
                text = f"## Sheet: {sheet_name}\n\n{preview}"
                pages.append(FastPageText(page_no=index, text=text, char_count=len(text)))
                sections.append(text)
        except Exception:
            fallback = self._fallback_text(file_path)
            return FastTextResult(
                document_name=file_path.name,
                page_count=1,
                total_chars=len(fallback),
                truncated=False,
                text=fallback,
                extras={"file_type": "spreadsheet", "extension": file_path.suffix.lower(), "fallback_only": True},
            )

        text = "\n\n".join(sections) if sections else self._fallback_text(file_path)
        if opts.normalize_whitespace:
            text = collapse_whitespace(text)
        if opts.trim_empty_lines:
            text = trim_empty_lines(text)
        text, truncated = enforce_max_chars(text, opts.max_chars)
        return FastTextResult(
            document_name=file_path.name,
            page_count=len(pages) or 1,
            total_chars=len(text),
            truncated=truncated,
            text=text,
            pages=pages if opts.return_per_page else [],
            extras={"file_type": "spreadsheet", "extension": file_path.suffix.lower(), "sheet_count": len(pages)},
        )
