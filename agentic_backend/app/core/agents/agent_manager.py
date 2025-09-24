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

import asyncio
import importlib
import logging
from inspect import iscoroutinefunction
from typing import Dict, List, Type

from app.common.structures import AgentSettings, Configuration
from app.core.agents.agent_loader import AgentLoader
from app.core.agents.agent_supervisor import AgentSupervisor
from app.core.agents.agentic_flow import AgenticFlow
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import RuntimeContext
from app.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


class AgentManager:
    """
    Manages the full lifecycle of AI agents (leaders and experts), including:

    - Loading static agents from configuration at startup.
    - Persisting new agents to storage (e.g., DuckDB).
    - Rehydrating all persisted agents at runtime (with class instantiation and async init).
    - Registering agents into in-memory maps for routing and discovery.
    - Injecting expert agents into leader agents.
    - Providing runtime agent discovery (e.g., for the UI).

    Supports both statically declared agents (via configuration.yaml) and dynamically created ones.
    """

    def __init__(self, config: Configuration, store: BaseAgentStore):
        self.config = config
        self.store = store
        self.loader = AgentLoader(config=self.config, store=self.store)
        self.supervisor = AgentSupervisor()

        # In-memory registries
        self.agent_instances: Dict[str, AgentFlow] = {}
        self.agent_settings: Dict[str, AgentSettings] = {}
        self.failed_agents: Dict[str, AgentSettings] = {}
        self.agent_classes: Dict[str, Type[AgentFlow]] = {}

    async def initialize_and_start_retries(self):
        """
        The main async entry point for application startup.
        """
        # Phase 1: Initial load
        static_instances, failed_static = await self.loader.load_static()
        for inst in static_instances:
            self._register_loaded_agent(inst.name, inst, inst.agent_settings)
        self.failed_agents.update(failed_static)

        persisted_instances = await self.loader.load_persisted()
        for inst in persisted_instances:
            self._register_loaded_agent(inst.name, inst, inst.agent_settings)

        self.supervisor.inject_experts_into_leaders(
            agents_by_name=self.agent_instances,
            settings_by_name=self.agent_settings,
            classes_by_name=self.agent_classes,
        )

        # Phase 2: Start the background retry loop managed by the supervisor
        # The retry loop is a long-lived coroutine, which we spawn as a task.
        asyncio.create_task(
            self.supervisor.run_retry_loop(self._retry_failed_agents_logic)
        )

        logger.info("✅ AgentManager startup tasks launched.")

    async def _retry_failed_agents_logic(self):
        """
        Called by the supervisor's background loop.
        Simple asyncio-based fan-out/fan-in:
        - snapshot and clear the current failures
        - retry them concurrently
        - if any retry task crashes unexpectedly, requeue that agent
        """
        if not self.failed_agents:
            return

        agents_to_retry = list(self.failed_agents.values())
        self.failed_agents.clear()
        logger.info("🔁 Retrying failed agents (count=%d)...", len(agents_to_retry))

        # Launch retries concurrently with asyncio, not anyio
        tasks = [
            asyncio.create_task(self._handle_single_agent_retry(cfg))
            for cfg in agents_to_retry
        ]

        # Gather; if a task crashes despite our internal try/except, requeue it
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for cfg, res in zip(agents_to_retry, results):
            if isinstance(res, BaseException):
                logger.exception(
                    "⚠️ Retry task crashed for '%s': %s", cfg.name, type(res).__name__
                )
                self.failed_agents[cfg.name] = cfg  # requeue for next loop

    async def _handle_single_agent_retry(self, agent_cfg: AgentSettings):
        """
        Tries to initialize and register a single agent.
        If it fails, it adds it back to the `failed_agents` dict.
        """
        try:
            # Re-run the core initialization logic (import, instantiate, async_init)
            cls = self.loader._import_agent_class(agent_cfg.class_path)
            instance = cls(agent_settings=agent_cfg)
            if iscoroutinefunction(getattr(instance, "async_init", None)):
                await instance.async_init()

            self._register_loaded_agent(instance.name, instance, agent_cfg)
            logger.info(f"✅ Recovered agent '{instance.name}' on retry.")

        except Exception as e:
            logger.exception(f"❌ Failed to recover agent '{agent_cfg.name}': {e}")
            self.failed_agents[agent_cfg.name] = agent_cfg

    async def _register_static_agent(self, agent_cfg: AgentSettings) -> bool:
        try:
            module_name, class_name = agent_cfg.class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except (ValueError, ImportError, AttributeError) as e:
            logger.error(
                f"❌ Failed to import class '{agent_cfg.class_path}' for '{agent_cfg.name}': {e}"
            )
            return False

        if not issubclass(cls, (AgentFlow)):
            logger.error(
                f"Class '{agent_cfg.class_path}' is not a supported Flow or AgentFlow."
            )
            return False

        try:
            instance = cls(agent_settings=agent_cfg)
            if iscoroutinefunction(getattr(instance, "async_init", None)):
                await instance.async_init()

            self._register_loaded_agent(agent_cfg.name, instance, agent_cfg)
            logger.info(
                f"✅ Registered static agent '{agent_cfg.name}' from configuration."
            )
            return True
        except Exception as e:
            logger.error(
                f"❌ Failed to instantiate or register static agent '{agent_cfg.name}': {e}"
            )
            return False

    def _try_seed_agent(self, agent_cfg: AgentSettings):
        """
        Attempts to load the class for the given agent and instantiate it.
        If successful, saves it to persistent store.
        Logs detailed errors for class import/instantiation issues.
        """
        try:
            module_name, class_name = agent_cfg.class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except (ValueError, ImportError, AttributeError) as e:
            logger.error(
                f"❌ Failed to load class '{agent_cfg.class_path}' for '{agent_cfg.name}': {e}"
            )
            return

        if not issubclass(cls, (AgentFlow)):
            logger.error(
                f"Class '{agent_cfg.class_path}' is not a supported Flow or AgentFlow."
            )
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

    def _register_loaded_agent(
        self, name: str, instance: AgentFlow, settings: AgentSettings
    ):
        """
        Internal helper: registers an already-initialized agent (typically at startup).
        Adds it to the runtime maps so it's discoverable and usable.
        """
        self.agent_classes[name] = type(instance)
        self.agent_settings[name] = settings
        self.agent_instances[name] = instance

    def register_dynamic_agent(self, instance: AgentFlow, settings: AgentSettings):
        """
        Public method to register a dynamically created agent in memory.
        Makes the agent immediately available in the running app, including UI and routing.
        Should be called after async_init.
        """
        name = settings.name
        self.agent_instances[name] = instance
        self.agent_classes[name] = type(instance)
        self.agent_settings[name] = settings
        logger.info(
            f"✅ Registered dynamic agent '{name}' ({type(instance).__name__}) in memory."
        )

    async def unregister_agent(self, name: str):
        """
        Removes an agent from memory and stops any running tasks.
        Delegates to `aclose_single` to centralize cleanup logic.
        """
        success = await self.aclose_single(name)
        if not success:
            logger.warning(f"Attempted to unregister non-existent agent '{name}'.")

    def get_agentic_flows(self) -> List[AgenticFlow]:
        flows = []
        for name, instance in self.agent_instances.items():
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

    def get_agent_instance(
        self, name: str, runtime_context: RuntimeContext | None = None
    ) -> AgentFlow:
        instance = self.agent_instances.get(name)
        if not instance:
            raise ValueError(f"No agent instance for '{name}'")
        if runtime_context:
            instance.set_runtime_context(runtime_context)
        return instance

    def get_agent_settings(self, name: str) -> AgentSettings:
        settings = self.agent_settings.get(name)
        if not settings:
            raise ValueError(f"No agent settings for '{name}'")
        return settings

    def get_agent_classes(self) -> Dict[str, Type[AgentFlow]]:
        return self.agent_classes

    async def aclose_single(self, name: str) -> bool:
        """
        Gracefully shuts down and unregisters a single agent.
        Returns True if the agent was found and closed, False otherwise.
        """
        instance = self.agent_instances.pop(name, None)
        self.agent_settings.pop(name, None)
        self.agent_classes.pop(name, None)

        if not instance:
            logger.warning(f"Attempted to close non-existent agent '{name}'.")
            return False

        await self.supervisor.close_agents([instance])
        logger.info(f"🗑️ Unregistered agent '{name}' from memory.")
        return True

    async def aclose(self):
        """
        Shuts down all agents.
        """
        # Iterate over a copy of keys to avoid RuntimeError
        for name in list(self.agent_instances.keys()):
            await self.aclose_single(name)

        self.supervisor.stop_retry_loop()
        self.agent_instances.clear()
        self.agent_settings.clear()
        self.agent_classes.clear()
        logger.info("🗑️ AgentManager cleanup complete.")
