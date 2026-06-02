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
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import CsvReadOptions, CsvTabularProcessor
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor, TabularProcessingError
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularArtifactV1,
    build_tabular_object_key,
    compute_source_revision,
    duckdb_schema,
    utc_now_iso,
    write_tabular_artifact,
)
from knowledge_flow_backend.features.tabular.structures import TabularColumnSchema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedParquetMetadata:
    """
    Schema facts extracted from one generated Parquet artifact.

    Why this exists:
    - The tabular output processor writes Parquet first, then fills metadata
      from the artifact without materializing a pandas DataFrame.

    How to use:
    - Build it with `_write_csv_to_parquet(...)`.
    """

    row_count: int
    columns: list[TabularColumnSchema]


class TabularProcessor(BaseOutputProcessor):
    """
    Scalable tabular output processor backed by DuckDB CSV-to-Parquet conversion.

    Why this exists:
    - Large CSV ingestion should avoid loading the whole dataset into pandas
      before writing the queryable Parquet artifact.

    How to use:
    - Instantiate once from the output-processor registry.
    - Call `process(...)` with the CSV path produced by the input stage.
    """

    description = "Converts CSV outputs to document-scoped Parquet artifacts using DuckDB without loading them fully in pandas."

    def __init__(self):
        """
        Initialize the tabular processor for the active runtime mode.

        Why this exists:
        - Tabular ingestion needs the shared content store and tabular config in
          one place before converting CSV artifacts to Parquet.

        How to use:
        - Instantiate once from the output-processor registry.
        - Call `process(...)` with the extracted CSV file path and document metadata.
        """
        context = ApplicationContext.get_instance()
        self.content_store = context.get_content_store()
        self.tabular_config = context.get_config().storage.tabular_store
        self.csv_reader = CsvTabularProcessor()

        logger.info("Initializing TabularPipeline")

    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Convert one extracted CSV file into the active tabular backend.

        Why this exists:
        - Each tabular document must produce one document-scoped Parquet
          artifact in `content_storage`.

        How to use:
        - Pass the extracted CSV file path produced by the input stage.
        - The returned metadata marks `ProcessingStage.SQL_INDEXED` and
          `ProcessingStage.PREVIEW_READY` as done because the Parquet artifact
          can now serve tabular previews directly.
        - The method updates `metadata.extensions["tabular_v1"]`.
        """
        try:
            logger.info("Processing tabular file %s for document %s", file_path, metadata.document_uid)
            csv_path = Path(file_path)
            csv_read_options = self._inspect_csv_source(csv_path)
            artifact = self._persist_parquet_artifact(
                file_path=file_path,
                metadata=metadata,
                csv_read_options=csv_read_options,
            )
            metadata.file.row_count = artifact.row_count
            write_tabular_artifact(metadata, artifact)

            metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
            metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
            return metadata

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error during tabular processing")
            raise TabularProcessingError("Tabular processing failed") from exc

    def _inspect_csv_source(self, csv_path: Path) -> CsvReadOptions:
        """
        Inspect one CSV file before the DuckDB conversion starts.

        Why this exists:
        - The scalable tabular path should resolve delimiter and encoding once,
          then reuse those settings for the full CSV-to-Parquet conversion.

        How to use:
        - Pass the local CSV path produced by the input stage.
        """
        return self.csv_reader.inspect_read_options(csv_path)

    def _persist_parquet_artifact(
        self,
        *,
        file_path: str,
        metadata: DocumentMetadata,
        csv_read_options: CsvReadOptions,
    ) -> TabularArtifactV1:
        """
        Persist one CSV source as a versioned Parquet artifact in content storage.

        Why this exists:
        - The shared content store is the source of truth for queryable tabular
          datasets.

        How to use:
        - Call after CSV inspection has succeeded.
        - The method uploads the generated local Parquet file directly through
          `content_store.put_file(...)`.
        """
        source_revision = compute_source_revision(file_path, metadata)
        object_key = build_tabular_object_key(
            artifacts_prefix=self.tabular_config.artifacts_prefix,
            document_uid=metadata.document_uid,
            source_revision=source_revision,
        )

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            parquet_path = Path(tmp.name)

        try:
            generated_metadata = self._write_csv_to_parquet(
                csv_path=Path(file_path),
                csv_read_options=csv_read_options,
                parquet_path=parquet_path,
            )
            stored_object = self.content_store.put_file(
                object_key,
                parquet_path,
                content_type="application/vnd.apache.parquet",
            )
        finally:
            parquet_path.unlink(missing_ok=True)

        return TabularArtifactV1(
            dataset_uid=metadata.document_uid,
            object_key=stored_object.key,
            source_revision=source_revision,
            format=self.tabular_config.format,
            row_count=generated_metadata.row_count,
            columns=generated_metadata.columns,
            generated_at=utc_now_iso(),
            file_size_bytes=stored_object.size,
        )

    def _write_csv_to_parquet(
        self,
        *,
        csv_path: Path,
        csv_read_options: CsvReadOptions,
        parquet_path: Path,
    ) -> GeneratedParquetMetadata:
        """
        Convert one CSV file to Parquet with DuckDB only.

        Why this exists:
        - Large CSV datasets must be converted without loading the full file in
          pandas memory.

        How to use:
        - Pass the inspected CSV read options and the destination Parquet path.
        - The returned metadata is derived from the written Parquet artifact.
        """
        connection = duckdb.connect(database=":memory:")
        try:
            source_relation_sql = self.csv_reader.build_duckdb_read_relation_sql(
                csv_path,
                csv_read_options,
                sample_size=-1,
            )
            # The table-function SQL below comes from locally escaped CSV path
            # and encoding settings, not from end-user SQL text.
            source_query = f"SELECT * FROM {source_relation_sql}"  # nosec B608
            raw_relation = connection.sql(source_query)
            if not raw_relation.columns and csv_path.stat().st_size > 0:
                raise ValueError(f"Failed to parse tabular file: {csv_path}")

            raw_relation.create_view("source_csv_raw")
            column_projection = self._build_column_projection(raw_relation.columns)
            # The projection is built only from quoted identifiers derived from
            # discovered CSV headers.
            projection_query = f"CREATE OR REPLACE TEMP VIEW source_csv AS SELECT {column_projection} FROM source_csv_raw"  # nosec B608
            connection.execute(projection_query)

            quoted_path = str(parquet_path).replace("'", "''")
            compression = self.tabular_config.compression.replace("'", "''")
            connection.execute(f"COPY source_csv TO '{quoted_path}' (FORMAT PARQUET, COMPRESSION '{compression}')")

            row_count = self._read_parquet_row_count(connection, parquet_path)
            columns = self._read_parquet_schema(connection, parquet_path)
            return GeneratedParquetMetadata(row_count=row_count, columns=columns)
        finally:
            connection.close()

    def _build_column_projection(self, column_names: list[str]) -> str:
        """
        Return the sanitized SQL projection used before Parquet export.

        Why this exists:
        - CSV headers may contain spaces, punctuation, or duplicates that should
          become stable SQL-safe column names in the final Parquet dataset.

        How to use:
        - Pass the column names discovered by DuckDB after CSV inspection.
        """
        aliases = self._sanitize_output_column_names(column_names)
        projection_parts = [f"{self._quote_identifier(source_name)} AS {self._quote_identifier(alias)}" for source_name, alias in zip(column_names, aliases)]
        return ", ".join(projection_parts)

    def _sanitize_output_column_names(self, column_names: list[str]) -> list[str]:
        """
        Sanitize and deduplicate CSV column names for SQL exposure.

        Why this exists:
        - Large CSV ingestion still needs deterministic SQL-safe column names
          even though the conversion no longer passes through pandas.

        How to use:
        - Pass the column names exposed by DuckDB's CSV reader.
        """
        used_names: set[str] = set()
        sanitized_names: list[str] = []
        for index, column_name in enumerate(column_names, start=1):
            base_name = sanitize_sql_name(column_name) or f"column_{index}"
            candidate = base_name
            suffix = 2
            while candidate in used_names:
                candidate = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(candidate)
            sanitized_names.append(candidate)
        return sanitized_names

    def _read_parquet_row_count(self, connection: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
        """
        Return the row count stored in one generated Parquet artifact.

        Why this exists:
        - The scalable CSV-to-Parquet path should derive row counts from the
          final artifact instead of rescanning the source CSV in Python.

        How to use:
        - Pass the active DuckDB connection and the generated Parquet path.
        """
        quoted_path = str(parquet_path).replace("'", "''")
        # The Parquet path is a local temporary file path escaped for DuckDB
        # string literals.
        row_count_query = f"SELECT num_rows FROM parquet_file_metadata('{quoted_path}')"  # nosec B608
        row_count = connection.execute(row_count_query).fetchone()
        return int(row_count[0]) if row_count else 0

    def _read_parquet_schema(self, connection: duckdb.DuckDBPyConnection, parquet_path: Path) -> list[TabularColumnSchema]:
        """
        Return the ordered API schema stored in one generated Parquet artifact.

        Why this exists:
        - The scalable tabular pipeline should expose schema from the final
          artifact without materializing a pandas DataFrame.

        How to use:
        - Pass the active DuckDB connection and the generated Parquet path.
        """
        quoted_path = str(parquet_path).replace("'", "''")
        # The Parquet path is a local temporary file path escaped for DuckDB
        # string literals.
        schema_query = f"SELECT name, duckdb_type FROM parquet_schema('{quoted_path}') WHERE name != 'duckdb_schema'"  # nosec B608
        schema_rows = connection.execute(schema_query).fetchall()
        normalized_rows = [(str(column_name), str(dtype_name) if dtype_name is not None else None) for column_name, dtype_name in schema_rows]
        return duckdb_schema(normalized_rows)

    def _quote_identifier(self, name: str) -> str:
        """
        Quote one SQL identifier for DuckDB view generation.

        Why this exists:
        - The tabular processor generates SQL projections from CSV headers and
          must keep identifier escaping in one place.

        How to use:
        - Pass one column or alias name that should be used in SQL text.
        """
        return '"' + name.replace('"', '""') + '"'
