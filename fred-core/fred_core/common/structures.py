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
from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class BaseModelWithId(BaseModel):
    id: str


class TemporalSchedulerConfig(BaseModel):
    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "default"
    workflow_id_prefix: str = "task"
    connect_timeout_seconds: Optional[int] = 5


class ModelConfiguration(BaseModel):
    provider: Optional[str] = Field(
        None, description="Provider of the AI model, e.g., openai, ollama, azure."
    )
    name: Optional[str] = Field(None, description="Model name, e.g., gpt-4o, llama2.")
    settings: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional provider-specific settings, e.g., Azure deployment name.",
    )


class OpenSearchStoreConfig(BaseModel):
    host: str = Field(..., description="OpenSearch host URL")
    username: str = Field(..., description="Username from env")
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"),
        description="Password from env",
    )
    secure: bool = Field(default=False, description="Use TLS (https)")
    verify_certs: bool = Field(default=False, description="Verify TLS certs")


class OpenSearchIndexConfig(BaseModel):
    type: Literal["opensearch"]
    index: str = Field(..., description="OpenSearch index name")


class LogStoreConfig(BaseModel):
    type: Literal["log"]
    level: str = Field(..., description="Logging level")


class DuckdbStoreConfig(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(..., description="Path to the DuckDB database file.")


class PostgresStoreConfig(BaseModel):
    type: Literal["postgres"] = "postgres"
    host: Optional[str] = Field(default=None, description="PostgreSQL host")
    port: int = 5432
    sqlite_path: Optional[str] = Field(
        default=None,
        description="Path to the SQLite database file (for local dev/testing).",
    )
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD")
    )
    echo: bool = Field(default=False, description="SQLAlchemy echo flag.")
    pool_size: Optional[int] = Field(
        default=None, description="Optional pool size for the engine."
    )
    max_overflow: Optional[int] = Field(
        default=None,
        description="Optional max_overflow for SQLAlchemy pool (defaults to SQLAlchemy's 10 if unset).",
    )
    pool_timeout: Optional[int] = Field(
        default=None,
        description="Seconds to wait for a connection from the pool before timing out.",
    )
    pool_recycle: Optional[int] = Field(
        default=None,
        description="Recycle connections after this many seconds (prevents stale TCP / server timeouts).",
    )
    pool_pre_ping: Optional[bool] = Field(
        default=None,
        description="Enable SQLAlchemy pool_pre_ping to evict stale connections.",
    )
    connect_args: Optional[dict[str, Any]] = Field(
        default=None, description="Optional connect_args passed to SQLAlchemy."
    )

    def dsn(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class PostgresTableConfig(BaseModel):
    # Allow reusing the same table-oriented config for local SQLite runs.
    type: Literal["postgres"]
    table: str = Field(..., description="Table name used by the store.")
    prefix: Optional[str] = Field(
        default=None, description="Optional prefix applied to the table name."
    )


class InMemoryStoreConfig(BaseModel):
    """
    Minimal config for in-memory stores (dev/test only).
    """

    type: Literal["memory"] = "memory"


class SQLStorageConfig(BaseModel):
    type: Literal["sql"] = "sql"
    driver: str
    mode: Literal["read_and_write", "read_only"]
    database: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = Field(default_factory=lambda: os.getenv("SQL_USERNAME"))
    password: Optional[str] = Field(default_factory=lambda: os.getenv("SQL_PASSWORD"))
    path: Optional[str] = None

    @model_validator(mode="after")
    def build_path(self) -> "SQLStorageConfig":
        if not self.driver:
            raise ValueError("Driver is required.")

        if self.path:
            # Facultatif : expanduser si tu veux supporter les "~"
            self.path = str(Path(self.path).expanduser())
        else:
            if not self.database:
                raise ValueError("Database name is required to build the path.")

            auth = ""
            if self.username:
                auth = self.username
                if self.password:
                    auth += f":{self.password}"
                auth += "@"

            host = self.host or "localhost"
            port = f":{self.port}" if self.port else ""
            self.path = f"{auth}{host}{port}/{self.database}"

        return self


StoreConfig = Annotated[
    Union[
        DuckdbStoreConfig,
        OpenSearchIndexConfig,
        SQLStorageConfig,
        LogStoreConfig,
        PostgresTableConfig,
        InMemoryStoreConfig,
    ],
    Field(discriminator="type"),
]
