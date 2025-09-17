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
from typing import Annotated, Literal, Optional, Union, Dict, Any

from pydantic import BaseModel, Field, model_validator


class BaseModelWithId(BaseModel):
    id: str

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
    host: str = Field(..., description="PostgreSQL host")
    port: int = 5432
    database: str
    username: str
    password: Optional[str] = Field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD")
    )

    def dsn(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class PostgresTableConfig(BaseModel):
    type: Literal["postgres"]
    table: str


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
        PostgresTableConfig,
        OpenSearchIndexConfig,
        SQLStorageConfig,
        LogStoreConfig,
    ],
    Field(discriminator="type"),
]
