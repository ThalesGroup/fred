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
import importlib
from builtins import ExceptionGroup
from inspect import iscoroutinefunction
from typing import Callable, Dict, List, Type

from app.application_context import get_configuration
from app.common.error import MCPToolFetchError, UnsupportedTransportError
from app.core.agents.flow import AgentFlow, Flow
from app.common.structures import AgentSettings, Configuration
from app.core.agents.agentic_flow import AgenticFlow
from app.core.agents.store.base_agent_store import BaseAgentStore
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]

class AgentManager:

    def __init__(self, config: Configuration, store: BaseAgentStore):
        self.config = get_configuration()
        self.store = store

        self.agent_constructors: Dict[str, Callable[[], Flow]] = {}
        self.agent_classes: Dict[str, Type[Flow]] = {}
        self.agent_settings: Dict[str, AgentSettings] = {}

    async def load_agents(self):
        self._seed_static_agents_from_config()
        await self._load_all_persisted_agents()
        self._inject_experts_into_leaders()


    def _seed_static_agents_from_config(self):
        """
        If config defines agents that are not in DuckDB, create and persist them.
        Validates agent class import and instantiation.
        """
        for agent_cfg in self.config.ai.agents:
            if not agent_cfg.enabled: #or self.store.get(agent_cfg.name):
                continue
            self._try_seed_agent(agent_cfg)

    def _try_seed_agent(self, agent_cfg: AgentSettings):
        try:
            module_name, class_name = agent_cfg.class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except (ValueError, ImportError, AttributeError) as e:
            logger.error(f"❌ Failed to load class '{agent_cfg.class_path}' for '{agent_cfg.name}': {e}")
            return

        if not issubclass(cls, (Flow, AgentFlow)):
            logger.error(f"Class '{agent_cfg.class_path}' is not a supported Flow or AgentFlow.")
            return

        try:
            cls(agent_settings=agent_cfg)  # Validate constructor works
        except Exception as e:
            logger.error(f"❌ Failed to instantiate '{agent_cfg.name}': {e}")
            return

        try:
            self.store.save(agent_cfg)
            logger.info(f"✅ Seeded agent '{agent_cfg.name}' from config into storage.")
        except Exception as e:
            logger.error(f"❌ Failed to save agent '{agent_cfg.name}': {e}")

    async def _load_all_persisted_agents(self):
        """
        Load all agents from persistent store and register them.
        Supports both sync and async agent initialization.
        """
        for agent_settings in self.store.load_all():
            if not agent_settings.class_path:
                logger.warning(f"No class_path for agent '{agent_settings.name}' — skipping.")
                continue

            try:
                module_name, class_name = agent_settings.class_path.rsplit(".", 1)
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)

                if not issubclass(cls, (Flow, AgentFlow)):
                    logger.error(f"Class '{cls}' is not a supported Flow or AgentFlow.")
                    continue

                instance = cls(agent_settings=agent_settings)

                if iscoroutinefunction(getattr(instance, "async_init", None)):
                    await instance.async_init()

                self._register_loaded_agent(agent_settings.name, instance, agent_settings)

                if isinstance(instance, AgentFlow):
                    logger.info(f"✅ Loaded expert agent '{agent_settings.name}' ({agent_settings.class_path})")
                elif isinstance(instance, Flow):
                    logger.info(f"✅ Loaded leader agent '{agent_settings.name}' ({agent_settings.class_path})")

            except Exception as e:
                logger.exception(f"❌ Failed to load agent '{agent_settings.name}': {e}")

    def _inject_experts_into_leaders(self):
        """
        After all agents are loaded, inject expert instances into any leader agents.
        """
        for leader_name, leader_settings in self.agent_settings.items():
            if leader_settings.type != "leader":
                continue

            leader_instance = self.get_agent_instance(leader_name)
            if not hasattr(leader_instance, "add_expert"):
                logger.warning(f"⚠️ Leader '{leader_name}' does not support expert injection (missing 'add_expert').")
                continue

            for expert_name, expert_settings in self.agent_settings.items():
                if expert_name == leader_name:
                    continue
                if not issubclass(self.agent_classes[expert_name], AgentFlow):
                    continue

                expert_instance = self.get_agent_instance(expert_name)
                compiled_graph = expert_instance.get_compiled_graph()

                leader_instance.add_expert(expert_name, expert_instance, compiled_graph)
                logger.info(f"👥 Added expert '{expert_name}' to leader '{leader_name}'")

    def _register_loaded_agent(self, name: str, instance: Flow, settings: AgentSettings):
        self.agent_constructors[name] = lambda a=instance: a
        self.agent_classes[name] = type(instance)
        self.agent_settings[name] = settings

    def get_agentic_flows(self) -> List[AgenticFlow]:
        flows = []
        for name, constructor in self.agent_constructors.items():
            instance = constructor()
            flows.append(AgenticFlow(
                name=instance.name,
                role=instance.role,
                nickname=instance.nickname,
                description=instance.description,
                icon=instance.icon,
                tag=instance.tag,
                experts=[],
            ))
        return flows

    def get_agent_instance(self, name: str) -> Flow:
        constructor = self.agent_constructors.get(name)
        if not constructor:
            raise ValueError(f"No agent constructor for '{name}'")
        return constructor()

    def get_agent_settings(self, name: str) -> AgentSettings:
        settings = self.agent_settings.get(name)
        if not settings:
            raise ValueError(f"No agent settings for '{name}'")
        return settings

    def get_agent_classes(self) -> Dict[str, Type[Flow]]:
        return self.agent_classes

    def get_enabled_agent_names(self) -> List[str]:
        return list(self.agent_constructors.keys())

    def get_mcp_client(self, agent_name: str) -> MultiServerMCPClient:
        agent_settings = self.get_agent_settings(agent_name)

        import asyncio
        import nest_asyncio
        nest_asyncio.apply()

        client = MultiServerMCPClient()
        loop = asyncio.get_event_loop()

        async def connect_all():
            exceptions = []
            for server in agent_settings.mcp_servers:
                if server.transport not in SUPPORTED_TRANSPORTS:
                    raise UnsupportedTransportError(f"Unsupported transport: {server.transport}")
                try:
                    await client.connect_to_server(
                        server_name=server.name,
                        url=server.url,
                        transport=server.transport,
                        command=server.command,
                        args=server.args,
                        env=server.env,
                        sse_read_timeout=server.sse_read_timeout
                    )
                except Exception as eg:
                    exceptions.extend(getattr(eg, "exceptions", [eg]))
            if exceptions:
                raise ExceptionGroup("Some MCP connections failed", exceptions)

        loop.run_until_complete(connect_all())
        return client

    def get_mcp_agent_tools(self, mcp_client: MultiServerMCPClient) -> list[BaseTool]:
        tools = mcp_client.get_tools()
        if not tools:
            raise MCPToolFetchError("The tool list is empty, make sure the MCP server configuration is correct.")
        return tools
