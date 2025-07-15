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
from typing import Annotated, List, Literal, Union
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


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


class Security(BaseModel):
    enabled: bool = True
    keycloak_url: str = "http://localhost:9080/realms/knowledge-flow"
    client_id: str = "knowledge-flow"
    authorized_origins: List[str] = ["http://localhost:5173"]

###########################################################
#
#  --- Content Storage Configuration
#

class MinioStorage(BaseModel):
    type: Literal["minio"]
    endpoint: str = Field(default="localhost:9000", description="MinIO API URL")
    access_key: Optional[str] = Field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY"), description="MinIO access key from env")
    secret_key: Optional[str] = Field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY"), description="MinIO secret key from env")
    content_bucket_name: str = Field(default="app-bucket", description="Content store bucket name")
    context_bucket_name: str = Field(default="agent-contexts", description="Context bucket name")
    secure: bool = Field(default=False, description="Use TLS (https)")

class LocalContentStorage(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.knowledge-flow/content-store")), description="² storage directory")

ContentStorageConfig = Annotated[
    Union[LocalContentStorage, MinioStorage],
    Field(discriminator="type")
]

###########################################################
#
#  --- Metadata Storage Configuration
#

class LocalMetadataStorage(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.knowledge-flow/metadata-store.json")), description="Local storage directory")

class OpenSearchStorage(BaseModel):
    type: Literal["opensearch"]
    host: str = Field(..., description="OpenSearch host URL")
    secure: bool = Field(default=False, description="Use TLS (https)")
    verify_certs: bool = Field(default=False, description="Verify TLS certs")
    metadata_index: str = Field(..., description="OpenSearch index name for metadata")
    vector_index: str = Field(..., description="OpenSearch index name for vectors")
    username: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_USER"), description="Username from env")
    password: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"), description="Password from env")


# --- Final union config (with discriminator)
MetadataStorageConfig = Annotated[
    Union[LocalMetadataStorage, OpenSearchStorage],
    Field(discriminator="type")
]

###########################################################
#
# --- Vector Storage Configuration
#

class InMemoryVectorStorage(BaseModel):
    type: Literal["in_memory"]

class WeaviateVectorStorage(BaseModel):
    type: Literal["weaviate"]
    host: str = Field(default="https://localhost:8080", description="Weaviate host")
    index_name: str = Field(default="CodeDocuments", description="Weaviate class (collection) name")

VectorStorageConfig = Annotated[
    Union[InMemoryVectorStorage, OpenSearchStorage, WeaviateVectorStorage],
    Field(discriminator="type")
]

###########################################################
#
# --- Tabular Storage Configuration
#

class DuckDBTabularStorage(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(default="~/.fred/tabular/tabular_data.duckdb", description="Path to the DuckDB database file for tabular storage.")

TabularStorageConfig = Annotated[
    Union[DuckDBTabularStorage,],
    Field(discriminator="type")
]


class EmbeddingConfig(BaseModel):
    type: str = Field(..., description="The embedding backend to use (e.g., 'openai', 'azureopenai')")

class KnowledgeContextStorageConfig(BaseModel):
    type: str = Field(..., description="The storage backend to use (e.g., 'local', 'minio')")
    local_path: str = Field(default="~/.fred/knowledge-context", description="The path of the local metrics store")

class Configuration(BaseModel):
    security: Security
    input_processors: List[ProcessorConfig]
    output_processors: Optional[List[ProcessorConfig]] = None
    content_storage: ContentStorageConfig = Field(..., description="Content Storage configuration")
    metadata_storage: MetadataStorageConfig = Field(..., description="Metadata storage configuration")
    vector_storage: VectorStorageConfig = Field(..., description="Vector storage configuration")
    tabular_storage: TabularStorageConfig = Field(..., description="Tabular storage configuration")
    embedding: EmbeddingConfig = Field(..., description="Embedding configuration")
    knowledge_context_storage: KnowledgeContextStorageConfig = Field(..., description="Knowledge context storage configuration")
    knowledge_context_max_tokens: int = 50000


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
