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
from typing import Annotated, Any, Dict, Literal, Optional, Union
from urllib.parse import quote

from pydantic import BaseModel, Field, model_validator


class OwnerFilter(str, Enum):
    """Filter resources by ownership type.

    - PERSONAL: resources where the user is directly owner/editor/viewer (not via team)
    - TEAM: resources owned by a specific team (requires team_id parameter)
    """

    PERSONAL = "personal"
    TEAM = "team"


class BaseModelWithId(BaseModel):
    id: str


class TemporalSchedulerConfig(BaseModel):
    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "default"
    workflow_id_prefix: str = "task"
    connect_timeout_seconds: Optional[int] = 5
    rpc_timeout_seconds: Optional[int] = Field(
        default=10,
        description="Deadline applied to individual Temporal RPC calls (start_workflow, describe) "
        "so a stuck Temporal frontend cannot hang the caller indefinitely.",
    )
    ingestion_workflow_parallelism: int = Field(
        default=3,
        ge=1,
        description="Max number of files launched in parallel per parent ingestion workflow.",
    )
    ingestion_max_concurrent_workflow_tasks: int = Field(
        default=3,
        ge=1,
        description="Max concurrent Temporal workflow tasks processed by a worker process.",
    )
    ingestion_max_concurrent_activities: int = Field(
        default=3,
        ge=1,
        description="Max concurrent Temporal activities processed by a worker process.",
    )


class ModelConfiguration(BaseModel):
    provider: Optional[str] = Field(
        None, description="Provider of the AI model, e.g., openai, ollama, azure."
    )
    name: Optional[str] = Field(None, description="Model name, e.g., gpt-4o, llama2.")
    settings: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Additional provider-specific settings, "
            "e.g. Azure endpoint/API version or Vertex AI project/location."
        ),
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

    @model_validator(mode="after")
    def _require_password(self) -> "OpenSearchStoreConfig":
        """Fail fast at config load if OpenSearch is configured without credentials.

        Reaching this validator means a ``storage.opensearch`` block is present in
        the active configuration, so the service genuinely depends on OpenSearch.
        A missing password only surfaces later as an opaque HTTP 401 deep inside a
        request handler — we convert it into an actionable startup failure instead.
        """
        if not self.password:
            raise ValueError(
                f"OpenSearch is configured (host={self.host!r}, username="
                f"{self.username!r}) but no password was provided. "
                "Set the OPENSEARCH_PASSWORD environment variable (in your .env) "
                "to the OpenSearch password for this user, or remove the "
                "storage.opensearch block if OpenSearch is not used."
            )
        return self


class OpenSearchIndexConfig(BaseModel):
    type: Literal["opensearch"]
    index: str = Field(..., description="OpenSearch index name")


class LogStoreConfig(BaseModel):
    type: Literal["log"]
    level: str = Field(..., description="Logging level")


class DuckdbStoreConfig(BaseModel):
    type: Literal["duckdb"]
    duckdb_path: str = Field(..., description="Path to the DuckDB database file.")


# Password env var used by every service that talks to a single Postgres database.
# Per-database overrides go through PostgresStoreConfig.password_env.
DEFAULT_POSTGRES_PASSWORD_ENV = "FRED_POSTGRES_PASSWORD"  # nosec B105 # pragma: allowlist secret - env var name, not a secret


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
    password: Optional[str] = None
    password_env: Optional[str] = Field(
        default=None,
        description=(
            "Name of the environment variable holding this database's password. "
            "Unset means FRED_POSTGRES_PASSWORD. Set it only when one service "
            "connects to several Postgres databases under different roles."
        ),
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

    @model_validator(mode="after")
    def _resolve_password_from_env(self) -> "PostgresStoreConfig":
        """Fill ``password`` from the environment when the config does not carry one.

        Why: passwords are never written into config files — they arrive as env vars.
        A service that talks to a single database reads ``FRED_POSTGRES_PASSWORD``
        (unchanged behaviour). A service that talks to several databases under
        different roles sets ``password_env`` per block, e.g.::

            storage:
              postgres:                       # reads FRED_POSTGRES_PASSWORD
                database: fred
              task_postgres:
                database: knowledge_flow
                password_env: POSTGRES_KNOWLEDGE_FLOW_PASSWORD

        An explicit ``password`` in the config always wins — including an explicit
        ``None``, which means "no password", not "go and find one".

        This reproduces the semantics of the ``default_factory`` it replaced, which a
        plain ``if self.password is None`` would not:

        - it resolves only when the field was genuinely **unset**, so an explicit
          ``password=None`` stays ``None``;
        - it writes through ``__dict__`` rather than by attribute assignment, so the
          field does not join ``model_fields_set``. Assigning normally would make
          ``model_dump(exclude_unset=True)`` — "dump only what was configured" —
          start emitting the live secret for every backend using this model.
        """
        if "password" not in self.__pydantic_fields_set__:
            self.__dict__["password"] = os.getenv(
                self.password_env or DEFAULT_POSTGRES_PASSWORD_ENV
            )
        return self

    def _userinfo(self) -> str:
        """Percent-encoded ``user:password`` for the DSN's userinfo section.

        Credentials are operator-chosen and routinely contain URL-reserved characters.
        Interpolated raw, they do not fail loudly — they re-parse the URL: a password of
        ``p@ss/wo:rd`` makes everything after the first ``@`` look like the host, so the
        connection silently targets the wrong server with a truncated password.

        ``None`` becomes an empty password rather than the literal string ``"None"``.
        The engine factory rejects a missing password before it gets here, but
        ``dsn()`` is also consumed directly by ``PostgresEventBus``, which bypasses that
        factory — an empty password fails authentication loudly, ``"None"`` would be
        offered as a real one.
        """
        return f"{quote(self.username or '', safe='')}:{quote(self.password or '', safe='')}"

    def dsn(self) -> str:
        return (
            f"postgresql://{self._userinfo()}@{self.host}:{self.port}/{self.database}"
        )

    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self._userinfo()}@{self.host}:{self.port}/{self.database}"


class PostgresTableConfig(BaseModel):
    # Allow reusing the same table-oriented config for local SQLite runs.
    type: Literal["postgres"]
    table: Optional[str] = Field(
        default=None,
        description="Table name used by the store. Deprecated: stores now use fixed table names.",
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Optional prefix applied to the table name. Deprecated: stores now use fixed table names.",
    )


class InMemoryStoreConfig(BaseModel):
    """
    Minimal config for in-memory stores (dev/test only).
    """

    type: Literal["memory"] = "memory"


StoreConfig = Annotated[
    Union[
        DuckdbStoreConfig,
        OpenSearchIndexConfig,
        LogStoreConfig,
        PostgresTableConfig,
        InMemoryStoreConfig,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# KPI observability config — shared across all backends
# ---------------------------------------------------------------------------


class KpiLogSinkConfig(BaseModel):
    enabled: bool = False
    level: str = "info"
    summary_interval_sec: float = 0.0
    summary_top_n: int = 0


class KpiPrometheusSinkConfig(BaseModel):
    enabled: bool = True
    port: int = 9000
    address: str = "127.0.0.1"


class KpiOpenSearchSinkConfig(BaseModel):
    enabled: bool = True
    index: str = "kpi-index"


class KpiObservabilityConfig(BaseModel):
    """
    KPI sink configuration shared across all Fred backends.

    Defaults enable Prometheus + OpenSearch (prod-ready out of the box).
    For local dev, disable both and enable log instead:

        observability:
          kpi:
            log:
              enabled: true
            prometheus:
              enabled: false
            opensearch:
              enabled: false
    """

    log: KpiLogSinkConfig = Field(default_factory=KpiLogSinkConfig)
    prometheus: KpiPrometheusSinkConfig = Field(default_factory=KpiPrometheusSinkConfig)
    opensearch: KpiOpenSearchSinkConfig = Field(default_factory=KpiOpenSearchSinkConfig)
    process_metrics_interval_sec: int = Field(
        default=10,
        description="Emit process/SQL-pool KPIs every N seconds. 0 to disable.",
    )
