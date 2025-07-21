import logging
from typing import Callable

from app.chatbot.structures.agentic_flow import AgenticFlow
from app.flow import AgentFlow  # or BaseAgent if renamed

logger = logging.getLogger(__name__)


class DynamicAgentManager:
    """
    Manages dynamic agents created at runtime (e.g. via REST).
    Each agent is registered by name and associated with a callable constructor.
    """

    def __init__(self):
        self.agent_cache: dict[str, AgentFlow] = {}
        self.agent_constructors: dict[str, Callable[[], AgentFlow]] = {}

    def register_agent(self, name: str, constructor: Callable[[], AgentFlow]):
        """
        Registers a new dynamic agent class or factory.
        """
        logger.info(f"Registering dynamic agent: {name}")
        self.agent_constructors[name] = constructor

    def get_create_agent_instance(self, name: str, session_id: str) -> AgentFlow:
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
