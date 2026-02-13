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

import pandas as pd

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import CsvTabularProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor

from .lite_markdown_structures import (
    LiteMarkdownOptions,
    LiteMarkdownResult,
    LitePageMarkdown,
    enforce_max_chars,
)

logger = logging.getLogger(__name__)


class LiteCsvToMdProcesor(BaseLiteMdProcessor):
    """Very simple CSV → Markdown table extraction.

    - Reads CSV using Python's csv module
    - Emits a single pipe table, truncated to max rows/cols
    - No images or complex formatting
    """

    description = "Lightweight CSV-to-Markdown table extractor with row/column truncation."

    def __init__(self):
        # Instantiate the robust processor once
        self._tabular_processor = CsvTabularProcessor()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()

        df: pd.DataFrame = self._tabular_processor.convert_file_to_table(file_path)
        if df.empty:
            md = "*Empty CSV*\n"
        else:
            # 2. Apply truncation limits using Pandas slicing
            original_rows = len(df)
            original_cols = len(df.columns)

            # Determine actual rows/cols to show (excluding the header row from 'rows' count)
            # We take the header row + 'max_table_rows' data rows
            rows_to_show = min(original_rows, max(0, opts.max_table_rows) + 1)  # +1 for the header
            cols_to_show = min(original_cols, max(0, opts.max_table_cols))

            # Truncate DataFrame: iloc is based on zero-index position
            df_truncated = df.iloc[0:rows_to_show, 0:cols_to_show]

            # 3. Convert truncated DataFrame to Markdown table string
            # index=False ensures the row index isn't included in the Markdown table
            md_table = df_truncated.to_markdown(index=False)

            lines: List[str] = []
            lines.append("")
            lines.extend(md_table.splitlines())  # Add all lines of the Pandas-generated table

            # Add truncation notice if limits were hit
            # We check against the original limits
            if rows_to_show <= original_rows and rows_to_show < original_rows or cols_to_show < original_cols:
                lines.append("… (table truncated)")

            lines.append("")

            md = "\n".join(lines) + "\n"

        # 4. Enforce final character limits and return LiteMarkdownResult
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


class LiteCsvMarkdownProcessor(BaseMarkdownProcessor):
    """
    Adapter so the lightweight CSV → Markdown extractor can be used as a
    BaseMarkdownProcessor during ingestion, instead of the tabular path.
    """

    description = "Lightweight CSV ingestion that outputs Markdown tables instead of tabular storage."

    def __init__(self) -> None:
        super().__init__()
        self._lite = LiteCsvToMdProcesor()

    def check_file_validity(self, file_path: Path) -> bool:
        try:
            stat = file_path.stat()
            if stat.st_size <= 0:
                logger.warning("LiteCsvMarkdownProcessor: CSV %s is empty.", file_path)
                return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("LiteCsvMarkdownProcessor: invalid CSV %s: %s", file_path, e)
            return False

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Lightweight metadata extraction for CSV.
        """
        try:
            return {
                "document_name": file_path.name,
                "title": file_path.stem,
            }
        except Exception as e:  # noqa: BLE001
            logger.error("LiteCsvMarkdownProcessor: error extracting metadata from %s: %s", file_path, e)
            return {"document_name": file_path.name, "error": str(e)}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Use the lightweight CSV-to-Markdown extractor and save to 'output.md'.
        """
        output_markdown_path = output_dir / "output.md"
        try:
            result = self._lite.extract(file_path, LiteMarkdownOptions())
            markdown = result.markdown or ""
            output_dir.mkdir(parents=True, exist_ok=True)
            output_markdown_path.write_text(markdown, encoding="utf-8")

            message = "Lite CSV conversion succeeded."
        except Exception as exc:  # noqa: BLE001
            logger.exception("LiteCsvMarkdownProcessor: conversion failed for %s", file_path)
            raise InputConversionError(f"LiteCsvMarkdownProcessor failed for '{file_path.name}': {exc}") from exc

        return {
            "doc_dir": str(output_dir),
            "md_file": str(output_markdown_path),
            "message": message,
        }
