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
from enum import Enum
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional, Union

from fred_core import (
    LogStorageConfig,
    ModelConfiguration,
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    SecurityConfiguration,
    StoreConfig,
)
from fred_core.common.structures import TemporalSchedulerConfig
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    FAST = "fast"
    MEDIUM = "medium"
    RICH = "rich"


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
    secret_key: str = Field(..., description="MinIO secret key (from MINIO_SECRET_KEY env)")
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


ContentStorageConfig = Annotated[Union[LocalContentStorageConfig, MinioStorageConfig], Field(discriminator="type")]


###########################################################
#
#  --- Vector storage configuration
#


class InMemoryVectorStorage(BaseModel):
    type: Literal["in_memory"]


class WeaviateVectorStorage(BaseModel):
    type: Literal["weaviate"]
    host: str = Field(default="https://localhost:8080", description="Weaviate host")
    index_name: str = Field(default="CodeDocuments", description="Weaviate class (collection) name")


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


VectorStorageConfig = Annotated[
    Union[
        InMemoryVectorStorage,
        OpenSearchVectorIndexConfig,
        ChromaVectorStorageConfig,
        WeaviateVectorStorage,
        PgVectorStorageConfig,
    ],
    Field(discriminator="type"),
]


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class PdfPipelineConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        backend: Literal["dlparse_v4", "pypdfium2"] = Field(
            default="dlparse_v4",
            description="PDF backend for Docling conversion.",
        )
        images_scale: float = Field(default=2.0, gt=0.0, description="Docling PDF image scaling factor.")
        generate_picture_images: bool = Field(
            default=False,
            description=("Generate extracted picture image assets during PDF conversion. Independent from profile.process_images (image description)."),
        )
        generate_page_images: bool = Field(default=False, description="Generate full-page images for PDFs.")
        generate_table_images: bool = Field(default=False, description="Generate table images for PDFs.")
        do_table_structure: bool = Field(
            default=False,
            description="Enable table structure extraction in the standard Docling PDF pipeline.",
        )
        do_ocr: bool = Field(
            default=False,
            description="Enable OCR in the standard Docling PDF pipeline.",
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
        pdf: "ProcessingConfig.PdfPipelineConfig" = Field(
            default_factory=lambda: ProcessingConfig.PdfPipelineConfig(),
            description="PDF processing options for this profile.",
        )
        input_processors: List["ProcessingConfig.ProfileInputProcessorConfig"] = Field(
            default_factory=list,
            description="Input processors selected for this profile (suffix-specific).",
        )

    class ProfilesConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        fast: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        medium: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        rich: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())

    default_profile: IngestionProcessingProfile = Field(
        default=IngestionProcessingProfile.MEDIUM,
        description="Default ingestion processing profile when no request-level profile is provided.",
    )
    profiles: ProfilesConfig = Field(
        default_factory=ProfilesConfig,
        description="Named ingestion profiles for request-level pipeline/option selection.",
    )

    def normalize_profile(self, profile: IngestionProcessingProfile | str | None) -> IngestionProcessingProfile:
        if profile is None:
            return self.default_profile
        if isinstance(profile, str):
            return IngestionProcessingProfile(profile)
        return profile

    def get_profile_config(self, profile: IngestionProcessingProfile | str | None) -> "ProcessingConfig.ProfileConfig":
        profile = self.normalize_profile(profile)

        if profile == IngestionProcessingProfile.FAST:
            return self.profiles.fast
        if profile == IngestionProcessingProfile.RICH:
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
    statistic_enabled: bool = Field(
        default=True,
        description="Expose the Statistical MCP server for data analysis helpers.",
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
    neo4j_enabled: bool = Field(
        default=False,
        description="Expose Neo4j graph exploration endpoints and the corresponding MCP server.",
    )
    filesystem_enabled: bool = Field(
        default=False,
        description="Expose agent filesystem utils endpoints and the corresponding MCP server.",
    )


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: str = "temporal"
    temporal: TemporalSchedulerConfig


class AppConfig(BaseModel):
    name: Optional[str] = "Knowledge Flow Backend"
    base_url: str = "/knowledge-flow/v1"
    address: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    reload_dir: str = "."
    max_ingestion_workers: int = 1
    metrics_enabled: bool = True
    metrics_address: str = "127.0.0.1"
    metrics_port: int = 9111
    kpi_process_metrics_interval_sec: int = Field(
        10,
        description="Interval in seconds for processing and logging KPI metrics.",
    )
    kpi_log_summary_interval_sec: float = Field(
        default=0.0,
        description="Emit KPI summary logs every N seconds (bench/debug). Set 0 to disable.",
    )
    kpi_log_summary_top_n: int = Field(
        default=0,
        description="Top-N metrics to show in KPI summary logs. 0 means all / disabled.",
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
    secret_key: str = Field(..., description="MinIO secret key (from MINIO_SECRET_KEY env variable)")
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
    resource_store: StoreConfig
    tag_store: StoreConfig
    kpi_store: StoreConfig
    metadata_store: StoreConfig
    task_store: Optional[StoreConfig] = Field(
        default=None,
        description="Task store backend (optional; scheduler may fall back to defaults).",
    )
    tabular_stores: Optional[Dict[str, StoreConfig]] = Field(default=None, description="Optional tabular store")
    vector_store: VectorStorageConfig
    log_store: Optional[LogStorageConfig] = Field(default=None, description="Optional log store")


# ---------- Agent filesystem config, used for listing, reading, creating & deleting files.  ---------- #


class LocalFilesystemConfig(BaseModel):
    type: Literal["local"] = "local"
    root: str = Field("~/.fred/knowledge-flow/filesystem/", description="Local filesystem root directory.")


class MinioFilesystemConfig(BaseModel):
    type: Literal["minio"] = "minio"
    endpoint: str = Field(..., description="MinIO or S3 compatible endpoint.")
    access_key: str = Field(..., description="MinIO access key.")
    secret_key: str = Field(..., description="MinIO secret key.")
    bucket_name: Optional[str] = Field("filesystem", description="MinIO bucket name.")
    secure: Optional[bool] = Field(False, description="Use TLS for the MinIO client.")

    @model_validator(mode="before")
    @classmethod
    def load_env_secrets(cls, values: dict) -> dict:
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))
        if not values.get("secret_key"):
            raise ValueError("Missing MINIO_SECRET_KEY environment variable")
        return values


FilesystemConfig = Annotated[Union[LocalFilesystemConfig, MinioFilesystemConfig], Field(discriminator="type")]


class WorkspaceLayoutConfig(BaseModel):
    """
    Configurable storage path layout for workspace storage.

    Allowed placeholders:
      {user_id}, {agent_id}, {key}
    """

    user_pattern: str = Field("users/{user_id}/{key}", description="Path template for user exchange storage")
    agent_config_pattern: str = Field("agents/{agent_id}/config/{key}", description="Path template for agent config storage")
    agent_user_pattern: str = Field("agents/{agent_id}/users/{user_id}/{key}", description="Path template for per-user agent storage")

    @model_validator(mode="after")
    def validate_placeholders(self):
        for field_name, required in [
            ("user_pattern", ["user_id", "key"]),
            ("agent_config_pattern", ["agent_id", "key"]),
            ("agent_user_pattern", ["agent_id", "user_id", "key"]),
        ]:
            pattern = getattr(self, field_name)
            for req in required:
                if "{" + req + "}" not in pattern:
                    raise ValueError(f"{field_name} must contain placeholder {{{req}}}")
        return self


class Configuration(BaseModel):
    app: AppConfig
    chat_model: ModelConfiguration
    embedding_model: ModelConfiguration
    vision_model: Optional[ModelConfiguration] = None
    crossencoder_model: Optional[ModelConfiguration] = None
    security: SecurityConfiguration
    attachment_processors: Optional[List[ProcessorConfig]] = Field(
        default=None,
        description=(
            "Optional fast-text processors for attachments. Uses the same ProcessorConfig structure, but classes must subclass BaseFastTextProcessor. If omitted, the default fast processor is used."
        ),
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
    # Workspace storage layout (paths for user/agent config/agent-user storage).
    workspace_layout: WorkspaceLayoutConfig = Field(
        default_factory=lambda: WorkspaceLayoutConfig(),  # type: ignore
        description="Patterns used to build workspace storage paths.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_root_input_processors(cls, values: dict):
        if isinstance(values, dict) and "input_processors" in values:
            raise ValueError(
                "Legacy root field 'input_processors' is no longer supported. Move processors under processing.profiles.<profile>.input_processors.",
            )
        return values
