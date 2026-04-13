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

import csv
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseTabularProcessor

logger = logging.getLogger(__name__)

DEFAULT_CSV_ENCODINGS = ["utf-8", "latin1", "iso-8859-1"]


@dataclass(frozen=True)
class CsvReadOptions:
    """
    Minimal CSV read settings reused across lightweight and tabular flows.

    Why this exists:
    - Large CSV processing should discover delimiter and encoding once, then
      feed those settings to DuckDB or pandas without reimplementing detection.

    How to use:
    - Build it with `CsvTabularProcessor.inspect_read_options(...)`.
    - Reuse the returned values when opening the CSV in DuckDB or pandas.

    Example:
    - `options = processor.inspect_read_options(Path("/tmp/data.csv"))`
    """

    delimiter: str
    encoding: str
    header: bool = True


class CsvTabularProcessor(BaseTabularProcessor):
    """
    CSV input processor that can either inspect or fully materialize one CSV.

    Why this exists:
    - The ingestion pipeline needs cheap CSV inspection for metadata and
      preview generation, while some lightweight markdown flows still expect a
      pandas DataFrame.

    How to use:
    - Use `inspect_read_options(...)` for scalable tabular ingestion.
    - Use `convert_file_to_table(...)` only for flows that explicitly need a
      pandas DataFrame.
    """

    description = "Parses CSV files, detects delimiters/encodings, and exposes scalable read settings."

    def check_file_validity(self, file_path: Path) -> bool:
        """
        Verify that the input path points to one CSV file on disk.

        Why this exists:
        - Early validation keeps the rest of the CSV helpers focused on parsing
          instead of path/suffix checks.

        How to use:
        - Call before attempting delimiter or encoding detection.
        """
        return file_path.suffix.lower() == ".csv" and file_path.is_file()

    def detect_delimiter(self, file_path: Path, encodings: list[str]) -> str:
        """
        Detect the CSV delimiter from a small file sample.

        Why this exists:
        - Real-world CSV uploads drift between comma, semicolon, tab, and pipe
          separators.

        How to use:
        - Pass the candidate encodings that should be tried while sniffing.
        """
        for enc in encodings:
            try:
                with open(file_path, encoding=enc) as file_handle:
                    sample = file_handle.read(4096)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                return dialect.delimiter
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to detect delimiter for %s with encoding '%s': %s", file_path, enc, exc)
        return ","

    def inspect_read_options(self, path: Path, encodings: list[str] | None = None) -> CsvReadOptions:
        """
        Return the delimiter and encoding that DuckDB can use for one CSV file.

        Why this exists:
        - The scalable tabular pipeline should inspect CSV settings once and
          then reuse them for metadata extraction, preview generation, and
          Parquet conversion.

        How to use:
        - Pass the CSV path and optional candidate encodings.
        - Raises `ValueError` when no compatible delimiter/encoding pair works.

        Example:
        - `options = processor.inspect_read_options(Path("/tmp/data.csv"))`
        """
        if not self.check_file_validity(path):
            raise ValueError(f"File invalid or not found: {path}")

        encodings_to_try = encodings or DEFAULT_CSV_ENCODINGS
        delimiter = self.detect_delimiter(path, encodings_to_try)
        for encoding in encodings_to_try:
            try:
                normalized_encoding = self.normalize_duckdb_encoding_name(encoding)
                self._validate_duckdb_read(path, delimiter=delimiter, encoding=normalized_encoding)
                logger.info(
                    "CSV inspection succeeded for %s with delimiter '%s' and encoding '%s'",
                    path,
                    delimiter,
                    normalized_encoding,
                )
                return CsvReadOptions(delimiter=delimiter, encoding=normalized_encoding, header=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to inspect CSV %s with encoding '%s': %s", path, encoding, exc)

        raise ValueError(f"Failed to inspect CSV file '{path}' with delimiter '{delimiter}' and encodings {encodings_to_try}")

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Return lightweight CSV metadata without loading the full file in pandas.

        Why this exists:
        - Metadata extraction runs before the tabular output processor and
          should stay cheap even for very large CSV files.

        How to use:
        - Pass the CSV file path from the ingestion input stage.
        - The returned schema preview preserves the CSV header names.
        """
        options = self.inspect_read_options(file_path)
        connection = duckdb.connect(database=":memory:")
        try:
            # The table-function SQL below is built from locally escaped file
            # paths and CSV options, not from end-user SQL text.
            describe_query = f"DESCRIBE SELECT * FROM {self.build_duckdb_read_relation_sql(file_path, options)}"  # nosec B608
            rows = connection.execute(describe_query)
            columns = [str(row[0]) for row in rows.fetchall()]
        finally:
            connection.close()

        return {
            "suffix": "CSV",
            "num_columns": len(columns),
            "sample_columns": columns,
        }

    def convert_file_to_table(self, file_path: Path) -> pd.DataFrame:
        """
        Load one CSV into pandas for lightweight preview-only code paths.

        Why this exists:
        - The lightweight CSV-to-Markdown processor still expects a pandas
          DataFrame for truncation and `to_markdown(...)`.

        How to use:
        - Prefer `inspect_read_options(...)` for scalable tabular ingestion.
        - Use this method only when a pandas DataFrame is explicitly required.
        """
        options = self.inspect_read_options(file_path)
        return pd.read_csv(
            file_path,
            sep=options.delimiter,
            encoding=options.encoding,
            engine="python",
        )

    def write_table_preview(self, file_path: Path, output_dir: Path) -> Path:
        """
        Expose the CSV preview file with a link-first strategy.

        Why this exists:
        - Large CSV ingestion should avoid creating a second full local copy
          just to satisfy the `output/table.csv` preview contract.

        How to use:
        - Pass the original CSV path and the ingestion output directory.
        - The method creates `output/table.csv`, preferring a hard link and
          falling back to a regular copy when linking is not possible.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        table_path = output_dir / "table.csv"
        table_path.unlink(missing_ok=True)
        try:
            os.link(file_path, table_path)
        except OSError:
            shutil.copy2(file_path, table_path)
        return table_path

    def _validate_duckdb_read(self, path: Path, *, delimiter: str, encoding: str) -> None:
        """
        Probe one CSV/encoding pair with DuckDB.

        Why this exists:
        - The scalable tabular pipeline should fail fast on broken encodings
          before the output processor starts the CSV-to-Parquet conversion.

        How to use:
        - Call with one candidate delimiter/encoding pair.
        - The method returns `None` on success and raises on failure.
        """
        connection = duckdb.connect(database=":memory:")
        try:
            # The table-function SQL below is built from locally escaped file
            # paths and CSV options, not from end-user SQL text.
            probe_query = f"SELECT * FROM {self.build_duckdb_read_relation_sql(path, CsvReadOptions(delimiter=delimiter, encoding=encoding))} LIMIT 1"  # nosec B608
            connection.execute(probe_query)
        finally:
            connection.close()

    def build_duckdb_read_relation_sql(self, file_path: Path, options: CsvReadOptions) -> str:
        """
        Return the DuckDB table-function SQL used to read one CSV file.

        Why this exists:
        - DuckDB's SQL CSV reader supports the legacy encodings we need for
          ingestion more reliably than the higher-level Python relation helper.

        How to use:
        - Pass a validated CSV path and the output of `inspect_read_options(...)`.
        - Embed the returned SQL fragment in a `SELECT` or `COPY` statement.

        Example:
        - `sql = processor.build_duckdb_read_relation_sql(Path("/tmp/data.csv"), options)`
        """
        quoted_path = str(file_path).replace("'", "''")
        quoted_delimiter = options.delimiter.replace("'", "''")
        quoted_encoding = options.encoding.replace("'", "''")
        header_literal = "true" if options.header else "false"
        return f"read_csv_auto('{quoted_path}', delim='{quoted_delimiter}', header={header_literal}, encoding='{quoted_encoding}')"

    def normalize_duckdb_encoding_name(self, encoding: str) -> str:
        """
        Map user-facing encoding aliases to the DuckDB SQL names we execute.

        Why this exists:
        - The inspection helpers try common Python codec spellings, while
          DuckDB's SQL reader expects its own small set of encoding names.

        How to use:
        - Pass one candidate encoding before building a DuckDB CSV read query.

        Example:
        - `duckdb_encoding = processor.normalize_duckdb_encoding_name("latin1")`
        """
        normalized_encoding = encoding.strip().lower()
        encoding_aliases = {
            "utf8": "utf-8",
            "utf-8": "utf-8",
            "utf16": "utf-16",
            "utf-16": "utf-16",
            "latin1": "latin-1",
            "latin-1": "latin-1",
            "iso-8859-1": "latin-1",
        }
        return encoding_aliases.get(normalized_encoding, normalized_encoding)
