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
import re
import tempfile
from pathlib import Path

import dateparser
import duckdb
import pandas as pd
from pandas._libs.tslibs.nattype import NaTType

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import CsvTabularProcessor
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor, TabularProcessingError
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularArtifactV1,
    build_tabular_object_key,
    compute_source_revision,
    dataframe_schema,
    document_artifact_prefix,
    utc_now_iso,
    write_tabular_artifact,
)

logger = logging.getLogger(__name__)

_DATE_REGEX = re.compile(
    r"""(
        \b\d{1,2}/\d{1,2}/\d{4}\b |
        \b\d{1,2}/\d{1,2}/\d{2}\b |
        \b\d{1,2}-\d{1,2}-\d{4}\b |
        \b\d{1,2}-\d{1,2}-\d{2}\b |
        \b\d{1,2}\.\d{1,2}\.\d{4}\b |
        \b\d{1,2}\.\d{1,2}\.\d{2}\b |
        \b\d{4}-\d{1,2}-\d{1,2}\b |
        \b\d{4}/\d{1,2}/\d{1,2}\b |
        \b\d{4}\.\d{1,2}\.\d{1,2}\b |

        \b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{2,4}\b |  # 1 Jan 2023
        \b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{1,2},?\s*\d{2,4}\b | # Jan 1, 2023

         \b\d{1,2}\s*(jan|fév|mar|avr|mai|jun|juin|juil|jui|aoû|sep|sept|oct|nov|déc)\s*\d{2,4}\b |  # 1 Fév 2023
        \b(jan|fév|mar|avr|mai|jun|juin|juil|jui|aoû|sep|sept|oct|nov|déc)\s*\d{1,2},?\s*\d{2,4}\b | # Fév 1, 2023

        \b\d{1,2}\s*(january|february|march|april|may|june|july|august|
                    september|october|november|december)\s*\d{2,4}\b |             # 1 January 2023
        \b(january|february|march|april|may|june|july|august|
            september|october|november|december)\s+\d{1,2},?\s*\d{2,4}\b |         # January 1, 2023

        \b\d{1,2}\s*(janvier|février|mars|avril|mai|juin|juillet|août|
                     septembre|octobre|novembre|décembre)\s*\d{2,4}\b |            # 1 septembre 2023
        \b(janvier|février|mars|avril|mai|juin|juillet|août|
            septembre|octobre|novembre|décembre)\s+\d{1,2},?\s*\d{2,4}\b           # septembre 1, 2023
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _looks_like_date(value: str) -> bool:
    """Check if the string matches a common date format (with separators or month names)."""
    return bool(_DATE_REGEX.search(value))


def _looks_like_compact_date(value: str) -> bool:
    """Check for compact date strings like YYYYMM or YYYYMMDD."""
    if not re.fullmatch(r"\d{6,8}", value):
        return False
    try:
        month = int(value[4:6])
        if not (1 <= month <= 12):
            return False
        if len(value) == 8:
            day = int(value[6:8])
            return 1 <= day <= 31
        return True
    except ValueError:
        return False


def _parse_date(value: str) -> pd.Timestamp | NaTType:
    """Attempt to parse a string into a pandas Timestamp using dateparser."""
    if not isinstance(value, str) or not any(c.isdigit() for c in value):
        return pd.NaT

    dt = dateparser.parse(value, settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False})

    if dt is None:
        return pd.NaT

    try:
        ts = pd.to_datetime(dt, errors="raise")
        return ts if ts.year >= 0 else pd.NaT
    except (ValueError, OverflowError):
        return pd.NaT


def is_valid_date(series: pd.Series, threshold: float = 0.7) -> bool:
    """
    Determine if a series contains mostly valid dates (above the given threshold).
    Uses both format heuristics and actual parsing.
    """
    values = series.dropna().astype(str)
    if values.empty:
        return False

    def is_parsable(value: str) -> bool:
        return (_looks_like_date(value) or _looks_like_compact_date(value)) and not bool(pd.isna(_parse_date(value)))

    valid_count = sum(is_parsable(val) for val in values)
    return (valid_count / len(values)) >= threshold


class TabularProcessor(BaseOutputProcessor):
    """
    A pipeline for processing tabular data.
    """

    description = "Loads tabular outputs, cleans column names, detects dates, and persists document-scoped Parquet artifacts in the shared content store."

    def __init__(self):
        """
        Initialize the tabular processor for the active runtime mode.

        Why this exists:
        - Tabular ingestion now has one single supported runtime backed by
          Parquet artifacts in the shared content store.
        - The processor should resolve the shared stores once, then keep the
          ingestion path identical for callers.

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
        Convert one extracted tabular file into the active tabular backend.

        Why this exists:
        - Each tabular document must produce one document-scoped Parquet
          artifact in `content_storage`.

        How to use:
        - Pass the extracted CSV file path produced by the tabular input stage.
        - The returned metadata always marks `ProcessingStage.SQL_INDEXED` as
          done and updates `metadata.extensions["tabular_v1"]`.
        """

        try:
            logger.info(f"Processing file: {file_path} with metadata: {metadata}")
            df = self._load_dataframe(file_path)
            df.columns = [sanitize_sql_name(col) for col in df.columns]

            for col in df.select_dtypes(include=["object"]).columns:
                sample = pd.Series(df[col].dropna().astype(str).head(20))
                if not sample.empty and is_valid_date(sample, threshold=0.7):
                    logger.info(f"🕒 Parsing column '{col}' as datetime")
                    df[col] = df[col].astype(str).map(_parse_date)

            metadata.file.row_count = int(len(df))
            artifact = self._persist_parquet_artifact(file_path=file_path, metadata=metadata, df=df)
            write_tabular_artifact(metadata, artifact)
            self._cleanup_previous_artifacts(metadata=metadata, keep_key=artifact.object_key)

            metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
            return metadata

        except Exception as e:
            logger.exception("Unexpected error during tabular processing")
            raise TabularProcessingError("Tabular processing failed") from e

    def _load_dataframe(self, file_path: str) -> pd.DataFrame:
        """
        Load one extracted CSV file with the existing tolerant CSV reader.

        Why this exists:
        - The input pipeline already handles delimiter and encoding drift for
          CSV files, and the Parquet refactor should keep that behavior.

        How to use:
        - Pass the extracted local file path produced by the tabular input
          processor.
        """

        df = self.csv_reader.read_csv_flexible(Path(file_path))
        if df.empty and len(df.columns) == 0 and Path(file_path).stat().st_size > 0:
            raise ValueError(f"Failed to parse tabular file: {file_path}")
        return df

    def _persist_parquet_artifact(self, *, file_path: str, metadata: DocumentMetadata, df: pd.DataFrame) -> TabularArtifactV1:
        """
        Persist one DataFrame as a versioned Parquet artifact in content storage.

        Why this exists:
        - The shared content store is the new source of truth for queryable
          datasets.

        How to use:
        - Call after the DataFrame has been cleaned and schema-normalized.
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
            self._write_dataframe_to_parquet(df=df, parquet_path=parquet_path)
            with parquet_path.open("rb") as stream:
                stored_object = self.content_store.put_object(
                    object_key,
                    stream,
                    content_type="application/vnd.apache.parquet",
                )
        finally:
            parquet_path.unlink(missing_ok=True)

        return TabularArtifactV1(
            dataset_uid=metadata.document_uid,
            object_key=stored_object.key,
            source_revision=source_revision,
            format=self.tabular_config.format,
            row_count=int(len(df)),
            columns=dataframe_schema(df),
            generated_at=utc_now_iso(),
            file_size_bytes=stored_object.size,
        )

    def _write_dataframe_to_parquet(self, *, df: pd.DataFrame, parquet_path: Path) -> None:
        """
        Write one DataFrame to Parquet using DuckDB.

        Why this exists:
        - The project already ships DuckDB, which can produce Parquet without
          adding a separate `pyarrow` dependency to the default offline flow.

        How to use:
        - Provide the cleaned DataFrame and the temporary target file path.
        """

        connection = duckdb.connect(database=":memory:")
        try:
            connection.register("dataset_df", df)
            quoted_path = str(parquet_path).replace("'", "''")
            compression = self.tabular_config.compression.replace("'", "''")
            connection.execute(f"COPY dataset_df TO '{quoted_path}' (FORMAT PARQUET, COMPRESSION '{compression}')")
        finally:
            connection.close()

    def _cleanup_previous_artifacts(self, *, metadata: DocumentMetadata, keep_key: str) -> None:
        """
        Remove stale Parquet revisions for the current document on re-ingestion.

        Why this exists:
        - The metadata should point to exactly one active dataset artifact.
        - Old revisions are no longer needed once the new artifact is available.

        How to use:
        - Call after the new artifact has been written successfully.
        - Cleanup is best-effort and never blocks ingestion success.
        """

        if self.tabular_config is None:
            return

        prefix = document_artifact_prefix(
            artifacts_prefix=self.tabular_config.artifacts_prefix,
            document_uid=metadata.document_uid,
        )

        try:
            for stored_object in self.content_store.list_objects(prefix):
                if stored_object.key != keep_key:
                    self.content_store.delete_object(stored_object.key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to cleanup stale tabular artifacts for %s: %s", metadata.document_uid, exc)
