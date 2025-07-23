import logging
from typing import Callable, Dict, Type

from app.features.dynamic_agent.mcp_agent import MCPAgent
from app.chatbot.structures.agentic_flow import AgenticFlow
from app.common.structures import AgentSettings
from app.flow import AgentFlow
from app.application_context import get_configuration, get_app_context

logger = logging.getLogger(__name__)


class DynamicAgentManager:
    """
    Manages dynamic agents created at runtime (e.g. via REST).
    Each agent is registered by name and associated with a callable constructor.
    """

    def __init__(self):
        self.agent_cache: Dict[str, AgentFlow] = {}
        self.agent_constructors: Dict[str, Callable[[], AgentFlow]] = {}

        # Automatically load and register all persisted agents from DuckDB
        ##############################################################################################################
        ##### @TODO load the dynamic agents somewhere else where ApplicartionContext is initialized because it is not here
        ##############################################################################################################
        try:
            agent_store = get_app_context().get_dynamic_agent_store()
            configuration = get_configuration()

            for agent in agent_store.load_all():
                if not isinstance(agent, AgentFlow):
                    continue

                def constructor(agent_instance=agent):
                    return agent_instance

                self.register_agent(agent.name, constructor, type(agent))

                get_app_context()._agent_index[agent.name] = AgentSettings(
                    name=agent.name,
                    class_path="app.features.dynamic_agent.mcp_agent.MCPAgent",
                    enabled=True,
                    categories=agent.categories,
                    settings={},
                    model=configuration.ai.default_model,
                    tag=agent.tag,
                    mcp_servers=[],
                    max_steps=10,
                )
                logger.info(f"Dynamically loaded agent: {agent.name}")
        except Exception as e:
            logger.error(f"Failed to preload agents from store: {e}")

    def get_agent_classes(self) -> Dict[str, Type[AgentFlow]]:
        """
        Return {agent_name: AgentFlow subclass} for every registered dynamic agent.
        """
        classes: Dict[str, Type[AgentFlow]] = {}
        for name, constructor in self.agent_constructors.items():
            try:
                classes[name] = constructor().__class__
            except Exception as exc:
                logger.warning("Skipping dynamic agent '%s': %s", name, exc)
        return classes
    
    def register_agent(self, name: str, constructor: Callable[[], AgentFlow], cls: Type[AgentFlow]):
        """
        Registers a new dynamic agent class or factory.
        """
        logger.info(f"Registering dynamic agent: {name}")
        self.agent_constructors[name] = constructor
        
        ctx = get_app_context()
        ctx.agent_classes[name] = cls 

    def get_create_agent_instance(self, name: str, session_id: str, argument: str) -> AgentFlow:
        """
        Returns an instance of a dynamic agent, optionally cached per session.
        """
        cache_key = f"{session_id}:{name}"
        if cache_key in self.agent_cache:
            return self.agent_cache[cache_key]

        constructor = self.agent_constructors.get(name)
        if not constructor:
            raise ValueError(f"Dynamic agent '{name}' not found")

        agent_instance = constructor()
        self.agent_cache[cache_key] = agent_instance
        logger.info(f"Created dynamic agent instance: {name}")
        return agent_instance

    def get_agentic_flows(self) -> list[AgenticFlow]:
        """
        Returns metadata for all registered dynamic agents.
        """
        flows = []
        for name, constructor in self.agent_constructors.items():
            instance = constructor()
            flows.append(
                AgenticFlow(
                    name=instance.name,
                    role=instance.role,
                    nickname=instance.nickname,
                    description=instance.description,
                    icon=instance.icon,
                    tag=instance.tag,
                    experts=[],
                )
            )
        return flows

    def get_registered_names(self) -> list[str]:
        return list(self.agent_constructors.keys())

    def clear_cache_for_session(self, session_id: str):
        to_remove = [k for k in self.agent_cache if k.startswith(f"{session_id}:")]
        for k in to_remove:
            del self.agent_cache[k]

    def has_agent(self, name: str) -> bool:
        return name in self.agent_constructors

    def get_agent_instance(self, name: str) -> AgentFlow:
        constructor = self.agent_constructors.get(name)
        if constructor is None:
            raise ValueError(f"Dynamic agent '{name}' is not registered.")
        return constructor()
    