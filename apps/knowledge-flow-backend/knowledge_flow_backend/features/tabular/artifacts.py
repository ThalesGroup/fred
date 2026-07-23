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

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fred_core.documents.document_structures import DocumentMetadata
from pydantic import BaseModel, Field

from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.features.tabular.structures import DTypes, TabularColumnSchema

logger = logging.getLogger(__name__)

TABULAR_EXTENSION_KEY = "tabular_v1"
TABULAR_MULTI_EXTENSION_KEY = "tabular_multi_v1"


class TabularArtifactV1(BaseModel):
    """
    Dataset-scoped Parquet artifact metadata stored in `DocumentMetadata.extensions`.

    Why this exists:
    - SQL access now targets per-document Parquet artifacts instead of global
      SQL tables.
    - Keeping one typed payload in metadata makes authorization and querying
      deterministic for every document.

    How to use:
    - Persist one instance under `metadata.extensions["tabular_v1"]`.
    - Rehydrate it with `read_tabular_artifact(...)` before listing or querying.

    Example:
    ```python
    artifact = TabularArtifactV1(
        dataset_uid="doc-123",
        object_key="tabular/datasets/doc-123/rev/data.parquet",
        source_revision="rev",
        format="parquet",
        row_count=10,
        columns=[TabularColumnSchema(name="city", dtype="string")],
        generated_at="2026-04-07T12:00:00+00:00",
        file_size_bytes=1024,
    )
    ```
    """

    dataset_uid: str
    object_key: str
    source_revision: str
    format: str = "parquet"
    row_count: int = Field(default=0, ge=0)
    columns: list[TabularColumnSchema] = Field(default_factory=list)
    generated_at: str
    file_size_bytes: int = Field(default=0, ge=0)


class TabularTableArtifactV1(TabularArtifactV1):
    """
    One table extracted from a multi-table document (e.g. an Excel workbook).

    Why this exists:
    - Spreadsheet ingestion produces several Parquet artifacts per document,
      one per detected table, each with its own SQL alias and provenance.
    - Reusing the `TabularArtifactV1` base keeps the tabular runtime (DuckDB
      mounting, schema exposure) working unchanged on each table.

    How to use:
    - Store a list of these under `metadata.extensions["tabular_multi_v1"]`
      through `TabularMultiArtifactV1`.
    - `query_alias` is the exact SQL relation name exposed to agents; it must
      match the alias printed in the document's `output.md` catalog.
    """

    query_alias: str
    sheet: str
    table_id: str
    title: str | None = None
    range: str | None = None
    data_range: str | None = None


class TabularMultiArtifactV1(BaseModel):
    """
    Multi-table dataset payload stored in `DocumentMetadata.extensions`.

    Why this exists:
    - One spreadsheet document maps to N queryable tables; authorization stays
      document-level while SQL exposure is table-level.

    How to use:
    - Persist one instance under `metadata.extensions["tabular_multi_v1"]`.
    - Rehydrate it with `read_tabular_multi_artifact(...)` before listing or
      querying.
    """

    tables: list[TabularTableArtifactV1] = Field(default_factory=list)


def read_tabular_artifact(metadata: DocumentMetadata) -> TabularArtifactV1 | None:
    """
    Return the typed tabular artifact payload stored on one document.

    Why this exists:
    - Metadata extensions are stored as raw dictionaries.
    - Query/list services need one typed view to avoid repeated defensive
      casting logic.

    How to use:
    - Call this before exposing one dataset in the API or mounting it in DuckDB.
    - Returns `None` when the document has no tabular artifact.

    Example:
    ```python
    artifact = read_tabular_artifact(metadata)
    if artifact:
        print(artifact.object_key)
    ```
    """

    raw_extensions = metadata.extensions or {}
    raw_artifact = raw_extensions.get(TABULAR_EXTENSION_KEY)
    if raw_artifact is None:
        return None

    try:
        return TabularArtifactV1.model_validate(raw_artifact)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid %s payload on document %s: %s", TABULAR_EXTENSION_KEY, metadata.document_uid, exc)
        return None


def write_tabular_artifact(metadata: DocumentMetadata, artifact: TabularArtifactV1) -> None:
    """
    Persist one typed tabular artifact payload back into document metadata.

    Why this exists:
    - Ingestion must update the dataset descriptor in one consistent place.
    - Call sites should not have to care about extension dict initialization.

    How to use:
    - Build a `TabularArtifactV1`.
    - Pass the current document metadata to update `extensions["tabular_v1"]`.

    Example:
    ```python
    write_tabular_artifact(metadata, artifact)
    ```
    """

    if metadata.extensions is None:
        metadata.extensions = {}
    metadata.extensions[TABULAR_EXTENSION_KEY] = artifact.model_dump(mode="json")


def read_tabular_multi_artifact(metadata: DocumentMetadata) -> TabularMultiArtifactV1 | None:
    """
    Return the typed multi-table payload stored on one document.

    Why this exists:
    - Spreadsheet documents register several tables under one extension key;
      the tabular service needs one typed view to expand them into datasets.

    How to use:
    - Call alongside `read_tabular_artifact(...)` when resolving datasets.
    - Returns `None` when the document carries no multi-table artifact.

    Example:
    ```python
    multi = read_tabular_multi_artifact(metadata)
    if multi:
        print([table.query_alias for table in multi.tables])
    ```
    """

    raw_extensions = metadata.extensions or {}
    raw_artifact = raw_extensions.get(TABULAR_MULTI_EXTENSION_KEY)
    if raw_artifact is None:
        return None

    try:
        return TabularMultiArtifactV1.model_validate(raw_artifact)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid %s payload on document %s: %s", TABULAR_MULTI_EXTENSION_KEY, metadata.document_uid, exc)
        return None


def write_tabular_multi_artifact(metadata: DocumentMetadata, artifact: TabularMultiArtifactV1) -> None:
    """
    Persist one typed multi-table payload back into document metadata.

    Why this exists:
    - The spreadsheet output stage must promote the input-stage sidecar into
      one consistent extension entry.

    How to use:
    - Build a `TabularMultiArtifactV1` and pass the current document metadata
      to update `extensions["tabular_multi_v1"]`.

    Example:
    ```python
    write_tabular_multi_artifact(metadata, TabularMultiArtifactV1(tables=tables))
    ```
    """

    if metadata.extensions is None:
        metadata.extensions = {}
    metadata.extensions[TABULAR_MULTI_EXTENSION_KEY] = artifact.model_dump(mode="json")


def dataframe_dtype_to_literal(dtype: Any) -> DTypes:
    """
    Map one pandas dtype to the tabular API literal used across Fred.

    Why this exists:
    - The API and metadata store should expose one stable, UI-friendly dtype
      vocabulary regardless of pandas internals.

    How to use:
    - Call this for each DataFrame column when building schema metadata.

    Example:
    ```python
    dtype_name = dataframe_dtype_to_literal(df["amount"].dtype)
    ```
    """

    series_dtype = pd.api.types.pandas_dtype(dtype)
    if pd.api.types.is_bool_dtype(series_dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(series_dtype):
        return "integer"
    if pd.api.types.is_float_dtype(series_dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series_dtype):
        return "datetime"
    if pd.api.types.is_string_dtype(series_dtype) or pd.api.types.is_object_dtype(series_dtype):
        return "string"
    return "unknown"


def dataframe_schema(df: pd.DataFrame) -> list[TabularColumnSchema]:
    """
    Build the ordered API schema for one DataFrame.

    Why this exists:
    - The ingestion path and the dataset listing endpoint must expose the same
      ordered schema without duplicating mapping logic.

    How to use:
    - Pass the cleaned DataFrame right before writing the Parquet artifact.

    Example:
    ```python
    columns = dataframe_schema(df)
    ```
    """

    return [TabularColumnSchema(name=str(column_name), dtype=dataframe_dtype_to_literal(df[column_name].dtype)) for column_name in df.columns]


def duckdb_dtype_to_literal(dtype_name: str | None) -> DTypes:
    """
    Map one DuckDB type name to the tabular API literal used across Fred.

    Why this exists:
    - The scalable CSV-to-Parquet pipeline now discovers schema from DuckDB and
      Parquet metadata instead of pandas DataFrames.

    How to use:
    - Pass the `duckdb_type` string returned by DuckDB schema inspection.

    Example:
    - `dtype = duckdb_dtype_to_literal("TIMESTAMP")`
    """
    normalized = (dtype_name or "").upper()
    if normalized in {"BOOLEAN"}:
        return "boolean"
    if normalized in {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
    }:
        return "integer"
    if normalized in {"FLOAT", "DOUBLE", "DECIMAL", "REAL"}:
        return "float"
    if normalized in {"DATE", "TIMESTAMP", "TIMESTAMP_MS", "TIMESTAMP_NS", "TIMESTAMP_S", "TIMESTAMP WITH TIME ZONE", "TIME"}:
        return "datetime"
    if normalized in {"VARCHAR", "BLOB", "UUID"}:
        return "string"
    return "unknown"


def duckdb_schema(column_types: list[tuple[str, str | None]]) -> list[TabularColumnSchema]:
    """
    Build the ordered tabular API schema from DuckDB column metadata.

    Why this exists:
    - The scalable tabular ingestion path now inspects schema after writing the
      Parquet artifact, without materializing a pandas DataFrame.

    How to use:
    - Pass `(column_name, duckdb_type)` pairs returned by DuckDB.

    Example:
    - `columns = duckdb_schema([("city", "VARCHAR"), ("amount", "BIGINT")])`
    """
    return [TabularColumnSchema(name=column_name, dtype=duckdb_dtype_to_literal(dtype_name)) for column_name, dtype_name in column_types]


def build_tabular_object_key(*, artifacts_prefix: str, document_uid: str, source_revision: str) -> str:
    """
    Return the canonical Parquet object key for one dataset revision.

    Why this exists:
    - Every deployment must write tabular artifacts under the same object-store
      layout to keep cleanup and lookup predictable.

    How to use:
    - Pass the configured prefix, document uid, and source revision from the
      ingestion pipeline.

    Example:
    ```python
    key = build_tabular_object_key(
        artifacts_prefix="tabular/datasets",
        document_uid="doc-123",
        source_revision="rev-1",
    )
    ```
    """

    clean_prefix = artifacts_prefix.strip("/").rstrip("/")
    return f"{clean_prefix}/{document_uid}/{source_revision}/data.parquet"


def build_tabular_table_object_key(*, artifacts_prefix: str, document_uid: str, source_revision: str, table_file_name: str) -> str:
    """
    Return the canonical Parquet object key for one table of a multi-table document.

    Why this exists:
    - Spreadsheet ingestion writes one Parquet artifact per detected table; all
      of them must live under the same per-document prefix as single-table
      datasets so `document_artifact_prefix(...)`-based cleanup keeps working.

    How to use:
    - Pass the configured prefix, document uid, source revision, and a
      filesystem-safe table file name (e.g. `Sheet1.t1.parquet`).

    Example:
    ```python
    key = build_tabular_table_object_key(
        artifacts_prefix="tabular/datasets",
        document_uid="doc-123",
        source_revision="rev-1",
        table_file_name="Sales.t1.parquet",
    )
    ```
    """

    clean_prefix = artifacts_prefix.strip("/").rstrip("/")
    return f"{clean_prefix}/{document_uid}/{source_revision}/{table_file_name}"


def document_artifact_prefix(*, artifacts_prefix: str, document_uid: str) -> str:
    """
    Return the object-store prefix holding every revision for one document dataset.

    Why this exists:
    - Re-ingestion needs one stable prefix to prune stale revisions safely.

    How to use:
    - Call it before `list_objects(...)` to find every artifact revision for one
      document.
    """

    clean_prefix = artifacts_prefix.strip("/").rstrip("/")
    return f"{clean_prefix}/{document_uid}/"


def compute_source_revision(file_path: str, metadata: DocumentMetadata) -> str:
    """
    Compute the dataset revision identifier used in object keys.

    Why this exists:
    - Re-ingestion must produce a new deterministic artifact location.
    - Reusing the document SHA when available avoids unnecessary re-hashing.

    How to use:
    - Call it once during tabular ingestion before writing the Parquet file.

    Example:
    ```python
    revision = compute_source_revision("/tmp/data.csv", metadata)
    ```
    """

    if metadata.file.sha256:
        return metadata.file.sha256

    hasher = hashlib.sha256()
    with Path(file_path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _query_alias_doc_prefix(document_uid: str) -> str:
    """Return the sanitized 12-character document prefix shared by every alias scheme."""

    return sanitize_sql_name(document_uid.replace("-", "_"))[:12] or "doc"


def build_default_query_alias(document_uid: str, document_name: str) -> str:
    """
    Build the default SQL alias exposed for one authorized dataset.

    Why this exists:
    - Query aliases must be stable enough for prompts and API clients while
      remaining safe as DuckDB relation names.

    How to use:
    - Use the returned alias as the preferred relation name.
    - If several aliases collide, suffix them in the caller.

    Example:
    ```python
    alias = build_default_query_alias("12345678-1234", "Sales Export.csv")
    ```
    """

    stem = sanitize_sql_name(Path(document_name).stem) or "dataset"
    return f"d_{_query_alias_doc_prefix(document_uid)}_{stem}"


def build_table_query_alias(document_uid: str, sheet_name: str, table_index: int) -> str:
    """
    Build the deterministic SQL alias for one table of a multi-table document.

    Why this exists:
    - The alias printed in the spreadsheet `output.md` catalog must be exactly
      the relation name later mounted by the tabular service, otherwise agent
      SQL is rejected by `validate_read_query`. One shared helper removes any
      chance of drift between the writer and the resolver.
    - Sheet-only aliases would collide when a sheet holds several tables, so
      the per-sheet table index is part of the name.

    How to use:
    - Call with the document uid, the source sheet name, and the 1-based table
      index within that sheet (the `N` of the extractor's `<sheet>.tN` id).
    - Deduplicate within one document in the caller if two sheet names
      sanitize to the same token.

    Example:
    ```python
    alias = build_table_query_alias("12345678-1234", "Ventes 2026", 1)
    # -> "d_12345678_123_ventes_2026_t1"
    ```
    """

    sheet = sanitize_sql_name(sheet_name) or "sheet"
    return f"d_{_query_alias_doc_prefix(document_uid)}_{sheet}_t{table_index}"


def utc_now_iso() -> str:
    """
    Return the current UTC timestamp as an ISO 8601 string.

    Why this exists:
    - Artifact metadata stores one transport-friendly timestamp string in the
      document extension payload.

    How to use:
    - Call during artifact creation for `generated_at`.
    """

    return datetime.now(timezone.utc).isoformat()
