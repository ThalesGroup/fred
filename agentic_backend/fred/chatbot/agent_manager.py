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

import logging
import json
from typing import cast
from fred.application_context import get_agent_class, get_enabled_agent_names
from fred.chatbot.structures.agentic_flow import AgenticFlow
from fred.leader.leader import Leader

logger = logging.getLogger(__name__)

class AgentManager:
    """
    Manages the creation and optional caching of agent instances by name.
    This class is responsible for instantiating agents based on their names and
    managing their lifecycle. It can cache agents to improve performance, especially
    in scenarios where the same agent is requested multiple times.
    """

    def __init__(self):
        """
        Initializes the AgentManager with an empty cache.
        """
        self.agent_cache = {}

    def get_create_agent_instance(self, name: str, 
                                  session_id: str,
                                  argument: str):
        """
        Retrieve an agent instance by name, optionally cached per session.

        Args:
            name (str): The agent name.
            session_id (str): Optional session ID for per-session caching.

        Returns:
            An instantiated agent.
        """
        cache_key = f"{session_id}:{name}"

        if cache_key in self.agent_cache:
            logger.debug(f"Reusing cached agent for key: {cache_key}")
            return self.agent_cache[cache_key]

        agent_class = get_agent_class(name)
        if not agent_class:
            raise ValueError(f"Agent '{name}' not found in configuration")

        if name == "Fred":
            agent_instance = agent_class()
            agent_instance = cast(Leader, agent_instance)
            logger.info("Initializing Fred with all enabled experts")
            for expert_name in get_enabled_agent_names():
                if expert_name == "Fred":
                    continue  # Don't add Fred as his own expert

                expert_instance = self.get_create_agent_instance(expert_name, session_id, argument)
                compiled_graph = expert_instance.graph.compile()
                agent_instance.add_expert(expert_name, expert_instance, compiled_graph)
            self.agent_cache[cache_key] = agent_instance
            return agent_instance

        agent_instance = agent_class(cluster_fullname=argument)
        self.agent_cache[cache_key] = agent_instance
        logger.debug(f"Cached agent with key: {cache_key}")
        logger.info(f"Created new agent instance for '{name}'")
        return agent_instance

    def clear_cache_for_session(self, session_id: str):
        """
        Remove all cached agents for a given session.
        """
        to_remove = [k for k in self.agent_cache if k.startswith(f"{session_id}:")]
        for key in to_remove:
            del self.agent_cache[key]
        logger.info(f"Cleared cached agents for session {session_id}")

    def get_agentic_flows(self) -> list[AgenticFlow]:
        """
        Lists all agentic flows including the leader.
        This function retrieves all enabled agent names and their corresponding
        classes, constructs AgenticFlow objects for each, and adds the leader
        manually.

        Returns:
            List of AgenticFlow objects representing all available agentic flows.
        """
        flows = [
            AgenticFlow(
                name=agent_name,
                role=agent_class.role,
                nickname=agent_class.nickname,
                description=agent_class.description,
                icon=agent_class.icon,
                tag=agent_class.tag,
                experts=[],
            )
            for agent_name in get_enabled_agent_names()
            if (agent_class := get_agent_class(agent_name))
        ]

        flows.append(
            AgenticFlow(
                name=Leader.name,
                role=Leader.role,
                nickname=Leader.nickname,
                description=Leader.description,
                icon=Leader.icon,
                tag=Leader.tag,
                experts=get_enabled_agent_names(),
            )
        )

        return flows
