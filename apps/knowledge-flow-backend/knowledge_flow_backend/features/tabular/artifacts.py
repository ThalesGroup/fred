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
from pydantic import BaseModel, Field

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.features.tabular.structures import DTypes, TabularColumnSchema

logger = logging.getLogger(__name__)

TABULAR_EXTENSION_KEY = "tabular_v1"


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
    doc_prefix = sanitize_sql_name(document_uid.replace("-", "_"))[:12] or "doc"
    return f"d_{doc_prefix}_{stem}"


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
