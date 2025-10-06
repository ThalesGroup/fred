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
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_loader import AgentLoader
from app.core.agents.agent_supervisor import AgentSupervisor
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
        Boot order:
        1) Catalog from YAML (all agents, enabled or not)
        2) Catalog from store (override YAML if present/edited)
        3) Runtime from YAML+store (enabled only)
        4) Wire leaders using the full catalog
        5) Start retry loop
        """

        # (1) Catalog ← YAML
        for cfg in self.config.ai.agents:
            self.agent_settings[cfg.name] = self._merge_with_class_defaults(cfg)

        # (2) Catalog ← Store (authoritative if exists)
        try:
            for cfg in self.store.load_all():
                self.agent_settings[cfg.name] = self._merge_with_class_defaults(cfg)
        except Exception:
            logger.exception("Failed to hydrate catalog from store.")

        # (3) Runtime (enabled only)
        (
            static_instances,
            failed_static,
        ) = await self.loader.load_static()  # respects enabled
        for inst in static_instances:
            self._register_loaded_agent(inst.get_name(), inst, inst.agent_settings)

        persisted_instances = await self.loader.load_persisted()  # respects enabled
        for inst in persisted_instances:
            self._register_loaded_agent(inst.get_name(), inst, inst.agent_settings)

        self.failed_agents.update(failed_static)

        # (4) Crew wiring (uses full catalog)
        self.supervisor.inject_experts_into_leaders(
            agents_by_name=self.agent_instances,
            settings_by_name=self.agent_settings,
            classes_by_name=self.agent_classes,
        )

        # (5) Retry loop
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
        if not agent_cfg.class_path:
            logger.error(
                "❌ Cannot retry agent '%s' without a class_path.", agent_cfg.name
            )
            return
        try:
            # Re-run the core initialization logic (import, instantiate, async_init)
            cls = self.loader._import_agent_class(agent_cfg.class_path)
            instance = cls(agent_settings=agent_cfg)
            if iscoroutinefunction(getattr(instance, "async_init", None)):
                await instance.async_init()

            self._register_loaded_agent(instance.get_name(), instance, agent_cfg)
            logger.info(f"✅ Recovered agent '{instance.get_name()}' on retry.")

        except Exception as e:
            logger.exception(f"❌ Failed to recover agent '{agent_cfg.name}': {e}")
            self.failed_agents[agent_cfg.name] = agent_cfg

    def _register_loaded_agent(
        self, name: str, instance: AgentFlow, settings: AgentSettings
    ):
        """
        Internal helper: registers an already-initialized agent (typically at startup).
        Adds it to the runtime maps so it's discoverable and usable.
        """
        merged_settings = self._merge_with_class_defaults(settings)
        instance.apply_settings(merged_settings)

        self.agent_classes[name] = type(instance)
        self.agent_settings[name] = merged_settings
        self.agent_instances[name] = instance

    def register_dynamic_agent(self, instance: AgentFlow, settings: AgentSettings):
        """
        Register a dynamically created agent immediately into runtime + catalog.
        """
        name = settings.name
        merged_settings = self._merge_with_class_defaults(settings)
        instance.apply_settings(merged_settings)

        self.agent_classes[name] = type(instance)
        self.agent_settings[name] = merged_settings
        self.agent_instances[name] = instance  # ⬅️ add to runtime (bug fix)
        logger.info(
            "✅ Registered dynamic agent '%s' (%s).", name, type(instance).__name__
        )

    def get_agentic_flows(self) -> List[AgentSettings]:
        return list(self.agent_settings.values())

    def _merge_with_class_defaults(self, settings: AgentSettings) -> AgentSettings:
        """Try to overlay class-declared defaults onto the given settings."""

        if not settings.class_path:
            return settings

        try:
            agent_cls = self.agent_classes.get(settings.name)
            if not agent_cls:
                agent_cls = self.loader._import_agent_class(settings.class_path)
            if not issubclass(agent_cls, AgentFlow):
                return settings
        except Exception as err:
            logger.debug(
                "Unable to merge defaults for '%s' (class import failed): %s",
                settings.name,
                err,
            )
            return settings

        return agent_cls.merge_settings_with_class_defaults(settings)

    def get_agent_instance(
        self, name: str, runtime_context: RuntimeContext | None = None
    ) -> AgentFlow:
        instance = self.agent_instances.get(name)
        if not instance:
            raise ValueError(f"No agent instance for '{name}'")
        if runtime_context:
            instance.set_runtime_context(runtime_context)
        return instance

    async def _aclose_single(self, name: str) -> bool:
        """
        Gracefully shut down a single runtime instance.
        Catalog entry (AgentSettings) is **retained**.
        """
        instance = self.agent_instances.pop(name, None)
        self.agent_classes.pop(name, None)

        if not instance:
            logger.warning("Attempted to close non-existent agent '%s'.", name)
            return False

        await self.supervisor.close_agents([instance])
        logger.info("🗑️ Unregistered agent '%s' from runtime.", name)
        return True

    async def aclose(self):
        """
        Shut down all runtime instances. Catalog stays intact.
        """
        for name in list(self.agent_instances.keys()):
            await self._aclose_single(name)

        self.supervisor.stop_retry_loop()
        # NOTE: do not clear self.agent_settings — the catalog is persistent
        self.agent_instances.clear()
        self.agent_classes.clear()
        logger.info("🗑️ AgentManager runtime cleanup complete (catalog preserved).")

    async def _ensure_running_instance(self, cfg: AgentSettings) -> AgentFlow:
        inst = self.agent_instances.get(cfg.name)
        if inst:
            return inst
        if not cfg.class_path:
            raise ValueError(f"Cannot (re)hydrate '{cfg.name}' without class_path.")
        cls: Type[AgentFlow] = self.loader._import_agent_class(cfg.class_path)
        instance = cls(agent_settings=cfg)
        if iscoroutinefunction(getattr(instance, "async_init", None)):
            await instance.async_init()
        self._register_loaded_agent(cfg.name, instance, cfg)
        return instance

    async def update_agent(self, new_settings: AgentSettings) -> bool:
        """
        Contract:
        - Update tuning/settings in memory + persist.
        - If `enabled=False`: close & unregister.
        - Leaders: crew changes are honored by a deterministic rewire pass.
        """
        name = new_settings.name
        merged_settings = self._merge_with_class_defaults(new_settings)

        # 1) Persist source of truth (DB)
        try:
            self.store.save(new_settings)
        except Exception:
            logger.exception(
                "Failed to persist agent '%s'; continuing with runtime update.", name
            )

        # 2) Disabled → unregister instance; keep latest settings for UI/discovery
        if new_settings.enabled is False:
            await self._aclose_single(name)  # unregister + shutdown
            self.agent_settings[name] = merged_settings  # keep the disabled snapshot
            # Safe & simple: leaders might reference this agent → rewire
            self.supervisor.inject_experts_into_leaders(
                agents_by_name=self.agent_instances,
                settings_by_name=self.agent_settings,
                classes_by_name=self.agent_classes,
            )
            logger.info("🛑 '%s' disabled & unregistered.", name)
            return True

        # 3) Enabled → ensure instance, then apply new settings atomically
        instance = await self._ensure_running_instance(merged_settings)
        instance.apply_settings(
            merged_settings
        )  # sets agent_settings + resolves _tuning
        self.agent_settings[name] = merged_settings  # registry snapshot

        # 4) Crew wiring: cheap to rebuild; avoids corner-cases
        #    If you want to optimize later, gate this on:
        #    - new_settings.kind == "leader"
        #    - or (prev_settings and prev_settings.crew != new_settings.crew)
        self.supervisor.inject_experts_into_leaders(
            agents_by_name=self.agent_instances,
            settings_by_name=self.agent_settings,
            classes_by_name=self.agent_classes,
        )

        logger.info("✅ '%s' updated.", name)
        return True

    async def delete_agent(self, name: str) -> bool:
        """
        Deletes an agent from the persistent store and unregisters it from runtime.
        """
        # 1) Shut down and remove from runtime registries
        await self._aclose_single(name)
        self.agent_classes.pop(name, None)

        # 2) Remove from the authoritative settings catalog
        settings = self.agent_settings.pop(name, None)
        if not settings:
            logger.warning(
                "Attempted to delete non-existent agent '%s' from catalog.", name
            )
            return False

        # 3) Remove from persistent storage
        try:
            self.store.delete(name)
        except Exception:
            logger.exception("Failed to delete agent '%s' from persistent store.", name)
            # We don't return False here because it's still removed from runtime
            # and in-memory catalogs, which is the primary goal.

        # 4) Rewire leaders to remove the deleted expert
        self.supervisor.inject_experts_into_leaders(
            agents_by_name=self.agent_instances,
            settings_by_name=self.agent_settings,
            classes_by_name=self.agent_classes,
        )

        logger.info(
            "🗑️ Agent '%s' and its settings have been permanently deleted.", name
        )
        return True
