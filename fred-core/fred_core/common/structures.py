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
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field

class BaseModelWithId(BaseModel):
    id: str

class OpenSearchStoreConfig(BaseModel):
    host: str = Field(..., description="OpenSearch host URL")
    username: str = Field(..., description="Username from env")
    password: Optional[str] = Field(default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"), description="Password from env")
    secure: bool = Field(default=False, description="Use TLS (https)")
    verify_certs: bool = Field(default=False, description="Verify TLS certs")

class OpenSearchIndexConfig(BaseModel):
    type: Literal["opensearch"]
    index: str = Field(..., description="OpenSearch index name")

class DuckdbStoreConfig(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(...,description="Path to the DuckDB database file.")

class PostgresStoreConfig(BaseModel):
    host: str = Field(..., description="PostgreSQL host")
    port: int = 5432
    database: str
    username: str
    password: Optional[str] = Field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD"))

    def dsn(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

class PostgresTableConfig(BaseModel):
    type: Literal["postgres"]
    table: str

StoreConfig = Annotated[
    Union[DuckdbStoreConfig, PostgresTableConfig, OpenSearchIndexConfig],
    Field(discriminator="type")
]