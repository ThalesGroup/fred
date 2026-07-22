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
Shared runtime context used by fred-runtime adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_sdk.contracts.models import MCPServerConfiguration
from langchain_core.language_models.chat_models import BaseChatModel


class McpConfigurationLike(Protocol):
    """
    Minimal MCP configuration contract needed by runtime adapters.

    Why this exists:
    - runtime adapters must resolve MCP server references without depending on
      agentic-backend configuration classes

    How to use it:
    - provide an object with a `get_server(id)` method and a `servers` list
    """

    servers: list[MCPServerConfiguration]

    def get_server(self, id: str) -> MCPServerConfiguration | None:
        raise NotImplementedError


class InprocessToolkitFactory(Protocol):
    """
    Provider for in-process MCP toolkits.

    Why this exists:
    - fred-runtime should not hardcode agentic-backend toolkits

    How to use it:
    - supply a callable that maps a provider key + the current agent turn to a
      toolkit instance (the agent carries the bound runtime context and settings)
    """

    def __call__(self, provider: str | None, agent: Any) -> Any:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RuntimeTimeouts:
    """
    Minimal timeout settings for outbound runtime HTTP clients.

    Why this exists:
    - KF/MCP clients need consistent timeout settings across runtimes

    How to use it:
    - construct with explicit connect/read values
    - call `as_httpx_timeout_config()` to feed httpx
    """

    connect: float = 5.0
    read: float = 30.0
    write: float | None = None
    pool: float | None = None

    def as_httpx_timeout_config(self) -> dict[str, float | None]:
        """
        Convert to an httpx timeout configuration dict.

        Why this exists:
        - shared httpx client helpers expect explicit timeout dicts

        How to use it:
        - pass the return value to httpx.Timeout or compute_transport_tuning

        Example:
        ```python
        timeout_cfg = RuntimeTimeouts(connect=5, read=15).as_httpx_timeout_config()
        ```
        """

        return {
            "connect": float(self.connect),
            "read": float(self.read),
            "write": float(self.write if self.write is not None else self.read),
            "pool": float(self.pool if self.pool is not None else self.connect),
        }


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """
    Shared runtime configuration for fred-runtime adapters.

    Why this exists:
    - runtime adapters should not depend on agentic-backend config classes
    - this keeps external agent apps lightweight while still consistent

    How to use it:
    - populate with base URLs, timeout values, and optional providers
    """

    knowledge_flow_url: str
    service_name: str | None = None
    control_plane_url: str | None = None
    # Pod-side ReBAC engine (RUNTIME-07 rev. 2). The pod is the execution
    # authority: every execute/stream/evaluate/resume request is authorized here
    # against OpenFGA on the caller's team. Built from `security.rebac` at startup
    # via `rebac_factory`; a disabled/Noop engine means identity-only (dev). Typed
    # Any to avoid importing the engine here (it is `RebacEngine | None`).
    rebac_engine: Any | None = None
    # Hardened security profile name from `security.profile` (e.g. "c3"), or None.
    # Used to fail closed on direct agent_id execution under c3 (RUNTIME-07 F-D).
    security_profile: str | None = None
    timeouts: RuntimeTimeouts = field(default_factory=RuntimeTimeouts)
    kpi_writer: BaseKPIWriter = field(default_factory=NoOpKPIWriter)
    mcp_configuration: McpConfigurationLike | None = None
    chat_model_provider: Callable[[], BaseChatModel] | None = None
    chat_model_factory: Any | None = (
        None  # ChatModelFactoryPort — avoids circular import
    )
    checkpointer: Any | None = None  # FredSqlCheckpointer — avoids circular import
    history_store: Any | None = None  # PostgresHistoryStore — avoids circular import
    inprocess_toolkit_factory: InprocessToolkitFactory | None = None
    http_client_limits: Mapping[str, Any] | None = None


class RuntimeContext:
    """
    Runtime context shared by fred-runtime adapters.

    Why this exists:
    - provides a narrow API for adapters that used to rely on application_context

    How to use it:
    - construct from RuntimeConfig and set it with `set_runtime_context`
    """

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def get_knowledge_flow_base_url(self) -> str:
        """
        Return the Knowledge Flow base URL.

        Why this exists:
        - KF clients need a consistent base URL across runtimes

        How to use it:
        - call from runtime adapters when building KF clients
        """

        return self._config.knowledge_flow_url.rstrip("/")

    def get_kpi_writer(self) -> BaseKPIWriter:
        """
        Return the KPI writer for runtime metrics.

        Why this exists:
        - phase timing helpers require a concrete BaseKPIWriter
        """

        return self._config.kpi_writer

    def get_mcp_configuration(self) -> McpConfigurationLike | None:
        """
        Return the MCP configuration catalog, if provided.
        """

        return self._config.mcp_configuration

    def get_default_chat_model(self) -> BaseChatModel:
        """
        Return the default chat model for runtime execution.

        Why this exists:
        - v2 runtimes may require a global default model in simple deployments
        """

        if self._config.chat_model_provider is None:
            raise RuntimeError("RuntimeContext missing chat_model_provider.")
        return self._config.chat_model_provider()

    def get_inprocess_toolkit_factory(self) -> InprocessToolkitFactory | None:
        """
        Return the in-process toolkit factory, if configured.
        """

        return self._config.inprocess_toolkit_factory

    def get_http_client_limits(self) -> Mapping[str, Any] | None:
        """
        Return optional httpx client limits for shared KF clients.
        """

        return self._config.http_client_limits


_RUNTIME_CONTEXT: RuntimeContext | None = None


def set_runtime_context(context: RuntimeContext | None) -> None:
    """
    Set the global runtime context for fred-runtime adapters.

    Why this exists:
    - most adapters are used deep in agent execution paths where explicit
      dependency injection is impractical

    How to use it:
    - call once during app startup after configuration is loaded
    - `None` is accepted so tests can restore the pre-test state (including
      "never set") without reaching into the private `_RUNTIME_CONTEXT` global
    """

    global _RUNTIME_CONTEXT
    _RUNTIME_CONTEXT = context


def get_runtime_context() -> RuntimeContext:
    """
    Return the global runtime context.

    Why this exists:
    - adapters need a stable source of runtime configuration

    How to use it:
    - call only after `set_runtime_context` has been invoked
    """

    if _RUNTIME_CONTEXT is None:
        raise RuntimeError("RuntimeContext has not been initialized.")
    return _RUNTIME_CONTEXT
