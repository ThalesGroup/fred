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


from datetime import datetime
import os
from pathlib import Path
from typing import Annotated, List, Literal, Union
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
    access_key: Optional[str] = Field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY"), description="MinIO access key from env")
    secret_key: Optional[str] = Field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY"), description="MinIO secret key from env")
    bucket_name: str = Field(default="app-bucket", description="Content store bucket name")
    secure: bool = Field(default=False, description="Use TLS (https)")

class LocalContentStorage(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.knowledge-flow/content-store")), description="Local storage directory")

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
    root_path: str = Field(default=str(Path("~/.knowledge-flow/metadata-store.json")), description="Local storage json file")

class OpenSearchStorage(BaseModel):
    type: Literal["opensearch"]
    host: str = Field(..., description="OpenSearch host URL")
    username: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_USER"), description="Username from env")
    password: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"), description="Password from env")
    secure: bool = Field(default=False, description="Use TLS (https)")
    verify_certs: bool = Field(default=False, description="Verify TLS certs")
    metadata_index: str = Field(..., description="OpenSearch index name for metadata")
    vector_index: str = Field(..., description="OpenSearch index name for vectors")


# --- Final union config (with discriminator)
MetadataStorageConfig = Annotated[Union[LocalMetadataStorage, OpenSearchStorage], Field(discriminator="type")]

###########################################################
#
# --- Tag Storage Configuration
#

class LocalTagStore(BaseModel):
    type: Literal["local"]
    root_path: str = Field(default=str(Path("~/.fred/knowledge/tags-store.json")), description="Local storage json file")

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
    embedding: EmbeddingConfig = Field(..., description="Embedding configuration")
    knowledge_context_storage: KnowledgeContextStorageConfig = Field(..., description="Knowledge context storage configuration")
    knowledge_context_max_tokens: int = 50000
    scheduler: SchedulerConfig


class DocumentProcessingStatus(str, Enum):
    UPLOADED = "uploaded"             # File stored, metadata extracted, no processing yet
    INPUT_PROCESSED = "input_processed"  # Markdown and chunks extracted
    OUTPUT_PROCESSED = "vectorized"         # Vector embedding done
    COMPLETED = "completed"           # All pipeline steps done
    FAILED = "failed"                 # Failed during one of the steps

class DocumentMetadata(BaseModel):
    document_name: str
    document_uid: str
    date_added_to_kb: datetime = Field(default_factory=datetime.utcnow)
    retrievable: bool = False
    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.UPLOADED
    tags: Optional[List[str]] = Field(default=None, description="User-provided tags from the frontend")

    # Optional metadata fields from front or file content
    title: Optional[str] = None
    author: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    last_modified_by: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None

    model_config = {
        "arbitrary_types_allowed": True,
        "json_schema_extra": {
            "examples": [
                {
                    "document_name": "CIR_TSN_PUNCH_2020.docx",
                    "document_uid": "bde801c70277572a5333fe666936f2de7258dbe4e412d2c9cc6be996dc77b310",
                    "date_added_to_kb": "2025-07-18T03:23:09.953244+00:00",
                    "retrievable": True,
                    "processing_status": "uploaded",
                    "tags": ["finance", "cir", "tsn"],
                    "title": "Dossier Technique CIR",
                    "author": "Thales Services SAS",
                    "created": "2021-11-22T11:54:00+00:00",
                    "modified": "2021-12-02T08:26:00+00:00",
                    "last_modified_by": "dimitri tombroff",
                    "category": "None",
                    "subject": "None",
                    "keywords": "None",
                }
            ]
        },
    }