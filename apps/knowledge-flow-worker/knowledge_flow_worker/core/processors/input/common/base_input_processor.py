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

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
from pydantic import BaseModel
from tabulate import tabulate

logger = logging.getLogger(__name__)


class StoredObjectInfo(BaseModel):
    """
    Metadata returned when a processor writes a tabular artifact.
    """

    key: str
    size: int
    file_name: str
    content_type: str | None = None
    modified: datetime | None = None
    etag: str | None = None
    document_uid: str | None = None


class InputConversionError(RuntimeError):
    """
    Raised when an input processor cannot generate a usable preview artifact.
    """


class BaseInputProcessor(ABC):
    """
    Format-specific validation, metadata extraction and document conversion.
    The control plane supplies the document identity and catalog metadata.
    """

    description: Optional[str] = None

    @abstractmethod
    def check_file_validity(self, file_path: Path) -> bool:
        pass

    @abstractmethod
    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Return a flat dict of optional fields you discovered.
        Supported keys include (examples, all optional):
          - title, author, created, modified, last_modified_by
          - mime_type, file_size_bytes, page_count, row_count, sha256, language, file_type
          - pull_location
          - tag_ids, tag_names, library_path, library_folder
          - license, confidential, acl
        Unknown keys are ignored.
        """


def read_text_with_fallback(file_path: Path) -> str:
    """
    Read a plain-text file whose encoding is not guaranteed to be UTF-8.

    Windows tools still write cp1252 ("ANSI"), invalid as UTF-8 as soon as it
    holds an accent; latin-1 decodes any byte, so this never fails. Newlines are
    normalised as text-mode `open()` would.
    """
    raw = file_path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


class BaseMarkdownProcessor(BaseInputProcessor):
    """For processors that convert to Markdown."""

    @abstractmethod
    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Convert the input file to Markdown and save it in the output directory.
        Returns a dict of paths or facts discovered (optional).
        Must raise on failure instead of returning a "status=error" payload.
        """


class BaseTabularProcessor(BaseInputProcessor):
    """
    Base class for tabular input processors backed by DuckDB-readable sources.

    Why this exists:
    - The input stage only needs to recognize that one file belongs to the
      tabular ingestion flow.
    - Tabular processors no longer promise a pandas DataFrame preview or an
      `output/table.csv` artifact during input processing.
    - The shared tabular preview path should reuse the same DuckDB-readable
      source description that the Parquet output stage already relies on.

    How to use:
    - Subclass it for processors whose real output is produced later by a
      tabular output processor, typically as a Parquet artifact.
    - Override `build_duckdb_source_relation_sql(...)` when the processor can
      expose a DuckDB relation for bounded preview rendering.
    """

    def build_duckdb_source_relation_sql(self, file_path: Path, *, sample_size: int | None = None) -> str:
        """
        Return the DuckDB relation SQL that reads one tabular source file.

        Why this exists:
        - The Parquet output stage and lightweight preview flows should share
          the same source relation contract instead of materializing pandas
          DataFrames during input processing.

        How to use:
        - Override this method in tabular processors that can expose their
          source file through DuckDB.
        - Return only a relation SQL fragment suitable for `SELECT * FROM ...`.

        Example:
        - `sql = processor.build_duckdb_source_relation_sql(Path("/tmp/data.csv"), sample_size=-1)`
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not expose a DuckDB tabular source relation.")

    def render_markdown_preview(self, file_path: Path, *, max_rows: int, max_cols: int) -> str:
        """
        Render a bounded markdown preview from one DuckDB-readable tabular file.

        Why this exists:
        - Lightweight CSV previews should reuse the same DuckDB-oriented
          ingestion path as the Parquet pipeline instead of loading the full
          source into pandas memory.

        How to use:
        - Pass the local source file path and the desired row/column limits.
        - The preview is read directly from the source relation and never
          persists `output/table.csv`.

        Example:
        - `markdown = processor.render_markdown_preview(Path("/tmp/data.csv"), max_rows=20, max_cols=10)`
        """
        visible_rows = max(0, max_rows)
        visible_cols = max(0, max_cols)
        if visible_rows == 0 or visible_cols == 0:
            return "*Empty CSV*\n"

        relation_sql = self.build_duckdb_source_relation_sql(file_path)
        preview_limit = visible_rows + 1
        connection = duckdb.connect(database=":memory:")
        try:
            preview_query = f"SELECT * FROM {relation_sql} LIMIT {preview_limit}"  # nosec B608
            cursor = connection.execute(preview_query)
            column_names = [str(description[0]) for description in (cursor.description or [])]
            rows = cursor.fetchall()
        finally:
            connection.close()

        if not rows or not column_names:
            return "*Empty CSV*\n"

        truncated_rows = len(rows) > visible_rows
        truncated_cols = len(column_names) > visible_cols
        visible_column_names = column_names[:visible_cols]
        visible_data_rows = [tuple(row[:visible_cols]) for row in rows[:visible_rows]]
        return self._rows_to_markdown_preview(
            column_names=visible_column_names,
            rows=visible_data_rows,
            truncated=truncated_rows or truncated_cols,
        )

    @staticmethod
    def _rows_to_markdown_preview(column_names: list[str], rows: list[tuple[object, ...]], *, truncated: bool) -> str:
        """
        Format one small tabular preview as GitHub-flavored Markdown.

        Why this exists:
        - Tabular previews should be rendered consistently whether they come
          from raw source inspection or later Parquet-backed reads.

        How to use:
        - Pass already-bounded columns and rows.
        - Set `truncated=True` when the caller intentionally omitted extra rows
          or columns from the preview.
        """
        if not column_names:
            return "*Empty CSV*\n"

        def _format_cell(value: object) -> str:
            text = "" if value is None else str(value)
            return text.replace("|", "&#124;").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        formatted_headers = [_format_cell(name) for name in column_names]
        formatted_rows = [[_format_cell(cell) for cell in row] for row in rows]
        markdown_table = tabulate(formatted_rows, headers=formatted_headers, tablefmt="github")

        lines = ["", markdown_table]
        if truncated:
            lines.append("... (table truncated)")
        lines.append("")
        return "\n".join(lines) + "\n"
