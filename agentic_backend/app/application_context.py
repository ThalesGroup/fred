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
from typing import Dict, List, Optional, Type
from app.core.agents.store.base_agent_store import BaseAgentStore
from app.core.feedback.store.base_feedback_store import BaseFeedbackStore

from pydantic import BaseModel
from app.model_factory import get_structured_chain
from app.common.structures import AgentSettings, Configuration, ModelConfiguration, ServicesSettings
from app.model_factory import get_model
from langchain_core.language_models.base import BaseLanguageModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from app.core.session.stores.abstract_session_backend import AbstractSessionStorage
from pathlib import Path

import logging

logger = logging.getLogger(__name__)



# -------------------------------
# Public access helper functions
# -------------------------------

def get_structured_chain_for_service(service_name: str, schema: Type[BaseModel]):
    """
    Returns a structured output chain for a given service and schema.
    This method provides fallback for unsupported providers. Only OpenAI and Azure 
    support the function_calling features. If not, like Ollama, it will use a default 
    prompt as a fallback.

    Args:
        service_name (str): The name of the AI service as configured.
        schema (Type[BaseModel]): The Pydantic schema expected from the LLM.

    Returns:
        A Langchain chain capable of returning a structured schema instance.
    """
    app_context = get_app_context()
    model_config = app_context.get_service_settings(service_name).model
    return get_structured_chain(schema, model_config)

def get_configuration() -> Configuration:
    """
    Retrieves the global application configuration.

    Returns:
        Configuration: The singleton application configuration.
    """
    return get_app_context().configuration

def get_sessions_store() -> AbstractSessionStorage:
    return get_app_context().get_sessions_store()

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


def toremove_get_model_for_agent(agent_name: str) -> BaseLanguageModel:
    """
    Retrieves the AI model instance for a given agent.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        BaseLanguageModel: The AI model configured for the agent.
    """
    return get_app_context().toremove_get_model_for_agent(agent_name)


def get_default_model() -> BaseLanguageModel:
    """
    Retrieves the default AI model instance.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        BaseLanguageModel: The AI model configured for the agent.
    """
    return get_app_context().get_default_model()


def get_agent_settings(agent_name: str) -> AgentSettings:
    """
    Retrieves the configuration settings for a given agent.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        AgentSettings: The configuration of the agent.
    """
    return get_app_context().get_agent_settings(agent_name)


def get_model_for_service(service_name: str) -> BaseLanguageModel:
    """
    Retrieves the AI model instance for a given service.

    Args:
        service_name (str): The name of the service.

    Returns:
        BaseLanguageModel: The AI model configured for the service.
    """
    return get_app_context().get_model_for_service(service_name)


def get_mcp_agent_tools(mcp_client: MultiServerMCPClient) -> list[BaseTool]:
    """
    Retrieves the AI MCP client tools list.

    Args:
        mcp_client (MultiServerMCPClient): The MCP client connected to the MCP servers.

    Returns:
        list[BaseTool]: A list of all the tools associated to the agent
    """
    return get_app_context().get_mcp_agent_tools(mcp_client)


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

    def __new__(cls, configuration: Configuration = None):
        
        with cls._lock:
            if cls._instance is None:
                if configuration is None:
                    raise ValueError("ApplicationContext must be initialized with a configuration first.")
                cls._instance = super().__new__(cls)

                # Store configuration and runtime status
                cls._instance.configuration = configuration
                cls._instance.status = RuntimeStatus()
                cls._instance._service_instances = {}  # Cache for service instances
                cls._instance.apply_default_models()
                cls._instance._build_indexes()

            return cls._instance

    def _build_indexes(self):
        """Builds fast access indexes from the list-based configuration."""
        self._agent_index: Dict[str, AgentSettings] = {
            agent.name: agent for agent in self.configuration.ai.agents
        }
        self._service_index: Dict[str, ServicesSettings] = {
            service.name: service for service in self.configuration.ai.services
        }

    def apply_default_models(self):
        """
        Apply the default model configuration to all agents and services if not explicitly set.
        This merges the default settings into each component's model config.
        """
        def merge(target: BaseModel) -> BaseModel:
            defaults = self.configuration.ai.default_model.model_dump(exclude_unset=True)
            target_dict = target.model_dump(exclude_unset=True)
            merged_dict = {**defaults, **target_dict}
            return type(target)(**merged_dict)

        # Apply to services
        for service in self.configuration.ai.services:
            service.model = self._merge_with_default_model(service.model)

        # Apply to agents
        for agent in self.configuration.ai.agents:
            agent.model = self._merge_with_default_model(agent.model)

    def _merge_with_default_model(self, model: Optional[ModelConfiguration]) -> ModelConfiguration:
        default_model = self.configuration.ai.default_model.model_dump(exclude_unset=True)
        model_dict = model.model_dump(exclude_unset=True) if model else {}
        merged = {**default_model, **model_dict}
        return ModelConfiguration(**merged)
    
    def apply_default_model_to_agent(self, agent_settings: AgentSettings) -> AgentSettings:
        """
        Returns a new AgentSettings with the default model merged in, unless already fully specified.
        """
        merged_model = self._merge_with_default_model(agent_settings.model)
        return agent_settings.model_copy(update={"model": merged_model})
    
    # --- AI Models ---

    def get_agent_settings(self, agent_name: str) -> AgentSettings:
        agent_settings = self._agent_index.get(agent_name)
        if agent_settings is None or not agent_settings.enabled:
            raise ValueError(f"AI agent '{agent_name}' is not configured or enabled.")
        return agent_settings

    def get_service_settings(self, service_name: str) -> ServicesSettings:
        service_settings = self._service_index.get(service_name)
        if service_settings is None or not service_settings.enabled:
            raise ValueError(f"AI service '{service_name}' is not configured or enabled.")
        return service_settings

    def get_model_for_service(self, service_name: str) -> BaseLanguageModel:
        service_settings = self.get_service_settings(service_name)
        return get_model(service_settings.model)

    def get_default_model(self) -> BaseLanguageModel:
        """
        Retrieves the default AI model instance.
        """
        return get_model(self.configuration.ai.default_model)
    
    def toremove_get_model_for_agent(self, agent_name: str) -> BaseLanguageModel:
        agent_settings = self.get_agent_settings(agent_name)
        return get_model(agent_settings.model)

    # --- Agent classes ---

    def get_enabled_agent_names(self) -> List[str]:
        """
        Retrieves a list of enabled agent names from the configuration.

        Returns:
            List[str]: List of enabled agent names.
        """
        return [agent.name for agent in self.configuration.ai.agents if agent.enabled]

    def get_sessions_store(self) -> AbstractSessionStorage:
        """
        Factory function to create a sessions store instance based on the configuration.
        As of now, it supports in_memory and OpenSearch sessions storage.
        
        Returns:
            AbstractSessionStorage: An instance of the sessions store.
        """
        # Import here to avoid avoid circular dependencies:
        from app.core.session.stores.in_memory_session_store import InMemorySessionStorage
        from app.core.session.stores.opensearch_session_store import OpensearchSessionStorage
        config = get_configuration().session_storage
        if config.type == "in_memory":
            return InMemorySessionStorage()
        elif config.type == "opensearch":
            return OpensearchSessionStorage(
                host=config.host,
                username=config.username,
                password=config.password,
                secure=config.secure,
                verify_certs=config.verify_certs,
                sessions_index=config.sessions_index,
                history_index=config.history_index
            )
        else:
            raise ValueError(f"Unsupported sessions storage backend: {config.type}")
        
    def get_agent_store(self) -> BaseAgentStore:
        """
        Retrieve the configured agent store. It is used to save all the configured or
        dynamically created agents
        
        Returns:
            BaseDynamicAgentStore: An instance of the dynamic agents store.
        """
        config = get_configuration().agent_storage
        if config.type == "duckdb":
            from app.core.agents.store.duckdb_agent_store import DuckdbAgentStorage
            db_path = Path(config.duckdb_path).expanduser()
            return DuckdbAgentStorage(db_path)
        else:
            raise ValueError(f"Unsupported sessions storage backend: {config.type}")


    def get_feedback_store(self) -> BaseFeedbackStore:
        """
        Retrieve the configured agent store. It is used to save all the configured or
        dynamically created agents
        
        Returns:
            BaseDynamicAgentStore: An instance of the dynamic agents store.
        """
        config = get_configuration().feedback_storage
        if config.type == "duckdb":
            from app.core.feedback.store.duckdb_feedback_store import DuckdbFeedbackStore
            db_path = Path(config.duckdb_path).expanduser()
            return DuckdbFeedbackStore(db_path)
        else:
            raise ValueError(f"Unsupported sessions storage backend: {config.type}")


