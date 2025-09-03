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

from dataclasses import dataclass
import os
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from app.core.agents.store.base_agent_store import BaseAgentStore
from app.core.feedback.store.base_feedback_store import BaseFeedbackStore

from app.common.structures import (
    AgentSettings,
    Configuration,
    ModelConfiguration,
)
from app.core.model.model_factory import get_model
from langchain_core.language_models.base import BaseLanguageModel
from app.core.monitoring.base_history_store import BaseHistoryStore
from app.core.session.stores.base_session_store import BaseSessionStore
from pathlib import Path
from fred_core import (
    LogStoreConfig,
    OpenSearchIndexConfig,
    DuckdbStoreConfig,
    ClientCredentialsProvider,
    BearerAuth,
    OpenSearchKPIStore,
    BaseKPIStore,
    KpiLogStore,
    KPIWriter,
    split_realm_url,
)
from requests.auth import AuthBase
import logging
import re


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
    _outbound_auth: OutboundAuth | None = None
    _kpi_writer: Optional[KPIWriter] = None

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
        default_model = self.configuration.ai.default_model.model_dump(
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
        return get_model(self.configuration.ai.default_model)

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

        sec = self.configuration.app.security
        if not sec.enabled:
            self._outbound_auth = OutboundAuth(auth=NoAuth(), refresh=None)
            return self._outbound_auth

        keycloak_base, realm = split_realm_url(sec.keycloak_url)
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

    def _log_config_summary(self) -> None:
        """
        Log a crisp, admin-friendly summary of the Agentic configuration and warn on common mistakes.
        Does NOT print secrets; only presence/masked hints.
        """
        cfg = self.configuration
        sec = cfg.app.security

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
                    # These carry index name + opensearch global section
                    os_cfg = cfg.storage.opensearch
                    logger.info(
                        "     • %-14s OpenSearch host=%s index=%s secure=%s verify=%s",
                        label,
                        os_cfg.host,
                        store_cfg.index,
                        os_cfg.secure,
                        os_cfg.verify_certs,
                    )
                else:
                    # Generic store types from your pydantic StoreConfig could land here
                    logger.info("     • %-14s %s", label, type(store_cfg).__name__)

            _describe("agent_store", st.agent_store)
            _describe("session_store", st.session_store)
            _describe("history_store", st.history_store)
            _describe("feedback_store", st.feedback_store)
            _describe("feedback_store", st.kpi_store)
        except Exception:
            logger.warning(
                "  ⚠️ Failed to read storage section (some variables may be missing)."
            )

        # Inbound security (UI -> Agentic)
        logger.info("  🔒 Outbound security (Agentic → Knwoledge/Third Party):")
        logger.info("     • enabled: %s", sec.enabled)
        logger.info("     • client_id: %s", sec.client_id or "<unset>")
        logger.info("     • keycloak_url: %s", sec.keycloak_url or "<unset>")
        # realm parsing
        try:
            base, realm = split_realm_url(sec.keycloak_url)
            logger.info("     • realm: %s  (base=%s)", realm, base)
        except Exception as e:
            logger.error(
                "     ❌ keycloak_url invalid (expected …/realms/<realm>): %s", e
            )

        # Heuristic warnings on client_id naming
        if sec.client_id == "app":
            logger.warning(
                "     ⚠️ client_id is 'app'. Reserve 'app' for the UI client; "
                "Agentic should usually use a dedicated client like 'agentic'."
            )

        # Outbound S2S (Agentic → Knowledge Flow)
        logger.info("  🔑 Outbound S2S (Agentic → Knowledge Flow):")
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
        if not sec.enabled and secret:
            logger.info(
                "     • Note: inbound security is disabled, but S2S secret is present. "
                "Outbound calls will still include a bearer if your code enables it."
            )

        # Final tips / quick misconfig guards
        if secret and sec.client_id and sec.client_id != "agentic":
            logger.warning(
                "     ⚠️ Secret is present but client_id is '%s' (expected 'agentic' for S2S). "
                "Ensure client_id matches the secret you provisioned.",
                sec.client_id,
            )

        logger.info("────────────────────────────────────────────────────────────────")
