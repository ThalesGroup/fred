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

from threading import Lock
from typing import Any, Dict, List, Optional

from app.core.agents.store.base_agent_store import BaseAgentStore
from app.core.feedback.store.base_feedback_store import BaseFeedbackStore
from pydantic import BaseModel

from app.common.structures import (
    AgentSettings,
    Configuration,
    ModelConfiguration,
)
from app.core.model.model_factory import get_model
from langchain_core.language_models.base import BaseLanguageModel
from app.core.session.stores.base_history_store import BaseHistoryStore
from app.core.session.stores.base_session_store import BaseSessionStore
from pathlib import Path
from fred_core import (
    OpenSearchIndexConfig,
    DuckdbStoreConfig,
)
import logging

logger = logging.getLogger(__name__)

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

def get_history_store() -> BaseHistoryStore:
    return get_app_context().get_history_store()


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

            return cls._instance

    def apply_default_models(self):
        """
        Apply the default model configuration to all agents and services if not explicitly set.
        This merges the default settings into each component's model config.
        """

        def merge(target: BaseModel) -> BaseModel:
            defaults = self.configuration.ai.default_model.model_dump(
                exclude_unset=True
            )
            target_dict = target.model_dump(exclude_unset=True)
            merged_dict = {**defaults, **target_dict}
            return type(target)(**merged_dict)

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
            from app.core.session.stores.opensearch_session_store import OpensearchSessionStore
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
        from app.core.session.stores.duckdb_history_store import DuckdbHistoryStore

        store_config = get_configuration().storage.history_store
        if isinstance(store_config, DuckdbStoreConfig):
            from app.core.session.stores.duckdb_history_store import DuckdbHistoryStore
            db_path = Path(store_config.duckdb_path).expanduser()
            return DuckdbHistoryStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError(
                    "Missing OpenSearch credentials: OPENSEARCH_USER and/or OPENSEARCH_PASSWORD"
                )
            from app.core.session.stores.opensearch_history_index import OpensearchHistoryIndex
            return OpensearchHistoryIndex(
                host=opensearch_config.username,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")

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
            from app.core.agents.store.opensearch_agent_store import OpenSearchAgentStore
            return OpenSearchAgentStore(
                host=opensearch_config.username,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")


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
            from app.core.feedback.store.duckdb_feedback_store import DuckdbFeedbackStore
            return DuckdbFeedbackStore(db_path)
        elif isinstance(store_config, OpenSearchIndexConfig):
            opensearch_config = get_configuration().storage.opensearch
            password = opensearch_config.password
            if not password:
                raise ValueError(
                    "Missing OpenSearch credentials: OPENSEARCH_PASSWORD"
                )
            from app.core.feedback.store.opensearch_feedback_store import OpenSearchFeedbackStore
            return OpenSearchFeedbackStore(
                host=opensearch_config.username,
                username=opensearch_config.username,
                password=password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=store_config.index,
            )
        else:
            raise ValueError("Unsupported sessions storage backend")
        

