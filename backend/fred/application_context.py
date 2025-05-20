# application_context.py

"""
Centralized application context singleton to store and manage global application configuration and runtime state.

Includes:
- Configuration access
- Runtime status (e.g., offline mode)
- AI model accessors
- Dynamic agent class loading and access
- Context service management
"""

import importlib
import os
import pathlib
from threading import Lock
from typing import Dict, List, Type, Any
from pydantic import BaseModel
from context.setting.context_store_minio_settings import ContextStoreMinioSettings
from context.setting.context_store_local_settings import ContextStoreLocalSettings
from context.store.local_context_store import LocalContextStore
from context.store.minio_context_store import MinIOContextStore
from model_factory import get_structured_chain
from fred.common.structure import AgentSettings, Configuration, ServicesSettings
from fred.model_factory import get_model
from langchain_core.language_models.base import BaseLanguageModel
from flow import AgentFlow, Flow  # Base class for all agent flows
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


def get_model_for_agent(agent_name: str) -> BaseLanguageModel:
    """
    Retrieves the AI model instance for a given agent.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        BaseLanguageModel: The AI model configured for the agent.
    """
    return get_app_context().get_model_for_agent(agent_name)

def get_default_model() -> BaseLanguageModel:
    """
    Retrieves the default AI model instance.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        BaseLanguageModel: The AI model configured for the agent.
    """
    return get_app_context().get_default_model()


def get_model_for_leader() -> BaseLanguageModel:
    """
    Retrieves the AI model instance for the leader agent.

    Returns:
        BaseLanguageModel: The AI model configured for the leader agent.
    """
    return get_app_context().get_model_for_leader()


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

def get_agent_class(agent_name: str) -> Type[AgentFlow]:
    """
    Retrieves the agent class for a given agent name.

    Args:
        agent_name (str): The name of the agent.

    Returns:
        Type[AgentFlow]: The class of the agent.
    """
    return get_app_context().get_agent_class(agent_name)


def get_all_agent_classes() -> Dict[str, Type[AgentFlow]]:
    """
    Retrieves a mapping of all configured agent names to their classes.

    Returns:
        Dict[str, Type[AgentFlow]]: Mapping of agent name to agent class.
    """
    return get_app_context().agent_classes


def _create_context_service():
    """
    Factory function to create the appropriate ContextStore implementation
    based on configuration or environment variables.
    """
    storage_backend = os.getenv("CONTEXT_STORAGE_BACKEND", "local").lower()

    if storage_backend == "minio":
        settings = ContextStoreMinioSettings()
        client = MinIOContextStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        return MinIOContextStore(client, settings.minio_bucket_name)

    settings = ContextStoreLocalSettings()
    return LocalContextStore(settings.root_path)


def get_context_service():
    """
    Public accessor for the context service instance.
    """
    return get_app_context().get_context_service()

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
    context_service = _create_context_service()

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
                cls._instance.context_service = _create_context_service()
                cls._instance._build_indexes()

                # ✅ Dynamically load agent classes based on configuration
                cls._instance.agent_classes = cls._instance._load_agent_classes()

            return cls._instance

    def _build_indexes(self):
        """Builds fast access indexes from the list-based configuration."""
        self._agent_index: Dict[str, AgentSettings] = {
            agent.name: agent for agent in self.configuration.ai.agents
        }
        self._service_index: Dict[str, ServicesSettings] = {
            service.name: service for service in self.configuration.ai.services
        }

    def _load_agent_classes(self) -> Dict[str, Type[AgentFlow]]:
        """
        Dynamically loads agent classes based on the class paths provided in the configuration.

        Returns:
            Dict[str, Type[AgentFlow]]: Mapping of agent name to agent class.

        Raises:
            ImportError: If an agent class cannot be imported.
            ValueError: If an agent class does not inherit from AgentFlow.
        """
        agent_classes = {}

        for agent in self.configuration.ai.agents:
            if not agent.enabled:
                continue

            if not agent.class_path:
                raise ValueError(f"Agent '{agent.name}' is enabled but 'class_path' is not defined in configuration.")

            module_name, class_name = agent.class_path.rsplit(".", 1)

            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
            except (ImportError, AttributeError) as e:
                raise ImportError(f"Error loading class '{agent.class_path}' for agent '{agent.name}': {e}") from e

            if not issubclass(cls, AgentFlow):
                raise ValueError(f"Agent class '{agent.class_path}' must inherit from AgentFlow.")

            agent_classes[agent.name] = cls

        return agent_classes
    
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

        # Apply to leader
        if self.configuration.ai.leader.enabled:
            self.configuration.ai.leader.model = merge(self.configuration.ai.leader.model)

        # Apply to services
        for service in self.configuration.ai.services:
            if service.enabled:
                service.model = merge(service.model)

        # Apply to agents
        for agent in self.configuration.ai.agents:
            if agent.enabled:
                agent.model = merge(agent.model)


    # --- AI Models ---

    def get_leader_settings(self) -> AgentSettings:
        return self.configuration.ai.leader

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
    
    def get_model_for_leader(self) -> BaseLanguageModel:
        leader_settings = self.get_leader_settings()
        return get_model(leader_settings.model)

    def get_model_for_agent(self, agent_name: str) -> BaseLanguageModel:
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

    def get_agent_class(self, agent_name: str) -> Type[AgentFlow]:
        if agent_name == self.configuration.ai.leader.name:
            return self._load_leader_class()
        agent_class = self.agent_classes.get(agent_name)
        if agent_class is None:
            raise ValueError(f"Agent class for '{agent_name}' not found.")
        return agent_class
    
    def _load_leader_class(self) -> Type[AgentFlow]:
        """
        Dynamically loads the leader agent class from the configuration.

        Returns:
            Type[AgentFlow]: The class of the leader agent.

        Raises:
            ImportError: If the class cannot be imported.
            ValueError: If it does not inherit from AgentFlow.
        """
        leader_cfg = self.configuration.ai.leader

        if not leader_cfg.enabled:
            raise ValueError("Leader is not enabled in configuration.")

        if not leader_cfg.class_path:
            raise ValueError("Leader class_path must be defined.")

        module_name, class_name = leader_cfg.class_path.rsplit(".", 1)

        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Error loading leader class '{leader_cfg.class_path}': {e}") from e

        if not issubclass(cls, Flow):
            raise ValueError(f"Leader class '{leader_cfg.class_path}' must inherit from AgentFlow.")

        return cls


    def list_agent_names(self) -> list[str]:
        """
        Lists all available agent names from the configuration.

        Returns:
            list[str]: List of available agent names.
        """
        return list(self.agent_classes.keys())
        
    def get_context_service(self):
        """
        Returns the singleton ContextService instance.
        """
        return self.context_service
