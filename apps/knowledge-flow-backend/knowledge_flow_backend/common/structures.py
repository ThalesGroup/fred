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


import os
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional, Union

from fred_core import (
    LogStorageConfig,
    SecurityConfiguration,
)
from fred_core.common import (
    KpiObservabilityConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    StoreConfig,
    TemporalSchedulerConfig,
)
from fred_core.scheduler import SchedulerBackend
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import WithJsonSchema

"""
This module defines the top level data structures used by controllers, processors
unit tests. It helps to decouple the different components of the application and allows
to define clear workflows and data structures.
"""


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    IGNORED = "ignored"
    FAILED = "failed"
    ERROR = "error"
    FINISHED = "finished"


class IngestionProcessingProfile(str, Enum):
    fast = "fast"
    medium = "medium"
    rich = "rich"


_DURATION_PATTERN = re.compile(r"^(?P<value>\d+)\s*(?P<unit>[smhd]?)$")
_DURATION_MULTIPLIER_SECONDS = {
    "": 1,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def parse_duration_seconds(value: object, *, field_name: str) -> int:
    """
    Parse duration values expressed as:
      - integer seconds (e.g. 3600)
      - compact strings (e.g. "45s", "10m", "1h", "2d")
    """
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive duration, got {value!r}")

    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds <= 0:
            raise ValueError(f"{field_name} must be > 0 seconds")
        return seconds

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be an integer seconds value or a compact duration string like '1h'",
        )

    token = value.strip().lower()
    match = _DURATION_PATTERN.fullmatch(token)
    if not match:
        raise ValueError(
            f"{field_name}='{value}' is invalid. Use formats like '45s', '10m', '1h', '2d' or integer seconds.",
        )

    amount = int(match.group("value"))
    unit = match.group("unit")
    seconds = amount * _DURATION_MULTIPLIER_SECONDS[unit]
    if seconds <= 0:
        raise ValueError(f"{field_name} must be > 0 seconds")
    return seconds


class OutputProcessorResponse(BaseModel):
    """
    Represents the response of a n output processor operation. It is used to report
    the status of the output process to the REST remote client.
    Attributes:
        status (str): The status of the vectorization operation.
    """

    status: Status


class ProcessorConfig(BaseModel):
    """
    Configuration structure for a file processor.
    Attributes:
        suffix (str): The file extension this processor handles (e.g., '.pdf').
        class_path (str): Dotted import path of the processor class.
        description (str): Human readable explanation of what the processor does.
    """

    suffix: str = Field(..., description="The file extension this processor handles (e.g., '.pdf')")
    class_path: str = Field(..., description="Dotted import path of the processor class")
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Human-readable description of the processor purpose shown in the UI.",
    )


class LibraryProcessorConfig(BaseModel):
    """
    Configuration structure for a library-level output processor.

    Attributes:
        class_path (str): Dotted import path of the processor class.
        description (str): Human readable explanation of what the processor does.
    """

    class_path: str = Field(..., description="Dotted import path of the library output processor class")
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Human-readable description of the library output processor purpose shown in the UI.",
    )


###########################################################
#
#  --- Content Storage Configuration
#


class MinioStorageConfig(BaseModel):
    type: Literal["minio"]
    endpoint: str = Field(default="localhost:9000", description="MinIO API URL")
    access_key: str = Field(..., description="MinIO access key (from MINIO_ACCESS_KEY env)")
    secret_key: Annotated[str, WithJsonSchema({"type": "string"})] = Field(default=None, description="MinIO secret key (from MINIO_SECRET_KEY env)")  # type: ignore[assignment]
    bucket_name: str = Field(default="app-bucket", description="Content store bucket name")
    secure: bool = Field(default=False, description="Use TLS (https)")
    public_endpoint: Optional[str] = Field(default=None, description="Public MinIO endpoint for browser-facing presigned URLs (e.g. 'https://my.minio.ingress'). If not set, uses endpoint.")
    public_secure: Optional[bool] = Field(default=None, description="Use TLS for public endpoint. If not set, inferred from public_endpoint scheme.")

    @model_validator(mode="before")
    @classmethod
    def load_env_if_missing(cls, values: dict) -> dict:
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))

        if not values.get("secret_key"):
            raise ValueError("Missing MINIO_SECRET_KEY environment variable")

        return values


class LocalContentStorageConfig(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.fred/knowledge-flow/content-store")), description="Local storage directory")


class GcsStorageConfig(BaseModel):
    """
    Google Cloud Storage content store. Authentication uses Application Default
    Credentials / Workload Identity (no JSON key required).

    Bucket-splitting mirrors MinIO: the configured ``bucket_name`` is suffixed
    with ``-documents`` and ``-objects`` (content store) and ``-files`` (namespace
    file store). All buckets must already exist.
    """

    type: Literal["gcs"]
    bucket_name: str = Field(default="app-bucket", description="Base GCS bucket name (suffixed with -documents/-objects).")
    project_id: Optional[str] = Field(default=None, description="GCP project id; inferred from ADC when empty.")
    signing_service_account_email: Optional[str] = Field(
        default=None,
        description=(
            "Service account email used to sign V4 signed URLs for backend-internal "
            "tabular Parquet reads, via IAM signBlob under Workload Identity (no JSON "
            "key). Required for content_storage.type=gcs; startup fails clearly when "
            "omitted. The Workload Identity service account must hold "
            "iam.serviceAccounts.signBlob on this account, which must have "
            "storage.objects.get on the objects bucket."
        ),
    )


ContentStorageConfig = Annotated[Union[LocalContentStorageConfig, MinioStorageConfig, GcsStorageConfig], Field(discriminator="type")]


class ClickHouseStoreConfig(BaseModel):
    host: str = Field(default="localhost", description="ClickHouse host")
    port: int = Field(default=8123, description="ClickHouse HTTP port")
    database: str = Field(default="default", description="ClickHouse database")
    username: str = Field(default="default", description="ClickHouse username")
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD"),
        description="ClickHouse password (from CLICKHOUSE_PASSWORD env)",
    )
    secure: bool = Field(default=False, description="Use HTTPS for ClickHouse client")
    verify: bool = Field(default=True, description="Verify TLS certificates for ClickHouse")


###########################################################
#
#  --- Vector storage configuration
#


class InMemoryVectorStorage(BaseModel):
    type: Literal["in_memory"]


class OpenSearchVectorIndexConfig(BaseModel):
    type: Literal["opensearch"]
    index: str = Field(..., description="OpenSearch index name")
    bulk_size: int = Field(default=1000, description="Number of documents to send in each bulk insert request")


class ChromaVectorStorageConfig(BaseModel):
    """
    Local, embedded Chroma. No server needed.
    - persist_path: folder where Chroma (DuckDB/Parquet) stores data
    - collection_name: logical collection for your chunks
    - distance: ANN space; 'cosine' matches our UI-friendly similarity
    """

    type: Literal["chroma"]
    local_path: str = Field(default=str(Path("~/.fred/knowledge-flow/chromadb-vector-store")), description="Local vector storage path")
    collection_name: str = Field("fred_chunks", description="Chroma collection name")
    distance: Literal["cosine", "l2", "ip"] = Field("cosine", description="Vector space (affects HNSW metric)")


class PgVectorStorageConfig(BaseModel):
    """
    PostgreSQL + pgvector backend.
    - Uses shared `storage.postgres` connection settings.
    - Stores vectors in the default pgvector table under a collection name.
    """

    type: Literal["pgvector"]
    collection_name: str = Field("fred_chunks", description="Logical collection name")


class ClickHouseVectorStorageConfig(BaseModel):
    """
    ClickHouse backend.
    - Uses shared `storage.clickhouse` connection settings.
    - Stores vectors in the configured table.
    """

    type: Literal["clickhouse"]
    table: str = Field("fred_vectors", description="ClickHouse table name for chunks")
    bulk_size: int = Field(default=1000, description="Number of rows per insert batch")


VectorStorageConfig = Annotated[
    Union[
        InMemoryVectorStorage,
        OpenSearchVectorIndexConfig,
        ChromaVectorStorageConfig,
        PgVectorStorageConfig,
        ClickHouseVectorStorageConfig,
    ],
    Field(discriminator="type"),
]


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    class PdfPipelineConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        extractor: Literal["docling", "pymupdf"] = Field(
            default="pymupdf",
            description="PDF text extractor engine: 'docling' for layout-aware extraction, 'pymupdf' for fast page-oriented extraction.",
        )
        do_ocr: bool = Field(
            default=False,
            description="Enable PaddleOCR post-processing on extracted images when using the docling extractor.",
        )

    class ProfileInputProcessorConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        suffix: str = Field(..., description="The file suffix this processor handles (e.g., '.pdf').")
        class_path: str = Field(..., description="Dotted import path of the processor class.")
        description: Optional[str] = Field(
            default=None,
            min_length=1,
            description="Human-readable description of the processor purpose shown in the UI.",
        )

    class ProfileConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        use_gpu: bool = Field(
            default=True,
            description="Enable/disable GPU usage for this profile (if supported by the selected processors).",
        )
        process_images: bool = Field(
            default=False,
            description="Enable/disable semantic image description in markdown for this profile.",
        )
        generate_summary: bool = Field(
            default=False,
            description="Enable/disable human-centric abstract and keyword generation for this profile.",
        )
        input_activity_timeout: str = Field(
            default="1h",
            description="Temporal start-to-close timeout for input processing activities (e.g., '1h', '45m').",
        )
        activity_heartbeat_timeout: str = Field(
            default="5m",
            description="Temporal heartbeat timeout for input processing activities (e.g., '5m', '10m'). Must be larger than the worker's heartbeat interval (~20s).",
        )
        pdf: "ProcessingConfig.PdfPipelineConfig" = Field(
            default_factory=lambda: ProcessingConfig.PdfPipelineConfig(),
            description="PDF processing options for this profile.",
        )
        text_splitter: "ProcessingConfig.TextSplitterConfig" = Field(
            default_factory=lambda: ProcessingConfig.TextSplitterConfig(),
            description="Text splitter configuration for vectorization and summarization.",
        )
        input_processors: List["ProcessingConfig.ProfileInputProcessorConfig"] = Field(
            default_factory=list,
            description="Input processors selected for this profile (suffix-specific).",
        )
        retry_initial_interval: str = Field(
            default="30s",
            description="Temporal retry delay before the first retry for this profile's ingestion activities.",
        )
        retry_backoff_coefficient: float = Field(
            default=2.0,
            ge=1.0,
            description="Temporal retry backoff coefficient for this profile's ingestion activities.",
        )
        retry_maximum_interval: str = Field(
            default="10m",
            description="Maximum Temporal retry delay for this profile's ingestion activities.",
        )
        retry_maximum_attempts: int = Field(
            default=6,
            ge=1,
            description="Maximum Temporal activity attempts for this profile, including the first attempt.",
        )
        retry_non_retryable_error_types: List[str] = Field(
            default_factory=list,
            description="Temporal application error types that should fail fast for this profile without retry.",
        )

        @property
        def retry_initial_interval_seconds(self) -> int:
            return parse_duration_seconds(self.retry_initial_interval, field_name="processing.profiles.*.retry_initial_interval")

        @property
        def retry_maximum_interval_seconds(self) -> int:
            return parse_duration_seconds(self.retry_maximum_interval, field_name="processing.profiles.*.retry_maximum_interval")

        @field_validator("input_activity_timeout", mode="before")
        @classmethod
        def _normalize_input_activity_timeout(cls, value: object) -> str:
            if value is None:
                return "1h"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.input_activity_timeout",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.input_activity_timeout",
            )
            return normalized

        @property
        def input_activity_timeout_seconds(self) -> int:
            return parse_duration_seconds(
                self.input_activity_timeout,
                field_name="processing.profiles.*.input_activity_timeout",
            )

        @field_validator("activity_heartbeat_timeout", mode="before")
        @classmethod
        def _normalize_activity_heartbeat_timeout(cls, value: object) -> str:
            if value is None:
                return "5m"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.activity_heartbeat_timeout",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.activity_heartbeat_timeout",
            )
            return normalized

        @property
        def activity_heartbeat_timeout_seconds(self) -> int:
            return parse_duration_seconds(
                self.activity_heartbeat_timeout,
                field_name="processing.profiles.*.activity_heartbeat_timeout",
            )

        @field_validator("retry_initial_interval", mode="before")
        @classmethod
        def _normalize_retry_initial_interval(cls, value: object) -> str:
            if value is None:
                return "30s"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.retry_initial_interval",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.retry_initial_interval",
            )
            return normalized

        @field_validator("retry_maximum_interval", mode="before")
        @classmethod
        def _normalize_retry_maximum_interval(cls, value: object) -> str:
            if value is None:
                return "10m"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.retry_maximum_interval",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.retry_maximum_interval",
            )
            return normalized

        @model_validator(mode="after")
        def validate_retry_intervals(self) -> "ProcessingConfig.ProfileConfig":
            """
            Keep per-profile Temporal retry intervals coherent.

            Why:
            - A retry cap smaller than the initial retry delay is almost always a
              configuration mistake for one processing profile.

            How to use:
            - Keep `retry_maximum_interval` greater than or equal to
              `retry_initial_interval`.
            """
            if self.retry_maximum_interval_seconds < self.retry_initial_interval_seconds:
                raise ValueError("processing.profiles.*.retry_maximum_interval must be >= retry_initial_interval")
            return self

    class ProfilesConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        fast: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        medium: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        rich: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())

    path_base_model: str = Field(
        default=".",
        description="Base directory prepended to the 'models/' subfolder when loading or downloading ML models. Defaults to '.' (current working directory).",
    )
    default_profile: IngestionProcessingProfile = Field(
        default=IngestionProcessingProfile.medium,
        description="Default ingestion processing profile when no request-level profile is provided.",
    )
    profiles: ProfilesConfig = Field(
        default_factory=ProfilesConfig,
        description="Named ingestion profiles for request-level pipeline/option selection.",
    )

    def normalize_profile(self, profile: IngestionProcessingProfile | str | None) -> IngestionProcessingProfile:
        if profile is None:
            return self.default_profile
        # IngestionProcessingProfile is itself a str subclass, so this also covers
        # (and is idempotent for) an already-valid enum member.
        return IngestionProcessingProfile(profile)

    def get_profile_config(self, profile: IngestionProcessingProfile | str | None) -> "ProcessingConfig.ProfileConfig":
        profile = self.normalize_profile(profile)

        if profile == IngestionProcessingProfile.fast:
            return self.profiles.fast
        if profile == IngestionProcessingProfile.rich:
            return self.profiles.rich
        return self.profiles.medium

    def is_gpu_enabled_any_profile(self) -> bool:
        return any(self.get_profile_config(profile).use_gpu for profile in IngestionProcessingProfile)


class MCPConfig(BaseModel):
    """
    Feature toggles for MCP-only HTTP/MCP surfaces.

    These do NOT affect core storage backends (e.g., using OpenSearch
    as vector store or metadata store). They only control whether
    optional monitoring/exploration controllers and their MCP servers
    are exposed.
    """

    reports_enabled: bool = Field(
        default=True,
        description="Expose the Reports MCP server (Markdown-first report generation).",
    )
    kpi_enabled: bool = Field(
        default=True,
        description="Expose the KPI MCP server for querying application KPIs.",
    )
    tabular_enabled: bool = Field(
        default=True,
        description="Expose the Tabular MCP server for SQL/table exploration.",
    )
    text_enabled: bool = Field(
        default=True,
        description="Expose the Text MCP server for semantic vector search.",
    )
    templates_enabled: bool = Field(
        default=True,
        description="Expose the Template MCP server for prompts/templates.",
    )
    resources_enabled: bool = Field(
        default=True,
        description="Expose the Resources MCP server for resource/tag management.",
    )
    opensearch_ops_enabled: bool = Field(
        default=False,
        description="Expose OpenSearch operational endpoints and the corresponding MCP server.",
    )
    prometheus_ops_enabled: bool = Field(
        default=False,
        description="Expose Prometheus operational endpoints and the corresponding MCP server.",
    )
    filesystem_enabled: bool = Field(
        default=False,
        description="Expose agent filesystem utils endpoints and the corresponding MCP server.",
    )
    filesystem_read_default_limit: int = Field(
        default=100,
        ge=1,
        description="Default line count returned by filesystem read_file when callers omit limit.",
    )
    filesystem_read_max_limit: int = Field(
        default=500,
        ge=1,
        description="Absolute maximum line count accepted by filesystem read_file.",
    )
    filesystem_read_default_max_chars: int = Field(
        default=20_000,
        ge=1,
        description="Default maximum character count returned by filesystem read_file when callers omit max_chars.",
    )
    filesystem_read_absolute_max_chars: int = Field(
        default=50_000,
        ge=1,
        description="Absolute maximum character count accepted by filesystem read_file.",
    )

    @model_validator(mode="after")
    def validate_filesystem_read_limits(self) -> "MCPConfig":
        if self.filesystem_read_default_limit > self.filesystem_read_max_limit:
            raise ValueError("mcp.filesystem_read_default_limit must be <= mcp.filesystem_read_max_limit")
        if self.filesystem_read_default_max_chars > self.filesystem_read_absolute_max_chars:
            raise ValueError("mcp.filesystem_read_default_max_chars must be <= mcp.filesystem_read_absolute_max_chars")
        return self


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: SchedulerBackend = SchedulerBackend.TEMPORAL
    temporal: TemporalSchedulerConfig


class AppConfig(BaseModel):
    name: Optional[str] = "Knowledge Flow Backend"
    base_url: str = "/knowledge-flow/v1"
    address: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    reload_dir: str = "."
    gcu_version: str | None = None
    default_team_max_resources_storage_size: Optional[int] = Field(
        default=None,
        description="Default storage limit in bytes for a team when not explicitly set.",
    )
    personal_max_resources_storage_size: Optional[int] = Field(
        default=None,
        description="Maximum resources storage size in bytes for a personal space",
    )


class PrometheusConfig(BaseModel):
    base_url: str = Field(
        ...,
        description="Base URL of a Prometheus-compatible HTTP API.",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify upstream TLS certificates when querying Prometheus.",
    )
    timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        description="HTTP timeout applied to Prometheus API calls.",
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="Optional bearer token loaded from PROMETHEUS_BEARER_TOKEN.",
    )
    username: Optional[str] = Field(
        default="admin",
        description="Basic-auth username configured directly in prometheus.username. Defaults to 'admin'.",
    )
    password: Optional[str] = Field(
        default=None,
        description="Optional basic-auth password loaded from PROMETHEUS_PASSWORD.",
    )

    @model_validator(mode="before")
    @classmethod
    def load_env_credentials(cls, values: dict) -> dict:
        values.setdefault("bearer_token", os.getenv("PROMETHEUS_BEARER_TOKEN"))
        values.setdefault("password", os.getenv("PROMETHEUS_PASSWORD"))
        return values

    @field_validator("base_url", mode="after")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("prometheus.base_url must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_basic_auth_pair(self) -> "PrometheusConfig":
        if self.password and not self.username:
            raise ValueError(
                "prometheus.username must not be empty when prometheus.password is set",
            )
        return self


class IntegrationsConfig(BaseModel):
    """Optional upstream service integrations consumed by Knowledge Flow."""

    prometheus: Optional[PrometheusConfig] = Field(
        default=None,
        description="Optional Prometheus API configuration for cluster-wide metrics queries.",
    )


class PullProvider(str, Enum):
    LOCAL_PATH = "local_path"
    WEBDAV = "webdav"
    S3 = "s3"
    GIT = "git"
    HTTP = "http"
    OTHER = "other"


class PushSourceConfig(BaseModel):
    type: Literal["push"] = "push"
    description: Optional[str] = Field(default=None, description="Human-readable description of this source")


class BasePullSourceConfig(BaseModel):
    type: Literal["pull"] = "pull"
    description: Optional[str] = Field(default=None, description="Human-readable description of this source")


class FileSystemPullSource(BasePullSourceConfig):
    provider: Literal["local_path"]
    base_path: str


class GitPullSource(BasePullSourceConfig):
    provider: Literal["github"]
    repo: str = Field(..., description="GitHub repository in the format 'owner/repo'")
    branch: Optional[str] = Field(default="main", description="Git branch to pull from")
    subdir: Optional[str] = Field(default="", description="Subdirectory to extract files from")
    username: Optional[str] = Field(default=None, description="Optional GitHub username (for logs)")
    token: str = Field(..., description="GitHub token (from GITHUB_TOKEN env variable)")

    @model_validator(mode="before")
    @classmethod
    def load_env_token(cls, values: dict) -> dict:
        values.setdefault("token", os.getenv("GITHUB_TOKEN"))
        if not values.get("token"):
            raise ValueError("Missing GITHUB_TOKEN environment variable")
        return values


class SpherePullSource(BasePullSourceConfig):
    provider: Literal["sphere"]
    base_url: str = Field(..., description="Base URL for the Sphere API")
    parent_node_id: str = Field(..., description="ID of the parent folder or node to list/download")
    username: str = Field(..., description="Username for Sphere Basic Auth")
    password: str = Field(..., description="Password (loaded from SPHERE_PASSWORD)")
    apikey: str = Field(..., description="API key (loaded from SPHERE_API_KEY)")
    verify_ssl: bool = Field(default=False, description="Set to True to verify SSL certs")

    @model_validator(mode="before")
    @classmethod
    def load_env_vars(cls, values: dict) -> dict:
        values.setdefault("password", os.getenv("SPHERE_PASSWORD"))
        values.setdefault("apikey", os.getenv("SPHERE_API_KEY"))

        if not values.get("password"):
            raise ValueError("Missing SPHERE_PASSWORD environment variable")

        if not values.get("apikey"):
            raise ValueError("Missing SPHERE_API_KEY environment variable")

        return values


class GitlabPullSource(BasePullSourceConfig):
    type: Literal["pull"] = "pull"
    provider: Literal["gitlab"]
    repo: str = Field(..., description="GitLab repository in the format 'namespace/project'")
    branch: Optional[str] = Field(default="main", description="Branch to pull from")
    subdir: Optional[str] = Field(default="", description="Optional subdirectory to scan files from")
    token: str = Field(..., description="GitLab private token (from GITLAB_TOKEN env variable)")
    base_url: str = Field(default="https://gitlab.com/api/v4", description="GitLab API base URL")

    @model_validator(mode="before")
    @classmethod
    def load_env_token(cls, values: dict) -> dict:
        values.setdefault("token", os.getenv("GITLAB_TOKEN"))
        if not values.get("token"):
            raise ValueError("Missing GITLAB_TOKEN environment variable")
        return values


class MinioPullSource(BasePullSourceConfig):
    type: Literal["pull"] = "pull"
    provider: Literal["minio"]
    endpoint_url: str = Field(..., description="S3-compatible endpoint (e.g., https://s3.amazonaws.com)")
    bucket_name: str = Field(..., description="Name of the S3 bucket to scan")
    prefix: Optional[str] = Field(default="", description="Optional prefix (folder path) to scan inside the bucket")
    access_key: str = Field(..., description="MinIO access key (from MINIO_ACCESS_KEY env variable)")
    secret_key: Annotated[str, WithJsonSchema({"type": "string"})] = Field(default=None, description="MinIO secret key (from MINIO_SECRET_KEY env variable)")  # type: ignore[assignment]
    region: Optional[str] = Field(default="us-east-1", description="AWS region (used by some clients)")
    secure: bool = Field(default=True, description="Use HTTPS (secure=True) or HTTP (secure=False)")

    @model_validator(mode="before")
    @classmethod
    def load_env_secrets(cls, values: dict) -> dict:
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))

        if not values.get("secret_key"):
            raise ValueError("Missing MINIO_SECRET_KEY environment variable")

        return values


PullSourceConfig = Annotated[
    Union[
        FileSystemPullSource,
        GitPullSource,
        SpherePullSource,
        GitlabPullSource,
        MinioPullSource,
    ],
    Field(discriminator="provider"),
]
DocumentSourceConfig = Annotated[Union[PushSourceConfig, PullSourceConfig], Field(discriminator="type")]


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig
    opensearch: Optional[OpenSearchStoreConfig] = Field(default=None, description="Optional OpenSearch store")
    clickhouse: Optional[ClickHouseStoreConfig] = Field(default=None, description="Optional ClickHouse store")
    resource_store: StoreConfig
    tag_store: StoreConfig
    metadata_store: StoreConfig
    tabular_store: "TabularStoreConfig" = Field(
        default_factory=lambda: TabularStoreConfig(),  # type: ignore
        description="Dataset-centric tabular runtime configuration backed by Parquet artifacts in content storage.",
    )
    vector_store: VectorStorageConfig
    log_store: Optional[LogStorageConfig] = Field(default=None, description="Optional log store")


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
        description="Hard cap applied to query result previews.",
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
        description="Prefix under content_storage objects where Parquet datasets are stored.",
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


# ---------- Agent filesystem config, used for listing, reading, creating & deleting files.  ---------- #


class LocalFilesystemConfig(BaseModel):
    type: Literal["local"] = "local"
    root: str = Field("~/.fred/knowledge-flow/filesystem/", description="Local filesystem root directory.")


class MinioFilesystemConfig(BaseModel):
    type: Literal["minio"] = "minio"
    endpoint: str = Field(..., description="MinIO or S3 compatible endpoint.")
    access_key: str = Field(..., description="MinIO access key.")
    secret_key: Annotated[str, WithJsonSchema({"type": "string"})] = Field(default=None, description="MinIO secret key (from MINIO_SECRET_KEY env).")  # type: ignore[assignment]
    bucket_name: Optional[str] = Field("filesystem", description="MinIO bucket name.")
    secure: Optional[bool] = Field(False, description="Use TLS for the MinIO client.")

    @model_validator(mode="before")
    @classmethod
    def load_env_secrets(cls, values: dict) -> dict:
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))
        if not values.get("secret_key"):
            raise ValueError("Missing MINIO_SECRET_KEY environment variable")
        return values


class GcsFilesystemConfig(BaseModel):
    """
    Google Cloud Storage virtual filesystem. Authentication uses Application
    Default Credentials / Workload Identity (no JSON key required). The bucket
    must already exist; an optional ``prefix`` lets several logical roots share it.
    """

    type: Literal["gcs"] = "gcs"
    bucket_name: str = Field("filesystem", description="GCS bucket name.")
    prefix: str = Field("", description="Optional key prefix within the bucket (default '').")
    project_id: Optional[str] = Field(default=None, description="GCP project id; inferred from ADC when empty.")


FilesystemConfig = Annotated[Union[LocalFilesystemConfig, MinioFilesystemConfig, GcsFilesystemConfig], Field(discriminator="type")]


class DocumentMarkingPatternConfig(BaseModel):
    label: str = Field(..., min_length=1, description="Normalized label returned when the regex matches.")
    pattern: str = Field(..., min_length=1, description="Regex used to detect the marking in extracted guardrail text.")


class DocumentGuardrailConfig(BaseModel):
    enabled: bool = Field(default=False, description="Enable ingestion-time document marking guardrails.")
    source_tags: list[str] = Field(
        default_factory=list,
        description="Optional source tags this guardrail applies to. Empty means all sources.",
    )
    allowed_labels: list[str] = Field(
        default_factory=list,
        description="Optional allow-list of labels accepted by the guardrail. Empty means detection-only.",
    )
    on_no_label: Literal["allow", "warn", "reject"] = Field(
        default="allow",
        description="Behavior when no explicit document marking is detected.",
    )
    patterns: list[DocumentMarkingPatternConfig] = Field(
        default_factory=list,
        description="Regex patterns used to recognize explicit document markings.",
    )

    @model_validator(mode="after")
    def validate_guardrail(self) -> "DocumentGuardrailConfig":
        if not self.enabled:
            return self
        if not self.patterns:
            raise ValueError("document_guardrail.patterns must not be empty when the guardrail is enabled")
        return self


class ObservabilityConfig(BaseModel):
    kpi: KpiObservabilityConfig = Field(default_factory=KpiObservabilityConfig)


class Configuration(BaseModel):
    app: AppConfig
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    integrations: Optional[IntegrationsConfig] = Field(
        default=None,
        description="Optional third-party service integrations used by the backend.",
    )
    chat_model: ModelConfiguration
    embedding_model: ModelConfiguration
    vision_model: Optional[ModelConfiguration] = None
    ocr_model: Optional[ModelConfiguration] = Field(
        default=None,
        description="Optional remote OCR model configuration. When set, PDF OCR can be delegated to an external API instead of local Docling OCR.",
    )
    crossencoder_model: Optional[ModelConfiguration] = None
    security: SecurityConfiguration
    attachment_processors: Optional[List[ProcessorConfig]] = Field(
        default=None,
        description="Optional fast-text processors for attachments. Uses the same ProcessorConfig structure, but classes must subclass BaseFastTextProcessor. If omitted, the default fast processor is used.",
    )
    document_guardrail: Optional[DocumentGuardrailConfig] = Field(
        default=None,
        description="Optional ingestion-time guardrail for explicit document markings.",
    )
    output_processors: Optional[List[ProcessorConfig]] = None
    library_output_processors: Optional[List[LibraryProcessorConfig]] = None
    content_storage: ContentStorageConfig = Field(..., description="Content Storage configuration")
    scheduler: SchedulerConfig
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig, description="A collection of feature flags to enable or disable optional functionality.")
    document_sources: Dict[str, DocumentSourceConfig] = Field(default_factory=dict, description="Mapping of source_tag identifiers to push/pull source configurations")
    storage: StorageConfig
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="Feature toggles for MCP-only endpoints and servers.")
    filesystem: FilesystemConfig = Field(..., description="Filesystem backend configuration.")

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_root_input_processors(cls, values: dict):
        if isinstance(values, dict) and "input_processors" in values:
            raise ValueError(
                "Legacy root field 'input_processors' is no longer supported. Move processors under processing.profiles.<profile>.input_processors.",
            )
        return values

    @model_validator(mode="before")
    @classmethod
    def resolve_tabular_store_config(cls, values: object):
        """
        Validate the modern tabular-store configuration shape.

        Why this exists:
        - Tabular storage is now exposed through one single dataset-centric
          `storage.tabular_store` block.
        - The removed `storage.tabular_stores` key should fail loudly instead
          of being silently ignored.

        How to use:
        - Configure `storage.tabular_store.artifacts_prefix`,
          `storage.tabular_store.format`, `storage.tabular_store.compression`,
          and `storage.tabular_store.query.*`.
        - Omit `storage.tabular_store` only when you want the defaults.

        Example:
        ```yaml
        content_storage:
          type: local
          root_path: ".fred/data/content"
        storage:
          tabular_store:
            artifacts_prefix: "tabular/datasets"
        ```
        """

        if not isinstance(values, dict):
            return values

        storage_value = values.get("storage")

        if isinstance(storage_value, dict) and "tabular_stores" in storage_value and storage_value.get("tabular_stores") is not None:
            raise ValueError(
                "'storage.tabular_stores' is no longer supported. Configure tabular settings under 'storage.tabular_store'.",
            )

        if isinstance(storage_value, dict):
            tabular_store_value = storage_value.get("tabular_store")
            if isinstance(tabular_store_value, dict):
                tabular_query_value = tabular_store_value.get("query")
                if isinstance(tabular_query_value, dict) and "presigned_ttl_seconds" in tabular_query_value:
                    raise ValueError(
                        "'storage.tabular_store.query.presigned_ttl_seconds' is no longer supported. Use 'storage.tabular_store.query.internal_presigned_ttl_seconds'.",
                    )

        return values

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_app_ingestion_concurrency(cls, values: object):
        """
        Move the legacy app-level ingestion workers knob into scheduler.temporal.

        Why:
            Ingestion queue/concurrency settings logically belong to the Temporal
            scheduler configuration, not generic app runtime settings.
        How:
            Read legacy `app.max_ingestion_workers` when present and backfill missing
            `scheduler.temporal.ingestion_*` keys without overriding explicit
            scheduler-level configuration.
        Usage example:
            `app.max_ingestion_workers: 3` now behaves like setting all three
            `scheduler.temporal.ingestion_*` keys to `3`.
        """
        if not isinstance(values, dict):
            return values

        app_value = values.get("app")
        scheduler_value = values.get("scheduler")
        if not isinstance(app_value, dict) or not isinstance(scheduler_value, dict):
            return values

        temporal_value = scheduler_value.get("temporal")
        if not isinstance(temporal_value, dict):
            return values

        legacy_single = app_value.get("max_ingestion_workers")

        if legacy_single is not None:
            temporal_value.setdefault("ingestion_workflow_parallelism", legacy_single)
            temporal_value.setdefault("ingestion_max_concurrent_workflow_tasks", legacy_single)
            temporal_value.setdefault("ingestion_max_concurrent_activities", legacy_single)

        return values
