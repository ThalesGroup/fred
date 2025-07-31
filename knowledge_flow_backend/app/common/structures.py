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
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from fred_core import Security

"""
This module defines the top level data structures used by controllers, processors
unit tests. It helps to decouple the different components of the application and allows
to define clear workflows and data structures.
"""


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


class MinioStorage(BaseModel):
    type: Literal["minio"]
    endpoint: str = Field(default="localhost:9000", description="MinIO API URL")
    access_key: str = Field(default_factory=lambda: os.environ["MINIO_ACCESS_KEY"], description="MinIO access key from env")
    secret_key: str = Field(default_factory=lambda: os.environ["MINIO_SECRET_KEY"], description="MinIO secret key from env")
    bucket_name: str = Field(default="app-bucket", description="Content store bucket name")
    secure: bool = Field(default=False, description="Use TLS (https)")


class LocalContentStorage(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.fred/knowledge-flow/content-store")), description="Local storage directory")


ContentStorageConfig = Annotated[Union[LocalContentStorage, MinioStorage], Field(discriminator="type")]

###########################################################
#
#  --- Metadata Storage Configuration
#


class DuckdbMetadataStorage(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(default="~/.fred/knowledge-flow/db.duckdb", description="Path to the DuckDB database file.")


class OpenSearchStorage(BaseModel):
    type: Literal["opensearch"]
    host: str = Field(..., description="OpenSearch host URL")
    username: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_USER"), description="Username from env")
    password: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"), description="Password from env")
    secure: bool = Field(default=False, description="Use TLS (https)")
    verify_certs: bool = Field(default=False, description="Verify TLS certs")
    index: str = Field(..., description="OpenSearch index name")


# --- Final union config (with discriminator)
MetadataStorageConfig = Annotated[Union[DuckdbMetadataStorage, OpenSearchStorage], Field(discriminator="type")]

###########################################################
#
# --- Tag Storage Configuration
#


class LocalTagStore(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.fred/knowledge-flow/tags-store.json")), description="Local storage json file")


TagStorageConfig = Annotated[Union[LocalTagStore], Field(discriminator="type")]


class InMemoryVectorStorage(BaseModel):
    type: Literal["in_memory"]


class WeaviateVectorStorage(BaseModel):
    type: Literal["weaviate"]
    host: str = Field(default="https://localhost:8080", description="Weaviate host")
    index_name: str = Field(default="CodeDocuments", description="Weaviate class (collection) name")


VectorStorageConfig = Annotated[Union[InMemoryVectorStorage, OpenSearchStorage, WeaviateVectorStorage], Field(discriminator="type")]


class DuckDBTabularStorage(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(default="~/.fred/knowledge-flow/db.duckdb", description="Path to the DuckDB database file.")


TabularStorageConfig = Annotated[Union[DuckDBTabularStorage,], Field(discriminator="type")]

CatalogStorageConfig = Annotated[Union[DuckDBTabularStorage,], Field(discriminator="type")]


class EmbeddingConfig(BaseModel):
    type: str = Field(..., description="The embedding backend to use (e.g., 'openai', 'azureopenai')")


class KnowledgeContextStorageConfig(BaseModel):
    type: str = Field(..., description="The storage backend to use (e.g., 'local', 'minio')")
    local_path: str = Field(default="~/.fred/knowledge-flow/knowledge-context", description="The path of the local metrics store")


class AppSecurity(Security):
    client_id: str = "knowledge-flow"
    keycloak_url: str = "http://localhost:9080/realms/knowledge-flow"


class KnowledgeContextDocument(BaseModel):
    id: str
    document_name: str
    document_type: str
    size: Optional[int] = None
    tokens: Optional[int] = Field(default=0)
    description: Optional[str] = ""


class KnowledgeContext(BaseModel):
    id: str
    title: str
    description: str
    created_at: str
    updated_at: str
    documents: List[KnowledgeContextDocument]
    creator: str
    tokens: Optional[int] = Field(default=0)
    tag: Optional[str] = Field(default="workspace")


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


class PullProvider(str, Enum):
    LOCAL_PATH = "local_path"
    WEBDAV = "webdav"
    S3 = "s3"
    GIT = "git"
    HTTP = "http"
    OTHER = "other"


class BaseDocumentSourceConfig(BaseModel):
    type: Literal["push", "pull"]
    description: Optional[str] = Field(default=None, description="Human-readable description of this source")


class PushSourceConfig(BaseDocumentSourceConfig):
    type: Literal["push"] = "push"
    # No additional fields


class BasePullSourceConfig(BaseModel):
    type: Literal["pull"] = "pull"
    description: Optional[str] = None


class LocalPathPullSource(BasePullSourceConfig):
    provider: Literal["local_path"]
    base_path: str


class GitPullSource(BasePullSourceConfig):
    provider: Literal["github"]
    repo: str


PullSourceConfig = Annotated[
    Union[
        LocalPathPullSource,
        GitPullSource,
        # Add WebDAV, HTTP, etc. here
    ],
    Field(discriminator="provider"),
]

DocumentSourceConfig = Annotated[Union[PushSourceConfig, PullSourceConfig], Field(discriminator="type")]


class Configuration(BaseModel):
    app: AppConfig
    security: AppSecurity
    input_processors: List[ProcessorConfig]
    output_processors: Optional[List[ProcessorConfig]] = None
    content_storage: ContentStorageConfig = Field(..., description="Content Storage configuration")
    metadata_storage: MetadataStorageConfig = Field(..., description="Metadata storage configuration")
    tag_storage: TagStorageConfig = Field(..., description="Tag storage configuration")
    vector_storage: VectorStorageConfig = Field(..., description="Vector storage configuration")
    tabular_storage: TabularStorageConfig = Field(..., description="Tabular storage configuration")
    catalog_storage: CatalogStorageConfig = Field(..., description="Catalog storage configuration")
    embedding: EmbeddingConfig = Field(..., description="Embedding configuration")
    scheduler: SchedulerConfig
    document_sources: Optional[Dict[str, DocumentSourceConfig]] = Field(default_factory=dict, description="Mapping of source_tag identifiers to push/pull source configurations")
