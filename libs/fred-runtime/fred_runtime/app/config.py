# Copyright Thales 2026
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
"""
AgentPodConfig — structured YAML configuration for Fred agent pods.

Why this exists:
- Every agent pod (rags-v2 and future pods) needs the same configuration
  structure as agentic-backend: security, storage, scheduler, and AI settings.
- Using pydantic-settings env-var flat fields is not viable for production:
  security keys, store backends, and scheduler settings need structured config.
- This model is composed entirely from existing fred-core types so nothing is
  reinvented.

How to use it:
- Add a `config/configuration.yaml` to your pod (same format as agentic-backend).
- Call `load_agent_pod_config()` in `main.py` and pass the result to
  `create_agent_app(config=...)`.

Example `config/configuration.yaml`:
    app:
      name: "RAGS"
      base_url: "/rags/v1"
      port: 8000
      log_level: "info"

    security:
      m2m:
        enabled: false
        client_id: "rags"
        realm_url: "http://app-keycloak:8080/realms/app"
      user:
        enabled: false
        client_id: "app"
        realm_url: "http://app-keycloak:8080/realms/app"
      authorized_origins:
        - "http://localhost:5173"

    ai:
      knowledge_flow_url: "http://localhost:8111/knowledge-flow/v1"
      timeout:
        connect: 5
        read: 30

    storage:
      postgres:
        sqlite_path: "~/.fred/rags/rags.sqlite3"

    scheduler:
      enabled: false

"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from fred_core.common import (
    OpenSearchStoreConfig,
    PostgresStoreConfig,
    TemporalSchedulerConfig,
)
from fred_core.logs.log_structures import LogStorageConfig
from fred_core.scheduler.backend import SchedulerBackend
from fred_core.security.structure import SecurityConfiguration
from pydantic import BaseModel, Field, PrivateAttr

from ..runtime_context import RuntimeTimeouts

# ---------------------------------------------------------------------------
# App section
# ---------------------------------------------------------------------------


class PodAppConfig(BaseModel):
    """
    Basic HTTP server and local observability settings for an agent pod.

    Why this exists:
    - every pod needs the same HTTP binding knobs plus the small Prometheus/KPI
      settings already used by the other Fred backends
    - keeping these fields in `app` preserves the familiar startup contract for
      local benches and scrape-based debugging

    How to use it:
    - keep the defaults for simple local development
    - set `metrics_port` / `metrics_address` when `observability.metrics` is
      `prometheus`

    Example:
    - `PodAppConfig(base_url="/pod/v1", port=8000, metrics_port=9115)`
    """

    name: str = "Fred Agent Pod"
    base_url: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    metrics_address: str = "127.0.0.1"
    metrics_port: int = 9000
    kpi_process_metrics_interval_sec: int = Field(
        default=0,
        description=(
            "Emit process and SQL pool KPIs every N seconds. Set 0 to disable "
            "the background emitters."
        ),
    )
    kpi_log_summary_interval_sec: float = Field(
        default=0.0,
        description=(
            "Emit periodic KPI summary logs every N seconds for local benches. "
            "Set 0 to disable."
        ),
    )
    kpi_log_summary_top_n: int = Field(
        default=0,
        description="Top-N KPI summary rows to log. 0 means all / disabled.",
    )
    openai_compat: bool = True
    """
    Enable the OpenAI-compatible /v1/chat/completions and /v1/models endpoints.

    When True, the pod exposes:
      GET  /v1/models                — lists registered agents as OpenAI models
      POST /v1/chat/completions      — streaming chat completions (SSE)

    These endpoints are compatible with any OpenAI-protocol frontend
    (Open WebUI, openai-python SDK, etc.).  Fred-specific metadata (sources,
    citations, HITL) is carried in a top-level `fred` key on each SSE chunk
    and silently ignored by standard OpenAI clients.

    Enabled by default — agent pods should be reachable from any OpenAI-
    compatible client without explicit configuration.  Set to false in pods
    that should not advertise an OpenAI surface (e.g. internal workers).
    """


# ---------------------------------------------------------------------------
# AI section
# ---------------------------------------------------------------------------


class PodAIConfig(BaseModel):
    """
    AI model and knowledge-flow settings for an agent pod.

    Why this section exists separately from AgentAppSettings:
    - pods only need the outbound Knowledge Flow base URL plus runtime HTTP
      timeout tuning shared by KF and MCP adapters
    - gateway-only concerns such as attachment/session limits should not leak
      into the pod config contract

    Example:
    - `PodAIConfig(knowledge_flow_url="http://localhost:8111/knowledge-flow/v1", timeout=RuntimeTimeouts(connect=20, read=60))`
    """

    knowledge_flow_url: str = "http://localhost:8111/knowledge-flow/v1"
    timeout: RuntimeTimeouts = Field(
        default_factory=RuntimeTimeouts,
        description=(
            "Timeout settings for pod outbound HTTP calls to Knowledge Flow and "
            "other runtime adapters."
        ),
    )


# ---------------------------------------------------------------------------
# Observability section
# ---------------------------------------------------------------------------


class TracerBackend(str, Enum):
    """
    Distributed tracing backend for the agent pod.

    - null     — no tracing, all spans are dropped
    - logging  — each span is emitted as a structured log entry (default)
    - langfuse — spans are sent to a Langfuse server;
                 credentials (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY) must be
                 set in the .env file; host is configured in the langfuse section
    """

    null = "null"
    logging = "logging"
    langfuse = "langfuse"


class MetricsBackend(str, Enum):
    """
    Metrics emission backend for the agent pod.

    - null       — no metrics, all timer events are dropped
    - logging    — each timer is emitted as a structured log entry (default)
    - prometheus — KPI/process metrics are exported in Prometheus format on the
                   dedicated metrics port configured under `app`
    """

    null = "null"
    logging = "logging"
    prometheus = "prometheus"


class LangfuseObservabilityConfig(BaseModel):
    """
    Langfuse connection settings.

    Only non-secret settings live here.
    Credentials go in the .env file as LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.
    """

    host: str = "http://localhost:3001"


class PodObservabilityConfig(BaseModel):
    """
    Observability provider selection for a Fred agent pod.

    Non-secret settings (backend choice, endpoints) live in configuration.yaml.
    Credentials (API keys, tokens) stay in the .env file.

    Example:
        observability:
          tracer: logging       # null | logging | langfuse
          metrics: logging      # null | logging | prometheus
          langfuse:
            host: "http://localhost:3001"
            # LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env
    """

    tracer: TracerBackend = TracerBackend.logging
    metrics: MetricsBackend = MetricsBackend.logging
    langfuse: LangfuseObservabilityConfig = Field(
        default_factory=LangfuseObservabilityConfig
    )


# ---------------------------------------------------------------------------
# Storage section
# ---------------------------------------------------------------------------


class PodStorageConfig(BaseModel):
    """
    Persistence backend settings for an agent pod.

    All conversation state (sessions, multi-turn history, checkpoints) is
    managed exclusively by the LangGraph SQL checkpointer, which uses the
    `postgres` connection. There are no separate session or history tables.

    Fields:
    - `postgres`: SQL engine used by the LangGraph checkpointer (SQLite in
      local dev via sqlite_path, PostgreSQL in production via host/port/database)
    - `opensearch`: optional, for log forwarding in production
    - `log_store`: optional, for structured log persistence
    """

    postgres: PostgresStoreConfig = Field(
        default_factory=lambda: PostgresStoreConfig(
            sqlite_path="~/.fred/pod/pod.sqlite3"
        )
    )
    opensearch: Optional[OpenSearchStoreConfig] = None
    log_store: Optional[LogStorageConfig] = None


# ---------------------------------------------------------------------------
# Scheduler section
# ---------------------------------------------------------------------------


class PodSchedulerConfig(BaseModel):
    """
    Temporal scheduler settings for an agent pod.

    Disabled by default — only needed for Story B (deep/durable agents).
    Reuses TemporalSchedulerConfig from fred-core.
    """

    enabled: bool = False
    backend: SchedulerBackend = SchedulerBackend.TEMPORAL
    temporal: TemporalSchedulerConfig = Field(default_factory=TemporalSchedulerConfig)


class PodPlatformConfig(BaseModel):
    """
    Small set of Fred platform service URLs needed by the pod runtime.

    Why this exists:
    - agent pods stay execution-focused, but some execution paths still need a
      central Fred service such as control-plane for managed agent-instance
      resolution

    How to use it:
    - set `control_plane_url` when the pod should accept `agent_instance_id`
      execution requests

    Example:
    - `PodPlatformConfig(control_plane_url="http://localhost:8222/control-plane/v1")`
    """

    control_plane_url: str | None = None


class AgentPodConfig(BaseModel):
    """
    Complete structured configuration for a Fred agent pod.

    Mirrors agentic-backend's `Configuration` model, scoped to what an agent
    pod actually needs. All field types are reused from fred-core and fred-sdk
    — no new types invented here.

    How to use it:
    - write a `config/configuration.yaml` alongside `config/models_catalog.yaml`
      and `config/mcp_catalog.yaml`
    - call `load_agent_pod_config()` at startup
    - pass the result to `create_agent_app(config=...)`

    The `security` field is a `SecurityConfiguration` from fred-core, the same
    type used in agentic-backend. When `security.user.enabled` is True,
    `create_agent_app` enforces Keycloak JWT validation on every endpoint.
    """

    _models_catalog_path: str | None = PrivateAttr(default=None)
    _mcp_configuration: Any | None = PrivateAttr(default=None)

    app: PodAppConfig = Field(default_factory=PodAppConfig)
    security: SecurityConfiguration
    ai: PodAIConfig = Field(default_factory=PodAIConfig)
    observability: PodObservabilityConfig = Field(
        default_factory=PodObservabilityConfig
    )
    storage: PodStorageConfig = Field(default_factory=PodStorageConfig)
    scheduler: PodSchedulerConfig = Field(default_factory=PodSchedulerConfig)
    platform: PodPlatformConfig = Field(default_factory=PodPlatformConfig)

    def set_models_catalog_path(self, path: str) -> None:
        """
        Attach the resolved models catalog path as internal runtime data.

        Why this exists:
        - pod startup should treat `models_catalog.yaml` as mandatory without
          exposing its path as a public config field in `configuration.yaml`

        How to use it:
        - call only from internal config bootstrap helpers after resolving the
          canonical catalog path

        Example:
        - `config.set_models_catalog_path("./config/models_catalog.yaml")`
        """

        self._models_catalog_path = path

    def get_models_catalog_path(self) -> str | None:
        """
        Return the resolved models catalog path attached during pod bootstrap.

        Why this exists:
        - runtime model-routing wiring must know the resolved catalog path while
          keeping that path out of the public Pydantic schema

        How to use it:
        - call from internal runtime wiring only

        Example:
        - `catalog_path = config.get_models_catalog_path()`
        """

        return self._models_catalog_path

    def set_mcp_configuration(self, configuration: Any | None) -> None:
        """
        Attach the resolved MCP catalog to this config as internal runtime data.

        Why this exists:
        - pod startup should keep `mcp_catalog.yaml` as the single MCP source of
          truth without exposing an `mcp` section in the public config schema

        How to use it:
        - call only from internal config bootstrap helpers after loading the
          external MCP catalog

        Example:
        - `config.set_mcp_configuration(resolved_mcp_catalog)`
        """

        self._mcp_configuration = configuration

    def get_mcp_configuration(self) -> Any | None:
        """
        Return the resolved MCP catalog attached during pod bootstrap.

        Why this exists:
        - `create_agent_app()` needs access to the loaded MCP configuration
          while `AgentPodConfig` keeps that catalog out of the public YAML model

        How to use it:
        - call from internal runtime wiring only; pod code should normally just
          pass `AgentPodConfig` through unchanged

        Example:
        - `mcp_configuration = config.get_mcp_configuration()`
        """

        return self._mcp_configuration
