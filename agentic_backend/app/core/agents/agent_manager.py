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
from typing import Dict, List

from app.common.structures import AgentSettings, Configuration
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_loader import AgentLoader
from app.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)


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

    def __init__(
        self, config: Configuration, agent_loader: AgentLoader, store: BaseAgentStore
    ):
        self.config = config
        self.store = store
        self.loader = agent_loader
        self.agent_settings: Dict[str, AgentSettings] = agent_loader.load_static()

    def get_agent_settings(self, name: str) -> AgentSettings | None:
        return self.agent_settings.get(name)

    def get_agentic_flows(self) -> List[AgentSettings]:
        return list(self.agent_settings.values())

    def _merge_with_class_defaults(self, settings: AgentSettings) -> AgentSettings:
        """Try to overlay class-declared defaults onto the given settings."""

        if not settings.class_path:
            return settings

        try:
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
            self.agent_settings[name] = merged_settings  # keep the disabled snapshot
            # Safe & simple: leaders might reference this agent → rewire
            # self.supervisor.inject_experts_into_leaders(
            #     agents_by_name=self.agent_instances,
            #     settings_by_name=self.agent_settings,
            #     classes_by_name=self.agent_classes,
            # )
            logger.info("🛑 '%s' disabled & unregistered.", name)
            logger.error("⚠️ TODO inject agent to leader.")
            return True

        self.agent_settings[name] = merged_settings  # registry snapshot

        # 4) Crew wiring: cheap to rebuild; avoids corner-cases
        #    If you want to optimize later, gate this on:
        #    - new_settings.kind == "leader"
        #    - or (prev_settings and prev_settings.crew != new_settings.crew)
        # self.supervisor.inject_experts_into_leaders(
        #     agents_by_name=self.agent_instances,
        #     settings_by_name=self.agent_settings,
        #     classes_by_name=self.agent_classes,
        # )

        logger.info("✅ '%s' updated.", name)
        logger.error("⚠️ TODO inject agent to leader.")
        return True

    async def delete_agent(self, name: str) -> bool:
        """
        Deletes an agent from the persistent store and unregisters it from runtime.
        """
        settings = self.agent_settings.pop(name, None)
        if not settings:
            logger.warning(
                "Attempted to delete non-existent agent '%s' from catalog.", name
            )
            return False

        # Remove from persistent storage
        try:
            self.store.delete(name)
        except Exception:
            logger.exception("Failed to delete agent '%s' from persistent store.", name)
            # We don't return False here because it's still removed from runtime
            # and in-memory catalogs, which is the primary goal.

        # 4) Rewire leaders to remove the deleted expert
        # self.supervisor.inject_experts_into_leaders(
        #     agents_by_name=self.agent_instances,
        #     settings_by_name=self.agent_settings,
        #     classes_by_name=self.agent_classes,
        # )

        logger.info(
            "🗑️ Agent '%s' and its settings have been permanently deleted.", name
        )
        logger.error("⚠️ TODO inject agent to leader.")
        return True
