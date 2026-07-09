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

import codecs
import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseTabularProcessor

logger = logging.getLogger(__name__)

DEFAULT_CSV_ENCODINGS = ["utf-8", "cp1252", "windows-1252", "latin1", "iso-8859-1"]

# Encoding is decided from a bounded head sample so inspection stays cheap on
# very large CSV files. 1 MiB comfortably covers even wide, multi-hundred-column
# exports (e.g. Jira) whose header line alone can be several kilobytes.
_ENCODING_DETECTION_SAMPLE_BYTES = 1 << 20


@dataclass(frozen=True)
class CsvReadOptions:
    """
    Minimal CSV read settings reused across lightweight and tabular flows.

    Why this exists:
    - Large CSV processing should discover delimiter and encoding once, then
      feed those settings to DuckDB-backed readers without reimplementing
      detection.

    How to use:
    - Build it with `CsvTabularProcessor.inspect_read_options(...)`.
    - Reuse the returned values when opening the CSV through DuckDB.

    Example:
    - `options = processor.inspect_read_options(Path("/tmp/data.csv"))`
    """

    delimiter: str
    encoding: str
    header: bool = True
    source_path: Path | None = None


class CsvTabularProcessor(BaseTabularProcessor):
    """
    CSV input processor for Parquet-backed tabular ingestion.

    Why this exists:
    - The tabular ingestion flow needs cheap CSV inspection before the output
      processor converts the source file to Parquet.
    - Lightweight Markdown previews should reuse the same DuckDB-readable
      source relation instead of building a separate pandas-based flow.

    How to use:
    - Use `inspect_read_options(...)` and `build_duckdb_read_relation_sql(...)`
      for the scalable tabular flow.
    - Use `render_markdown_preview(...)` when one bounded Markdown table is
      needed from the same CSV source.
    """

    description = "Parses CSV files, detects delimiters/encodings, and exposes scalable read settings."

    def transcode_csv_to_utf8(self, path: Path, source_encoding: str) -> Path:
        """
        Create a UTF-8 copy of a CSV file when DuckDB cannot read the source
        encoding directly.

        Why this exists:
        - Some Excel/Windows exports are cp1252/windows-1252 encoded.
        - DuckDB may reject those encodings depending on the installed version.
        - The ingestion pipeline can still process the file safely once it has
          been converted to UTF-8.
        """
        utf8_path = path.with_suffix(path.suffix + ".utf8")

        with open(path, "r", encoding=source_encoding, errors="strict", newline="") as source_file:
            content = source_file.read()

        with open(utf8_path, "w", encoding="utf-8", newline="") as utf8_file:
            utf8_file.write(content)

        return utf8_path

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

    def detect_source_encoding(self, path: Path, encodings: list[str]) -> str:
        """
        Return the first candidate encoding that decodes the file head cleanly.

        Why this exists:
        - Encoding detection and CSV-dialect detection are independent problems.
          Deciding the encoding with a strict Python decode keeps DuckDB's
          tolerant reader (`ignore_errors`, see `build_duckdb_read_relation_sql`)
          from silently masking a wrong-encoding choice as empty rows.

        How to use:
        - Pass the candidate encodings in priority order (UTF-8 first).
        - `latin1`/`iso-8859-1` decode any byte, so the last candidate always
          matches; the returned name is the raw candidate, not the DuckDB alias.
        """
        with open(path, "rb") as file_handle:
            sample = file_handle.read(_ENCODING_DETECTION_SAMPLE_BYTES)

        for encoding in encodings:
            try:
                # final=False tolerates a multi-byte character cut at the sample boundary.
                codecs.getincrementaldecoder(encoding)().decode(sample, final=False)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue
        return encodings[-1]

    def inspect_read_options(self, path: Path, encodings: list[str] | None = None) -> CsvReadOptions:
        """
        Return the delimiter and encoding that DuckDB can use for one CSV file.

        Why this exists:
        - The scalable tabular pipeline should inspect CSV settings once and
          then reuse them for metadata extraction, preview generation, and
          Parquet conversion.
        - Some CSV files come from Windows/Excel exports and use cp1252. DuckDB
          reads the common legacy encodings directly; when the installed build
          rejects one, the file is transcoded to UTF-8 once and the transcoded
          path is stored in the returned options.

        How to use:
        - Pass the CSV path and optional candidate encodings.
        - Raises `ValueError` when the file is missing/invalid.
        """
        if not self.check_file_validity(path):
            raise ValueError(f"File invalid or not found: {path}")

        encodings_to_try = encodings or DEFAULT_CSV_ENCODINGS
        source_encoding = self.detect_source_encoding(path, encodings_to_try)
        delimiter = self.detect_delimiter(path, [source_encoding])
        duckdb_encoding = self.normalize_duckdb_encoding_name(source_encoding)

        try:
            self._validate_duckdb_read(path, delimiter=delimiter, encoding=duckdb_encoding)
            logger.info(
                "CSV inspection succeeded for %s (delimiter '%s', encoding '%s')",
                path,
                delimiter,
                duckdb_encoding,
            )
            return CsvReadOptions(delimiter=delimiter, encoding=duckdb_encoding, header=True)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DuckDB could not read %s with encoding '%s' (%s) — transcoding to UTF-8",
                path,
                duckdb_encoding,
                exc,
            )
            utf8_path = self.transcode_csv_to_utf8(path, source_encoding)
            self._validate_duckdb_read(utf8_path, delimiter=delimiter, encoding="utf-8")
            return CsvReadOptions(delimiter=delimiter, encoding="utf-8", header=True, source_path=utf8_path)

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

    def build_duckdb_source_relation_sql(self, file_path: Path, *, sample_size: int | None = None) -> str:
        """
        Return the DuckDB relation SQL for one CSV file.

        Why this exists:
        - The tabular input processor and lightweight Markdown preview should
          share the same DuckDB CSV reader contract as the Parquet output
          processor.

        How to use:
        - Pass the CSV file path and optional `sample_size`.
        - The method inspects delimiter/encoding once and returns a relation
          SQL fragment suitable for `SELECT * FROM ...`.

        Example:
        - `sql = processor.build_duckdb_source_relation_sql(Path("/tmp/data.csv"), sample_size=-1)`
        """
        options = self.inspect_read_options(file_path)
        return self.build_duckdb_read_relation_sql(
            file_path,
            options,
            sample_size=sample_size,
        )

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

    def build_duckdb_read_relation_sql(
        self,
        file_path: Path,
        options: CsvReadOptions,
        *,
        sample_size: int | None = None,
    ) -> str:
        """
        Return the DuckDB table-function SQL used to read one CSV file.

        Why this exists:
        - DuckDB's SQL CSV reader supports the legacy encodings we need for
          ingestion more reliably than the higher-level Python relation helper.
        - When the source CSV had to be transcoded to UTF-8, the transcoded path
          from CsvReadOptions is used transparently.
        - `ignore_errors=true` keeps real-world exports (e.g. Jira dumps with
          multi-line quoted fields and a stray malformed trailing line) from
          aborting the whole ingestion: DuckDB's strict sniffer rejects such
          files outright, whereas here we skip only the offending rows. The
          encoding is validated separately in `detect_source_encoding`, so this
          tolerance cannot silently swallow a wrong-encoding read.
        """
        effective_path = options.source_path or file_path

        quoted_path = str(effective_path).replace("'", "''")
        quoted_delimiter = options.delimiter.replace("'", "''")
        quoted_encoding = options.encoding.replace("'", "''")
        header_literal = "true" if options.header else "false"
        sample_size_sql = f", sample_size={sample_size}" if sample_size is not None else ""

        return f"read_csv_auto('{quoted_path}', delim='{quoted_delimiter}', header={header_literal}, encoding='{quoted_encoding}', ignore_errors=true{sample_size_sql})"

    def normalize_duckdb_encoding_name(self, encoding: str) -> str:
        """
        Map user-facing encoding aliases to the DuckDB SQL names we execute.
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
            "cp1252": "CP1252",
            "windows-1252": "CP1252",
        }
        return encoding_aliases.get(normalized_encoding, normalized_encoding)
