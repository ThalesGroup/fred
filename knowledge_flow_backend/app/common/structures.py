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
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Union
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from enum import Enum
from fred_core import (
    SecurityConfiguration,
    PostgresStoreConfig,
    OpenSearchStoreConfig,
    OpenSearchIndexConfig,
    StoreConfig,
)

"""
This module defines the top level data structures used by controllers, processors
unit tests. It helps to decouple the different components of the application and allows
to define clear workflows and data structures.
"""


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    AZUREOPENAI = "azureopenai"
    AZUREAPIM = "azureapim"
    OLLAMA = "ollama"


class Status(str, Enum):
    SUCCESS = "success"
    IGNORED = "ignored"
    ERROR = "error"


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
        prefix (str): The file extension this processor handles (e.g., '.pdf').
        class_path (str): Dotted import path of the processor class.
    """

    prefix: str = Field(..., description="The file extension this processor handles (e.g., '.pdf')")
    class_path: str = Field(..., description="Dotted import path of the processor class")


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

    @model_validator(mode="before")
    @classmethod
    def load_env_if_missing(cls, values: dict) -> dict:
        values.setdefault("access_key", os.getenv("MINIO_ACCESS_KEY"))
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))

        if not values.get("access_key"):
            raise ValueError("Missing MINIO_ACCESS_KEY environment variable")
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


VectorStorageConfig = Annotated[Union[InMemoryVectorStorage, OpenSearchIndexConfig, WeaviateVectorStorage], Field(discriminator="type")]


class EmbeddingConfig(BaseModel):
    type: EmbeddingProvider = Field(..., description="The embedding backend to use (e.g., 'openai', 'azureopenai')")


class TemporalSchedulerConfig(BaseModel):
    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "ingestion"
    workflow_prefix: str = "pipeline"
    connect_timeout_seconds: Optional[int] = 5


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
    security: SecurityConfiguration


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
        values.setdefault("access_key", os.getenv("MINIO_ACCESS_KEY"))
        values.setdefault("secret_key", os.getenv("MINIO_SECRET_KEY"))

        if not values.get("access_key"):
            raise ValueError("Missing MINIO_ACCESS_KEY environment variable")

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
    opensearch: OpenSearchStoreConfig
    resource_store: StoreConfig
    tag_store: StoreConfig
    kpi_store: StoreConfig
    metadata_store: StoreConfig
    catalog_store: StoreConfig
    tabular_stores: Optional[Dict[str, StoreConfig]] = Field(default=None, description="Optional tabular store")
    vector_store: VectorStorageConfig


class Configuration(BaseModel):
    app: AppConfig

    input_processors: List[ProcessorConfig]
    output_processors: Optional[List[ProcessorConfig]] = None
    content_storage: ContentStorageConfig = Field(..., description="Content Storage configuration")
    embedding: EmbeddingConfig = Field(..., description="Embedding configuration")
    scheduler: SchedulerConfig
    document_sources: Dict[str, DocumentSourceConfig] = Field(default_factory=dict, description="Mapping of source_tag identifiers to push/pull source configurations")
    storage: StorageConfig
