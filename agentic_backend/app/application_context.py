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

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from fred_core import (
    BaseKPIStore,
    BaseLogStore,
    BearerAuth,
    ClientCredentialsProvider,
    DuckdbStoreConfig,
    InMemoryLogStorageConfig,
    KpiLogStore,
    KPIWriter,
    LogStoreConfig,
    OpenSearchIndexConfig,
    OpenSearchKPIStore,
    OpenSearchLogStore,
    RamLogStore,
    SpiceDbRebacConfig,
    SQLStorageConfig,
    get_model,
    split_realm_url,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.security.rebac.spicedb_engine import SpiceDbRebacEngine
from langchain_core.language_models.base import BaseLanguageModel
from requests.auth import AuthBase

from app.common.structures import (
    AgentSettings,
    Configuration,
    ModelConfiguration,
)
from app.core.agents.store.base_agent_store import BaseAgentStore
from app.core.feedback.store.base_feedback_store import BaseFeedbackStore
from app.core.monitoring.base_history_store import BaseHistoryStore
from app.core.session.stores.base_session_store import BaseSessionStore

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


def get_knowledge_flow_base_url() -> str:
    return get_app_context().get_knowledge_flow_base_url()


def get_history_store() -> BaseHistoryStore:
    return get_app_context().get_history_store()


def get_kpi_writer() -> KPIWriter:
    return get_app_context().get_kpi_writer()


def get_rebac_engine() -> RebacEngine:
    """Expose the shared ReBAC engine instance."""

    return get_app_context().get_rebac_engine()


def get_agent_store() -> BaseAgentStore:
    return get_app_context().get_agent_store()


def get_feedback_store() -> BaseFeedbackStore:
    return get_app_context().get_feedback_store()


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
    _session_store_instance: Optional[BaseSessionStore] = None
    _history_store_instance: Optional[BaseHistoryStore] = None
    _kpi_store_instance: Optional[BaseKPIStore] = None
    _log_store_instance: Optional[BaseLogStore] = None
    _outbound_auth: OutboundAuth | None = None
    _kpi_writer: Optional[KPIWriter] = None
    _rebac_engine: Optional[RebacEngine] = None

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
                cls._instance.apply_default_models()
                cls._instance._log_config_summary()

            return cls._instance

    def apply_default_models(self):
        """
        Apply the default model configuration to all agents and services if not explicitly set.
        This merges the default settings into each component's model config.
        """

        # Apply to agents
        for agent in self.configuration.ai.agents:
            agent.model = self._merge_with_default_model(agent.model)

    def _merge_with_default_model(
        self, model: Optional[ModelConfiguration]
    ) -> ModelConfiguration:
        default_model = self.configuration.ai.default_chat_model.model_dump(
            exclude_unset=True
        )
        model_dict = model.model_dump(exclude_unset=True) if model else {}
        merged = {**default_model, **model_dict}
        return ModelConfiguration(**merged)

    def apply_default_model_to_agent(
        self, agent_settings: AgentSettings
    ) -> AgentSettings:
        """
        Returns a new AgentSettings with the default model merged in, unless already fully specified.
        """
        merged_model = self._merge_with_default_model(agent_settings.model)
        return agent_settings.model_copy(update={"model": merged_model})

    def get_knowledge_flow_base_url(self) -> str:
        """
        Retrieves the base URL for the knowledge flow service.
        """
        return self.configuration.ai.knowledge_flow_url

    # --- AI Models ---

    def get_default_model(self) -> BaseLanguageModel:
        """
        Retrieves the default AI model instance.
        """
        return get_model(self.configuration.ai.default_chat_model)

    # --- Agent classes ---

    def get_enabled_agent_names(self) -> List[str]:
        """
        Retrieves a list of enabled agent names from the configuration.

        Returns:
            List[str]: List of enabled agent names.
        """
        return [agent.name for agent in self.configuration.ai.agents if agent.enabled]

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
        if isinstance(store_config, DuckdbStoreConfig):
            from app.core.session.stores.duckdb_session_store import DuckdbSessionStore

            db_path = Path(store_config.duckdb_path).expanduser()
            return DuckdbSessionStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            from app.core.session.stores.opensearch_session_store import (
                OpensearchSessionStore,
            )

            password = opensearch_config.password
            if not password:
                raise ValueError(
                    "Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD"
                )

            return OpensearchSessionStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")

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
        from app.core.monitoring.duckdb_history_store import DuckdbHistoryStore

        store_config = get_configuration().storage.history_store
        if isinstance(store_config, DuckdbStoreConfig):
            from app.core.monitoring.duckdb_history_store import DuckdbHistoryStore

            db_path = Path(store_config.duckdb_path).expanduser()
            return DuckdbHistoryStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError(
                    "Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD"
                )
            from app.core.monitoring.opensearch_history_store import (
                OpensearchHistoryStore,
            )

            return OpensearchHistoryStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")

    def get_kpi_store(self) -> BaseKPIStore:
        if self._kpi_store_instance is not None:
            return self._kpi_store_instance

        store_config = get_configuration().storage.kpi_store
        if isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            self._kpi_store_instance = OpenSearchKPIStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        elif isinstance(store_config, LogStoreConfig):
            self._kpi_store_instance = KpiLogStore(level=store_config.level)
        else:
            raise ValueError("Unsupported KPI storage backend")
        return self._kpi_store_instance

    def get_agent_store(self) -> BaseAgentStore:
        """
        Factory function to create a sessions store instance based on the configuration.
        As of now, it supports in_memory and OpenSearch sessions storage.

        Returns:
            AbstractSessionStorage: An instance of the sessions store.
        """
        if self._agent_store_instance is not None:
            return self._agent_store_instance
        from app.core.agents.store.duckdb_agent_store import DuckdbAgentStore
        from app.core.agents.store.opensearch_agent_store import OpenSearchAgentStore

        store_config = get_configuration().storage.agent_store
        if isinstance(store_config, DuckdbStoreConfig):
            from app.core.agents.store.duckdb_agent_store import DuckdbAgentStore

            db_path = Path(store_config.duckdb_path).expanduser()
            return DuckdbAgentStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError(
                    "Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD"
                )
            from app.core.agents.store.opensearch_agent_store import (
                OpenSearchAgentStore,
            )

            return OpenSearchAgentStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")

    def get_kpi_writer(self) -> KPIWriter:
        if self._kpi_writer is not None:
            return self._kpi_writer

        self._kpi_writer = KPIWriter(store=self.get_kpi_store())
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
        if isinstance(store_config, DuckdbStoreConfig):
            db_path = Path(store_config.duckdb_path).expanduser()
            from app.core.feedback.store.duckdb_feedback_store import (
                DuckdbFeedbackStore,
            )

            return DuckdbFeedbackStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")
            from app.core.feedback.store.opensearch_feedback_store import (
                OpenSearchFeedbackStore,
            )

            return OpenSearchFeedbackStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
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
        if self._rebac_engine is not None:
            return self._rebac_engine

        rebac_config = self.configuration.security.rebac
        if isinstance(rebac_config, SpiceDbRebacConfig):
            token_env_var = rebac_config.token_env_var
            token = os.getenv(token_env_var)
            if not token:
                raise ValueError(
                    f"Missing SpiceDB token environment variable: {token_env_var}"
                )

            logger.info(
                "Initializing SpiceDB ReBAC engine (endpoint=%s, insecure=%s)",
                rebac_config.endpoint,
                rebac_config.insecure,
            )
            self._rebac_engine = SpiceDbRebacEngine(rebac_config, token=token)
        else:
            raise ValueError(
                f"Unsupported ReBAC engine type: {getattr(rebac_config, 'type', rebac_config)}"
            )

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
        logger.info("  ⏱️  Timeouts: connect=%ss, read=%ss", tcfg.connect, tcfg.read)

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
        if isinstance(rebac_cfg, SpiceDbRebacConfig):
            logger.info("  🕸️ ReBAC engine: %s", rebac_cfg.type)
            logger.info("     • endpoint: %s", rebac_cfg.endpoint)
            logger.info("     • insecure: %s", rebac_cfg.insecure)
            logger.info("     • sync_schema_on_init: %s", rebac_cfg.sync_schema_on_init)
            token_value = os.getenv(rebac_cfg.token_env_var, "")
            if token_value:
                logger.info(
                    "     • %s: present (%s)",
                    rebac_cfg.token_env_var,
                    _mask(token_value),
                )
            else:
                logger.warning(
                    "     ⚠️ %s is not set — ReBAC authorization calls will fail.",
                    rebac_cfg.token_env_var,
                )
        else:
            logger.info("  🕸️ ReBAC engine: disabled")

        logger.info("────────────────────────────────────────────────────────────────")
