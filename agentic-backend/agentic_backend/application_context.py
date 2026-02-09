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

"""
Centralized application context singleton to store and manage global application configuration and runtime state.

Includes:
- Configuration access
- Runtime status (e.g., offline mode)
- AI model accessors
- Dynamic agent class loading and access
- Context service management
"""

import asyncio
import atexit
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from fred_core import (
    BaseLogStore,
    BearerAuth,
    ClientCredentialsProvider,
    DuckdbStoreConfig,
    InMemoryLogStorageConfig,
    LogStoreConfig,
    OpenFgaRebacConfig,
    OpenSearchIndexConfig,
    OpenSearchLogStore,
    PostgresTableConfig,
    RamLogStore,
    RebacEngine,
    SQLStorageConfig,
    get_model,
    rebac_factory,
    split_realm_url,
)
from fred_core.kpi import (
    BaseKPIStore,
    KPIDefaults,
    KpiLogStore,
    KPIWriter,
    OpenSearchKPIStore,
    PrometheusKPIStore,
)
from fred_core.logs.log_structures import StdoutLogStorageConfig
from fred_core.logs.null_log_store import NullLogStore
from fred_core.scheduler import TemporalClientProvider
from fred_core.sql import create_async_engine_from_config
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from requests.auth import AuthBase
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.common.structures import (
    Configuration,
    McpConfiguration,
)
from agentic_backend.core.agents.store.base_agent_store import BaseAgentStore
from agentic_backend.core.feedback.store.base_feedback_store import BaseFeedbackStore
from agentic_backend.core.feedback.store.postgres_feedback_store import (
    PostgresFeedbackStore,
)
from agentic_backend.core.mcp.mcp_server_manager import McpServerManager
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore
from agentic_backend.core.mcp.store.postgres_mcp_server_store import (
    PostgresMcpServerStore,
)
from agentic_backend.core.monitoring.base_history_store import BaseHistoryStore
from agentic_backend.core.monitoring.postgres_history_store import PostgresHistoryStore
from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
)
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore
from agentic_backend.core.session.stores.postgres_session_attachment_store import (
    PostgresSessionAttachmentStore,
)
from agentic_backend.core.session.stores.postgres_session_store import (
    PostgresSessionStore,
)
from agentic_backend.scheduler.store.base_task_store import BaseAgentTaskStore

logger = logging.getLogger(__name__)


def _mask(value: Optional[str], left: int = 4, right: int = 4) -> str:
    if not value:
        return "<empty>"
    if len(value) <= left + right:
        return "<hidden>"
    return f"{value[:left]}…{value[-right:]}"


def _looks_like_jwt(token: str) -> bool:
    # Very light heuristic: three base64url segments
    return bool(
        token
        and token.count(".") == 2
        and re.match(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$", token)
        is not None
    )


class NoAuth(AuthBase):
    """No-op requests auth (adds no headers)."""

    def __call__(self, r):
        return r

    def auth_header(self) -> Optional[str]:
        return None


@dataclass(frozen=True)
class OutboundAuth:
    auth: AuthBase
    refresh: Optional[Callable[[], None]] = None  # None = nothing to refresh


# -------------------------------
# Public access helper functions
# -------------------------------


def get_configuration() -> Configuration:
    """
    Retrieves the global application configuration.

    Returns:
        Configuration: The singleton application configuration.
    """
    return get_app_context().configuration


def get_session_store() -> BaseSessionStore:
    return get_app_context().get_session_store()


def get_session_attachment_store() -> Optional[BaseSessionAttachmentStore]:
    return get_app_context().get_session_attachment_store()


def get_mcp_configuration() -> McpConfiguration:
    return get_app_context().get_mcp_configuration()


def get_knowledge_flow_base_url() -> str:
    return get_app_context().get_knowledge_flow_base_url()


def get_history_store() -> BaseHistoryStore:
    return get_app_context().get_history_store()


def get_kpi_writer() -> KPIWriter:
    return get_app_context().get_kpi_writer()


def pg_async_tx():
    """
    Convenience helper to open a short async Postgres transaction using the
    shared async engine. Usage:

        async with pg_async_tx() as conn:
            ...

    This allows callers to update cleanly one or two tables in a single transaction without needing to manage the connection or transaction scope themselves.
    """
    return get_app_context().begin_pg_transaction()


def get_rebac_engine() -> RebacEngine:
    """Expose the shared ReBAC engine instance."""

    return get_app_context().get_rebac_engine()


def get_agent_store() -> BaseAgentStore:
    return get_app_context().get_agent_store()


async def get_mcp_server_manager() -> "McpServerManager":
    return await get_app_context().get_mcp_server_manager()


def get_feedback_store() -> BaseFeedbackStore:
    return get_app_context().get_feedback_store()


def get_task_store() -> BaseAgentTaskStore:
    return get_app_context().get_task_store()


def get_temporal_client_provider() -> TemporalClientProvider:
    return get_app_context().get_temporal_client_provider()


def get_enabled_agent_names() -> List[str]:
    """
    Retrieves a list of enabled agent names from the application context.

    Returns:
        List[str]: List of enabled agent names.
    """
    return get_app_context().get_enabled_agent_names()


def get_app_context() -> "ApplicationContext":
    """
    Retrieves the global application context instance.

    Returns:
        ApplicationContext: The singleton application context.

    Raises:
        RuntimeError: If the context has not been initialized yet.
    """
    if ApplicationContext._instance is None:
        raise RuntimeError("ApplicationContext is not yet initialized")
    return ApplicationContext._instance


def get_default_model() -> BaseLanguageModel:
    """
    Retrieves the default AI model instance.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        BaseLanguageModel: The AI model configured for the agent.
    """
    return get_app_context().get_default_model()


def get_default_chat_model() -> BaseChatModel:
    """
    Retrieves the default chat model instance.

    You can use this function in agents that always want to use the globally configured chat model.
    If this is not desired, use get_model() with the agent's specific model tunings.

    Returns:
        BaseChatModel: The global chat model.
    """
    return get_app_context().get_default_chat_model()


# -------------------------------
# Runtime status class
# -------------------------------


class RuntimeStatus:
    """
    Manages runtime status of the application, such as offline mode.
    Thread-safe implementation.
    """

    def __init__(self):
        self._offline = False
        self._lock = Lock()

    @property
    def offline(self) -> bool:
        with self._lock:
            return self._offline

    def enable_offline(self):
        with self._lock:
            self._offline = True

    def disable_offline(self):
        with self._lock:
            self._offline = False


# -------------------------------
# Application context singleton
# -------------------------------


class ApplicationContext:
    """
    Singleton class to hold application-wide configuration and runtime state.

    Attributes:
        configuration (Configuration): Loaded application configuration.
        status (RuntimeStatus): Runtime status (e.g., offline mode).
        agent_classes (Dict[str, Type[AgentFlow]]): Mapping of agent names to their Python classes.
    """

    _instance = None
    _lock = Lock()
    configuration: Configuration
    status: RuntimeStatus
    _service_instances: Dict[str, Any]
    _feedback_store_instance: Optional[BaseFeedbackStore] = None
    _agent_store_instance: Optional[BaseAgentStore] = None
    _task_store_instance: Optional[BaseAgentTaskStore] = None
    _mcp_server_store_instance: Optional[BaseMcpServerStore] = None
    _mcp_server_manager: Optional[McpServerManager] = None
    _session_store_instance: Optional[BaseSessionStore] = None
    _session_attachment_store_instance: Optional[BaseSessionAttachmentStore] = None
    _history_store_instance: Optional[BaseHistoryStore] = None
    _kpi_store_instance: Optional[BaseKPIStore] = None
    _log_store_instance: Optional[BaseLogStore] = None
    _outbound_auth: OutboundAuth | None = None
    _kpi_writer: Optional[KPIWriter] = None
    _rebac_engine: Optional[RebacEngine] = None
    _io_executor: ThreadPoolExecutor | None = None
    _default_chat_model_instance: Optional[BaseChatModel] = None
    _default_model_instance: Optional[BaseLanguageModel] = None
    _pg_engine: Optional[Engine] = None
    _pg_async_engine: Optional[AsyncEngine] = None
    _temporal_provider: Optional[TemporalClientProvider] = None

    def __new__(cls, configuration: Configuration):
        with cls._lock:
            if cls._instance is None:
                if configuration is None:
                    raise ValueError(
                        "ApplicationContext must be initialized with a configuration first."
                    )
                cls._instance = super().__new__(cls)

                # Store configuration and runtime status
                cls._instance.configuration = configuration
                cls._instance.status = RuntimeStatus()
                cls._instance._service_instances = {}  # Cache for service instances
                cls._instance._log_config_summary()
                cls._instance._io_executor = ThreadPoolExecutor(max_workers=10)
                cls._instance._pg_engine = None

            return cls._instance

    async def run_in_executor(self, func, *args):
        """
        Runs a synchronous (blocking) function in the shared thread pool.

        This method correctly retrieves the event loop and uses the loop's
        run_in_executor method, which is the proper asyncio pattern.
        """
        if self._io_executor is None:
            raise RuntimeError("IO executor not initialized")
        # 2. Get the active asyncio event loop
        loop = asyncio.get_event_loop()

        # 3. Call the event loop's run_in_executor method.
        # This is the awaitable call that runs 'func' in a separate thread.
        return await loop.run_in_executor(
            self._io_executor,  # The ThreadPoolExecutor instance
            func,  # The synchronous function (e.g., fetch_asset_content_text)
            *args,  # Arguments for the function
        )

    def get_io_executor(self) -> ThreadPoolExecutor:
        if self._io_executor is None:
            raise RuntimeError("IO executor not initialized")
        return self._io_executor

    def shutdown_io_executor(self):
        if self._io_executor is not None:
            self._io_executor.shutdown(wait=True)
            self._io_executor = None

    async def shutdown(self):
        """Gracefully shut down global resources."""
        # HTTP clients (LLM / external calls)
        try:
            from fred_core.model import http_clients

            await http_clients.async_shutdown_shared_clients()
        except Exception:
            logger.warning("[HTTP] Failed to shutdown shared clients", exc_info=True)

        # Async PG engine
        if self._pg_async_engine is not None:
            try:
                await self._pg_async_engine.dispose()
            finally:
                self._pg_async_engine = None

        # Thread pool executor
        self.shutdown_io_executor()

    def get_knowledge_flow_base_url(self) -> str:
        """
        Retrieves the base URL for the knowledge flow service.
        """
        return self.configuration.ai.knowledge_flow_url

    # --- AI Models ---

    def get_default_chat_model(self) -> BaseChatModel:
        """
        Retrieves the default chat model instance.
        """
        if self._default_chat_model_instance is None:
            self._default_chat_model_instance = get_model(
                self.configuration.ai.default_chat_model
            )
            logger.info(
                "[MODEL] cached default chat model instance %s",
                type(self._default_chat_model_instance).__name__,
            )
        return self._default_chat_model_instance

    def get_default_model(self) -> BaseLanguageModel:
        """
        Retrieves the default AI model instance.
        """
        if self.configuration.ai.default_language_model is None:
            logger.warning(
                "[DEPRECATION] No default language model configured; falling back to default chat model."
            )
            logger.info(
                "Please set 'default_language_model' in the AI configuration to avoid this warning."
            )
            return self.get_default_chat_model()
        if self._default_model_instance is None:
            self._default_model_instance = get_model(
                self.configuration.ai.default_language_model
            )
            logger.info(
                "[MODEL] cached default language model instance %s",
                type(self._default_model_instance).__name__,
            )
        return self._default_model_instance

    # --- Agent classes ---

    def get_enabled_agent_names(self) -> List[str]:
        """
        Retrieves a list of enabled agent names from the configuration.

        Returns:
            List[str]: List of enabled agent names.
        """
        return [agent.name for agent in self.configuration.ai.agents if agent.enabled]

    def get_pg_async_engine(self):
        """
        Lazily create and cache a single async Postgres Engine for all the postgres async stores.
        """
        if self._pg_async_engine is None:
            pg_cfg = self.configuration.storage.postgres
            self._pg_async_engine = create_async_engine_from_config(pg_cfg)
            engine = self._pg_async_engine

            def _dispose_async_engine():
                try:
                    asyncio.run(engine.dispose())
                except Exception:
                    logger.debug(
                        "[SQL] Async engine dispose at exit failed", exc_info=True
                    )

            atexit.register(_dispose_async_engine)
            logger.info("[SQL] Shared Postgres async initialized.")
        return self._pg_async_engine

    def begin_pg_transaction(self):
        """
        Returns an async context manager for a short Postgres transaction
        using the shared async engine.
        """
        return self.get_pg_async_engine().begin()

    def get_session_store(self) -> BaseSessionStore:
        """
        Factory function to create a sessions store instance based on the configuration.
        As of now, it supports in_memory and OpenSearch sessions storage.

        Returns:
            AbstractSessionStorage: An instance of the sessions store.
        """
        if self._session_store_instance is not None:
            return self._session_store_instance

        store_config = get_configuration().storage.session_store
        if isinstance(store_config, PostgresTableConfig):
            return PostgresSessionStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
        raise ValueError("Unsupported sessions storage backend (async-only)")

    def get_session_attachment_store(self) -> Optional[BaseSessionAttachmentStore]:
        """
        Optional persistence for session attachment summaries.
        Must be explicitly configured; no implicit reuse of the session store.
        """
        if self._session_attachment_store_instance is not None:
            return self._session_attachment_store_instance

        storage_cfg = get_configuration().storage
        store_config = storage_cfg.attachments_store
        if store_config is None:
            raise ValueError(
                "attachments_store must be explicitly configured; implicit reuse of session_store is no longer supported."
            )

        if isinstance(store_config, PostgresTableConfig):
            table_name = (
                store_config.table
                if storage_cfg.attachments_store is not None
                else f"{store_config.table}_attachments"
            )
            self._session_attachment_store_instance = PostgresSessionAttachmentStore(
                engine=self.get_pg_async_engine(),
                table_name=table_name,
                prefix=store_config.prefix or "",
            )
            return self._session_attachment_store_instance

        logger.info(
            "[SESSIONS] Attachment persistence is disabled for backend=%s.",
            store_config.type,
        )
        self._session_attachment_store_instance = None
        return None

    def get_log_store(self) -> BaseLogStore:
        """
        Factory function to get the appropriate log storage backend based on configuration.
        Returns:
            BaseLogStore: An instance of the log storage backend.
        """
        if self._log_store_instance is not None:
            return self._log_store_instance

        config = self.configuration.storage.log_store
        if isinstance(config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            if opensearch_config is None:
                raise ValueError(
                    "OpenSearch configuration is required but not provided"
                )
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")

            self._log_store_instance = OpenSearchLogStore(
                host=opensearch_config.host,
                index=config.index,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
            )
        elif isinstance(config, StdoutLogStorageConfig):
            self._log_store_instance = NullLogStore()
        elif isinstance(config, InMemoryLogStorageConfig) or config is None:
            self._log_store_instance = RamLogStore(
                capacity=1000
            )  # Default to in-memory store if not configured
        else:
            raise ValueError("Log store configuration is missing or invalid")

        return self._log_store_instance

    def get_history_store(self) -> BaseHistoryStore:
        """
        Factory function to create a sessions store instance based on the configuration.
        As of now, it supports in_memory and OpenSearch sessions storage.

        Returns:
            AbstractSessionStorage: An instance of the sessions store.
        """
        if self._history_store_instance is not None:
            return self._history_store_instance
        store_config = get_configuration().storage.history_store
        if isinstance(store_config, PostgresTableConfig):
            self._history_store_instance = PostgresHistoryStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
            logger.info(
                "[HISTORY][STORE] Using Postgres backend table=%s prefix=%s",
                store_config.table,
                store_config.prefix or "",
            )
            return self._history_store_instance
        else:
            raise ValueError("Unsupported history storage backend (async-only)")

    def get_kpi_store(self) -> BaseKPIStore:
        if self._kpi_store_instance is not None:
            return self._kpi_store_instance

        store_config = get_configuration().storage.kpi_store
        if isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            if opensearch_config is None:
                raise ValueError(
                    "OpenSearch configuration is required but not provided"
                )
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            store: BaseKPIStore = OpenSearchKPIStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        elif isinstance(store_config, LogStoreConfig):
            store = KpiLogStore(level=store_config.level)
        else:
            raise ValueError("Unsupported KPI storage backend")
        self._kpi_store_instance = PrometheusKPIStore(delegate=store)
        return self._kpi_store_instance

    def get_task_store(self):
        if self._task_store_instance is not None:
            return self._task_store_instance
        store_config = get_configuration().storage.task_store
        if isinstance(store_config, PostgresTableConfig):
            from agentic_backend.scheduler.store.postgres_task_store import (
                PostgresAgentTaskStore,
            )

            self._task_store_instance = PostgresAgentTaskStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
            return self._task_store_instance
        raise ValueError(f"Unsupported tasks storage backend {type(store_config)}")

    def get_temporal_client_provider(self) -> TemporalClientProvider:
        if self._temporal_provider is not None:
            return self._temporal_provider

        cfg = get_configuration().scheduler
        if cfg.backend.lower() != "temporal":
            raise RuntimeError(
                f"Temporal client requested but scheduler backend is {cfg.backend}"
            )

        self._temporal_provider = TemporalClientProvider(cfg.temporal)
        return self._temporal_provider

    def get_agent_store(self) -> BaseAgentStore:
        """
        Factory function to create a sessions store instance based on the configuration.
        As of now, it supports in_memory and OpenSearch sessions storage.

        Returns:
            AbstractSessionStorage: An instance of the sessions store.
        """
        if self._agent_store_instance is not None:
            return self._agent_store_instance

        store_config = get_configuration().storage.agent_store
        if isinstance(store_config, PostgresTableConfig):
            from agentic_backend.core.agents.store.postgres_agent_store import (
                PostgresAgentStore,
            )

            return PostgresAgentStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
        else:
            raise ValueError(
                f"Unsupported sessions storage backend {type(store_config)}"
            )

    def get_mcp_server_store(self) -> BaseMcpServerStore:
        """
        Factory for the MCP servers persistent store. Falls back to the agent store
        backend if no explicit mcp_servers_store is provided.
        """
        if self._mcp_server_store_instance is not None:
            return self._mcp_server_store_instance

        store_config = (
            get_configuration().storage.mcp_servers_store
            or get_configuration().storage.agent_store
        )

        if isinstance(store_config, PostgresTableConfig):
            self._mcp_server_store_instance = PostgresMcpServerStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
            return self._mcp_server_store_instance
        raise ValueError(
            f"Unsupported MCP servers storage backend {type(store_config)}"
        )

    def get_mcp_configuration(self) -> McpConfiguration:
        return self.configuration.mcp

    async def get_mcp_server_manager(self) -> McpServerManager:
        """
        Lazily create the MCP server manager using the configured store.
        """
        if self._mcp_server_manager is not None:
            return self._mcp_server_manager

        manager = McpServerManager(
            config=self.configuration, store=self.get_mcp_server_store()
        )
        await manager.bootstrap()
        self._mcp_server_manager = manager
        return manager

    def get_kpi_writer(self) -> KPIWriter:
        if self._kpi_writer is not None:
            return self._kpi_writer

        self._kpi_writer = KPIWriter(
            store=self.get_kpi_store(),
            defaults=KPIDefaults(static_dims={"service": "agentic"}),
            summary_interval_s=self.configuration.app.kpi_log_summary_interval_sec,
            summary_top_n=self.configuration.app.kpi_log_summary_top_n,
        )
        return self._kpi_writer

    def get_feedback_store(self) -> BaseFeedbackStore:
        """
        Retrieve the configured agent store. It is used to save all the configured or
        dynamically created agents

        Returns:
            BaseDynamicAgentStore: An instance of the dynamic agents store.
        """
        if self._feedback_store_instance is not None:
            return self._feedback_store_instance

        store_config = get_configuration().storage.feedback_store
        if isinstance(store_config, PostgresTableConfig):
            self._feedback_store_instance = PostgresFeedbackStore(
                engine=self.get_pg_async_engine(),
                table_name=store_config.table,
                prefix=store_config.prefix or "",
            )
            return self._feedback_store_instance
        raise ValueError("Unsupported sessions storage backend")

    def get_outbound_auth(self) -> OutboundAuth:
        """
        Get the client credentials provider for outbound requests.
        This will return a BearerAuth instance if the security is enabled. If not, it will return a NoAuth instance.
        """
        if self._outbound_auth is not None:
            return self._outbound_auth

        sec = self.configuration.security.m2m
        if not sec.enabled:
            self._outbound_auth = OutboundAuth(auth=NoAuth(), refresh=None)
            return self._outbound_auth

        keycloak_base, realm = split_realm_url(str(sec.realm_url))
        client_id = sec.client_id
        try:
            client_secret = os.environ.get("KEYCLOAK_AGENTIC_CLIENT_SECRET")
        except KeyError:
            raise RuntimeError(
                "Missing client secret env var 'KEYCLOAK_AGENTIC_CLIENT_SECRET'."
            )
        if not client_secret:
            raise ValueError("Client secret is empty.")
        provider = ClientCredentialsProvider(
            keycloak_base=keycloak_base,
            realm=realm,
            client_id=client_id,
            client_secret=client_secret,
        )
        self._outbound_auth = OutboundAuth(
            auth=BearerAuth(provider),
            refresh=provider.force_refresh,
        )
        return self._outbound_auth

    def get_rebac_engine(self) -> RebacEngine:
        if self._rebac_engine is None:
            self._rebac_engine = rebac_factory(self.configuration.security)

        return self._rebac_engine

    def _log_config_summary(self) -> None:
        """
        Log a crisp, admin-friendly summary of the Agentic configuration and warn on common mistakes.
        Does NOT print secrets; only presence/masked hints.
        """
        cfg = self.configuration
        logger.info("🔧 Agentic configuration summary")
        logger.info("────────────────────────────────────────────────────────────────")

        # App basics
        logger.info("  🏷️  App: %s", cfg.app.name or "Agentic Backend")
        logger.info("  🌐  Base URL: %s", cfg.app.base_url)
        logger.info(
            "  🖥️  Bind: %s:%s  (log_level=%s, reload=%s)",
            cfg.app.address,
            cfg.app.port,
            cfg.app.log_level,
            cfg.app.reload,
        )

        # Knowledge Flow target
        kf_url = (cfg.ai.knowledge_flow_url or "").strip()
        logger.info("  📡 Knowledge Flow URL: %s", kf_url or "<missing>")
        if not kf_url:
            logger.error(
                "     ❌ Missing ai.knowledge_flow_url — outbound calls will fail."
            )
        elif not (kf_url.startswith("http://") or kf_url.startswith("https://")):
            logger.error(
                "     ❌ knowledge_flow_url must start with http:// or https://"
            )
        # Light suggestion about expected path (non-blocking)
        if kf_url and "/knowledge-flow/v1" not in kf_url:
            logger.warning(
                "     ⚠️ URL doesn't contain '/knowledge-flow/v1' — double-check the base."
            )

        # Timeouts
        tcfg = cfg.ai.timeout
        logger.info(
            "  ⏱️  Rest Call Timeouts: connect=%ss, read=%ss", tcfg.connect, tcfg.read
        )

        # Agents
        enabled_agents = [a.name for a in cfg.ai.agents if a.enabled]
        logger.info(
            "  🤖 Agents enabled: %d%s",
            len(enabled_agents),
            f"  ({', '.join(enabled_agents)})" if enabled_agents else "",
        )

        # Storage overview (mirrors the backends you instantiate later)
        try:
            st = cfg.storage
            logger.info("  🗄️  Storage:")

            def _describe(label: str, store_cfg):
                if isinstance(store_cfg, DuckdbStoreConfig):
                    logger.info(
                        "     • %-14s DuckDB  path=%s", label, store_cfg.duckdb_path
                    )
                elif isinstance(store_cfg, OpenSearchIndexConfig):
                    os_cfg = cfg.storage.opensearch
                    if os_cfg is None:
                        return
                    logger.info(
                        "     • %-14s OpenSearch host=%s index=%s secure=%s verify=%s",
                        label,
                        os_cfg.host,
                        store_cfg.index,
                        os_cfg.secure,
                        os_cfg.verify_certs,
                    )
                elif isinstance(store_cfg, SQLStorageConfig):
                    # Generic SQL storage (could be MySQL, MariaDB, etc.)
                    logger.info(
                        "     • %-14s SQLStorage  dsn=%s  table=%s",
                        label,
                        getattr(store_cfg, "dsn", "<unset>"),
                        getattr(store_cfg, "table_name", "<unset>"),
                    )
                elif isinstance(store_cfg, LogStoreConfig):
                    # No-op KPI / log-only store
                    logger.info(
                        "     • %-14s No-op / LogStore  level=%s  (logs only, no persistence)",
                        label,
                        getattr(store_cfg, "level", "INFO"),
                    )
                else:
                    logger.info("     • %-14s %s", label, type(store_cfg).__name__)

            _describe("agent_store", st.agent_store)
            _describe("mcp_servers_store", st.mcp_servers_store)
            _describe("session_store", st.session_store)
            _describe("history_store", st.history_store)
            _describe("feedback_store", st.feedback_store)
            _describe("kpi_store", st.kpi_store)
        except Exception:
            logger.warning(
                "  ⚠️ Failed to read storage section (some variables may be missing)."
            )

        # Inbound security (UI -> Agentic)
        user_sec = cfg.security.user
        logger.info("  🔒 Inbound security (UI → Agentic):")
        logger.info("     • enabled: %s", user_sec.enabled)
        logger.info("     • client_id: %s", user_sec.client_id or "<unset>")
        logger.info("     • keycloak_url: %s", user_sec.realm_url or "<unset>")
        # realm parsing
        try:
            base, realm = split_realm_url(str(user_sec.realm_url))
            logger.info("     • realm: %s  (base=%s)", realm, base)
        except Exception as e:
            logger.error(
                "     ❌ keycloak_url invalid (expected …/realms/<realm>): %s", e
            )

        # Heuristic warnings on client_id naming
        if user_sec.client_id == "agentic":
            logger.warning(
                "     ⚠️ user client_id is 'agentic'. Reserve 'agentic' for M2M client; "
                "UI should usually use a client like 'app'."
            )

        # Outbound S2S (Agentic → Knowledge Flow)
        m2m_sec = cfg.security.m2m
        logger.info("  🔑 Outbound S2S (Agentic → Knowledge Flow):")
        logger.info("     • enabled: %s", m2m_sec.enabled)
        logger.info("     • client_id: %s", m2m_sec.client_id or "<unset>")
        logger.info("     • keycloak_url: %s", m2m_sec.realm_url or "<unset>")

        secret = os.getenv("KEYCLOAK_AGENTIC_CLIENT_SECRET", "")
        if secret:
            logger.info(
                "     • KEYCLOAK_AGENTIC_CLIENT_SECRET: present  (%s)", _mask(secret)
            )
        else:
            logger.warning(
                "     ⚠️ KEYCLOAK_AGENTIC_CLIENT_SECRET is not set — outbound calls will be unauthenticated "
                "(NoAuth). Knowledge Flow will likely return 401."
            )

        # Relationship between inbound 'enabled' and outbound needs
        if not m2m_sec.enabled and secret:
            logger.info(
                "     • Note: M2M security is disabled, but S2S secret is present. "
                "Outbound calls will still include a bearer if your code enables it."
            )

        # Final tips / quick misconfig guards
        if secret and m2m_sec.client_id and m2m_sec.client_id != "agentic":
            logger.warning(
                "     ⚠️ Secret is present but M2M client_id is '%s' (expected 'agentic' for S2S). "
                "Ensure client_id matches the secret you provisioned.",
                m2m_sec.client_id,
            )

        rebac_cfg = cfg.security.rebac
        if rebac_cfg and rebac_cfg.enabled:
            # Print rebac type
            logger.info("  🕸️ Rebac Enabled:")
            logger.info("     • Type: %s", rebac_cfg.type)
            if isinstance(rebac_cfg, OpenFgaRebacConfig):
                logger.info("     • API URL: %s", rebac_cfg.api_url)
                logger.info("     • Store Name: %s", rebac_cfg.store_name)
                logger.info(
                    "     • Sync Schema on Init: %s", rebac_cfg.sync_schema_on_init
                )
                logger.info(
                    "     • Create Store if Needed: %s",
                    rebac_cfg.create_store_if_needed,
                )
        else:
            logger.info("  🕸️ Rebac Disabled")

        logger.info("────────────────────────────────────────────────────────────────")
