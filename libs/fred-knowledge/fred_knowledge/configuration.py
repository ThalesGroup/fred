# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OpenSearchVectorIndexConfig(BaseModel):
    type: Literal["opensearch"]
    index: str = Field(..., description="OpenSearch index name")
    bulk_size: int = Field(default=1000, description="Number of documents to send in each bulk insert request")


class PgVectorStorageConfig(BaseModel):
    """
    PostgreSQL + pgvector backend.
    - Uses shared `storage.postgres` connection settings.
    - Stores vectors in the default pgvector table under a collection name.
    """

    type: Literal["pgvector"]
    collection_name: str = Field("fred_chunks", description="Logical collection name")


VectorStorageConfig = Annotated[
    Union[
        OpenSearchVectorIndexConfig,
        PgVectorStorageConfig,
    ],
    Field(discriminator="type"),
]


class ArtifactStorageConfig(BaseModel):
    """S3 connection for generation artifacts, independent of worker settings."""

    model_config = ConfigDict(extra="forbid")
    endpoint: str
    bucket: str
    region: str = "us-east-1"
    access_key_env: str
    secret_key_env: str
    allow_insecure: bool = False

    @model_validator(mode="after")
    def validate_endpoint(self):
        if not self.endpoint.startswith("https://") and not (self.allow_insecure and self.endpoint.startswith("http://")):
            raise ValueError("artifact storage endpoint requires HTTPS")
        return self


class TabularQueryConfig(BaseModel):
    """
    Runtime settings for dataset-centric SQL queries.

    Why this exists:
    - Tabular querying now runs on transient Parquet datasets rather than
      long-lived SQL tables.
    - These values keep query execution bounded and configurable from YAML.

    How to use:
    - Keep the default `duckdb` engine.
    - Tune result limits and backend-internal presigned URL TTL per deployment.
    """

    engine: Literal["duckdb"] = Field(
        default="duckdb",
        description="Embedded query engine used to read Parquet datasets.",
    )
    access_mode: Literal["presigned_url"] = Field(
        default="presigned_url",
        description="Primary object-access method for remote tabular artifacts.",
    )
    internal_presigned_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        description="TTL in seconds for backend-internal object-storage URLs used by tabular DuckDB reads.",
    )
    default_max_rows: int = Field(
        default=200,
        ge=1,
        description="Default preview row limit applied when callers omit max_rows.",
    )
    max_rows: int = Field(
        default=1000,
        ge=1,
        description="Hard cap applied to query result previews. Bounds the rows returned, not the work done to produce them: use the execution guardrails below for that.",
    )
    max_concurrent_queries: int = Field(
        default=2,
        ge=1,
        description="Maximum DuckDB jobs running at once in this process. Sizes the dedicated thread pool, so it also bounds worst-case DuckDB memory together with duckdb_memory_limit.",
    )
    max_queued_queries: int = Field(
        default=4,
        ge=0,
        description="Extra jobs allowed to wait for a free slot before new requests are rejected with 503. Absorbs bursts without letting the queue grow without bound.",
    )
    query_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Wall-clock budget for one DuckDB job before it is aborted and the caller receives 504. Abort is best-effort for work blocked on network I/O.",
    )
    duckdb_threads: int = Field(
        default=1,
        ge=1,
        description="Threads DuckDB may use per connection. Set explicitly because DuckDB otherwise auto-detects the host's CPUs and ignores the container's CPU limit.",
    )
    duckdb_memory_limit: str = Field(
        default="256MB",
        pattern=r"(?i)^\d+(\.\d+)?\s*(B|[KMGT]B|[KMGT]iB)$",
        description="Buffer-manager budget per DuckDB connection, e.g. '256MB'. Validated at startup so a typo fails fast instead of at the first query.",
    )
    max_selected_datasets: int = Field(
        default=50,
        ge=1,
        description="Maximum datasets one request may mount or scan. Backstop for searches and for queries whose referenced-relation set is still too large.",
    )


class TabularStoreConfig(BaseModel):
    """
    Dataset-centric tabular storage settings for the supported tabular runtime.

    Why this exists:
    - CSV ingestion persists one Parquet artifact per document in the shared
      content store.
    - One dedicated config block keeps object keys and query limits explicit.

    How to use:
    - Configure the block directly under `storage.tabular_store`.
    - `artifacts_prefix` namespaces Parquet datasets under the shared
      content-store object area.
    - `format` is intentionally fixed to `parquet`.
    """

    artifacts_prefix: str = Field(
        default="tabular/datasets",
        description="Logical prefix for tabular dataset keys within a processing attempt.",
    )
    format: Literal["parquet"] = Field(
        default="parquet",
        description="Physical storage format used for tabular artifacts.",
    )
    compression: str = Field(
        default="snappy",
        description="Parquet compression codec used when persisting tabular artifacts.",
    )
    pointer_chunks_enabled: bool = Field(
        default=False,
        description=(
            "Emit one synthetic 'dataset pointer' chunk per tabular dataset into the shared "
            "vector index, so semantic search can discover a dataset exists and route agents "
            "to the SQL/tabular tool (RAG-DATASET-DISCOVERY-RFC.md). Off by default for "
            "measured, gradual activation."
        ),
    )
    query: TabularQueryConfig = Field(
        default_factory=TabularQueryConfig,
        description="Runtime limits and access settings for tabular SQL queries.",
    )


class TextSplitterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = Field(
        default=1500,
        ge=1,
        description="Maximum number of characters per chunk for text splitting.",
    )
    chunk_overlap: int = Field(
        default=150,
        ge=0,
        description="Number of overlapping characters between consecutive chunks.",
    )
    preserve_tables: bool = Field(
        default=True,
        description="If true, keep annotated markdown tables intact (do not split by size).",
    )
