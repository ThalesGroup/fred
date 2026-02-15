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
from typing import Dict, List, Tuple, cast

from agentic_backend.application_context import (
    get_mcp_configuration,
    get_mcp_server_manager,
)
from agentic_backend.common.structures import (
    AgentChatOptions,
    AgentSettings,
    Configuration,
    Leader,
)
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    MCPServerConfiguration,
)
from agentic_backend.core.agents.store.base_agent_store import (
    BaseAgentStore,
)

logger = logging.getLogger(__name__)


class AgentUpdatesDisabled(Exception):
    """Raised when updates are attempted while static-config-only mode is enabled."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message or "Agent updates are disabled in static-config-only mode."
        )


class AgentAlreadyExistsException(Exception):
    pass


class AgentManager:
    """
    Manages the full lifecycle of AI agents (leaders and experts).

    The persistent store (Postgres) is the single source of truth — no in-memory
    cache is kept, making the manager safe for multi-worker / multi-replica deployments.

    Responsibilities:
    - Reconciling static agents (configuration.yaml) with persisted state at bootstrap.
    - Creating, updating, and deleting dynamic agents via the store.
    - Providing runtime agent discovery (e.g., for the UI) by querying the store.
    """

    def __init__(
        self, config: Configuration, agent_loader: AgentLoader, store: BaseAgentStore
    ):
        self.config = config
        self.store = store
        self.loader = agent_loader
        self.use_static_config_only = config.ai.use_static_config_only
        logger.info(
            "[AGENTS] AgentManager initialized with static_config_only=%s",
            self.use_static_config_only,
        )

    async def get_agent_settings(self, agent_id: str) -> AgentSettings | None:
        return await self.store.get(agent_id)

    @staticmethod
    def _chat_options_from_tuning(tuning: AgentTuning) -> AgentChatOptions:
        """
        Extract chat option booleans from tuning.fields (keys starting with chat_options.).
        """
        if not tuning or not tuning.fields:
            return AgentChatOptions()
        overrides: Dict[str, bool] = {}
        for f in tuning.fields:
            if not f.key or not f.key.startswith("chat_options."):
                continue
            key = f.key.split(".", 1)[1]
            if isinstance(f.default, bool):
                overrides[key] = f.default
        return AgentChatOptions(**overrides)

    async def get_mcp_servers_configuration(self) -> List[MCPServerConfiguration]:
        try:
            manager = await get_mcp_server_manager()
            return manager.list_servers()
        except Exception:
            # Fallback to static configuration if manager unavailable (e.g., early boot)
            return [s for s in get_mcp_configuration().servers if s.enabled]

    async def create_dynamic_agent(
        self, agent_settings: AgentSettings, agent_tuning: AgentTuning
    ) -> None:
        """
        Creates a new dynamic agent and persists it to the store.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        existing = await self.store.get(agent_settings.id)
        if existing:
            raise AgentAlreadyExistsException(
                f"Agent '{agent_settings.id}' already exists."
            )

        # Keep chat_options consistent with tuning defaults at creation time.
        try:
            agent_settings.chat_options = self._chat_options_from_tuning(agent_tuning)
        except Exception:
            logger.debug(
                "[AGENTS] Failed to derive chat_options from tuning for %s at creation time",
                agent_settings.id,
                exc_info=True,
            )

        await self.store.save(agent_settings, agent_tuning)
        logger.info("[AGENTS] agent=%s registered as dynamic agent.", agent_settings.id)

    async def update_agent(self, new_settings: AgentSettings) -> bool:
        """
        Updates an agent's settings and tuning in the persistent store.
        Leaders: crew changes are logged for observability.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        if new_settings.type == "leader":
            new_leader_settings = cast(Leader, new_settings)
            old_leader_settings = cast(Leader, await self.store.get(new_settings.id))
            if old_leader_settings:
                old_crew = set(old_leader_settings.crew or [])
                new_crew = set(new_leader_settings.crew or [])
                if old_crew != new_crew:
                    logger.info(
                        "[AGENTS] leader=%s crew changed from %s to %s",
                        new_settings.id,
                        old_crew,
                        new_crew,
                    )

        agent_id = new_settings.id
        tunings = new_settings.tuning
        if not tunings:
            return False
        logger.info("[AGENTS] agent=%s new_tuning=%s", agent_id, tunings.dump())
        # Sync chat_options with tuning fields (chat_options.*) to keep UI toggles consistent.
        try:
            new_settings.chat_options = self._chat_options_from_tuning(tunings)
        except Exception:
            logger.debug(
                "[AGENTS] Failed to sync chat_options from tuning for %s",
                agent_id,
                exc_info=True,
            )
        try:
            await self.store.save(new_settings, tunings)
        except Exception:
            logger.exception(
                "Failed to persist agent '%s'.",
                agent_id,
            )
            return False

        return True

    async def delete_agent(self, agent_id: str) -> bool:
        """
        Deletes an agent from the persistent store.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        existing = await self.store.get(agent_id)
        if not existing:
            logger.warning(
                "[AGENTS] agent=%s not found in store, nothing to delete.", agent_id
            )
            return False

        try:
            await self.store.delete(agent_id)
        except Exception:
            logger.exception(
                "[AGENTS] agent=%s could not be deleted from persistent store.",
                agent_id,
            )
            return False

        return True

    async def bootstrap(self):
        """
        Bootstraps the agent manager by loading agents from static configuration,
        reconciling with persisted storage, and saving the merged result to the store.

        The store is the single source of truth for all workers/replicas.

        The principles are simple:
        1. Static agents (from configuration.yaml) define the base settings and default tunings.
        2. Persisted agents (from the database) override tunings for static agents.
        3. Dynamically created agents (persisted-only) are kept as-is in the database.
        """
        # 1. Load static agent definitions from YAML (instantiates classes to get default tunings)
        static_instances = self.loader.load_static()

        static_catalogue: Dict[str, Tuple[AgentSettings, AgentTuning]] = {}
        for instance in static_instances:
            agent_id = instance.get_id()
            settings = instance.get_agent_settings()
            tunings = instance.get_agent_tunings()
            static_catalogue[agent_id] = (settings, tunings)
            logger.info(
                "[AGENTS] agent=%s loaded from YAML. Class: %s",
                agent_id,
                settings.class_path,
            )

        # 2. Load persisted state directly from the store (no class instantiation needed)
        persisted_state: Dict[str, AgentSettings] = {}
        if not self.use_static_config_only:
            persisted_agents = await self.store.load_all()
            persisted_state = {agent.id: agent for agent in persisted_agents}
        else:
            logger.warning(
                "[AGENTS] 'use_static_config_only' is ENABLED. "
                "Skipping persisted agent overrides."
            )

        # 3. Reconcile: for static agents, merge YAML settings with persisted tunings
        #    and save to the store so all workers see consistent state.
        for agent_id, (static_settings, static_tunings) in sorted(
            static_catalogue.items()
        ):
            persisted = persisted_state.get(agent_id)

            if persisted and persisted.tuning:
                logger.info(
                    "[AGENTS] agent=%s found in YAML and store. Merging with persisted tunings.",
                    agent_id,
                )
                effective_tuning = persisted.tuning
            else:
                logger.info(
                    "[AGENTS] agent=%s using YAML defaults.",
                    agent_id,
                )
                effective_tuning = static_tunings

            final_settings = static_settings.model_copy(
                update={"tuning": effective_tuning}
            )

            try:
                await self.store.save(final_settings, effective_tuning)
            except Exception:
                logger.exception(
                    "[AGENTS] Failed to save reconciled settings for '%s'", agent_id
                )

    async def restore_static_agents(self, *, force_overwrite: bool = True) -> None:
        """
        Re-seed static agents from configuration into the store and reload the catalog.
        """
        if self.use_static_config_only:
            logger.info(
                "[AGENTS] Static-config-only mode active; nothing to restore into store."
            )
            return

        for agent_cfg in self.config.ai.agents:
            tuning = agent_cfg.tuning
            if not tuning:
                try:
                    if agent_cfg.class_path:
                        cls = self.loader._import_agent_class(agent_cfg.class_path)
                        tuning = getattr(cls, "tuning", None)
                        if tuning:
                            logger.info(
                                "[AGENTS] Restore: using class default tuning for '%s'",
                                agent_cfg.id,
                            )
                except Exception:
                    logger.exception(
                        "[AGENTS] Restore: failed to load class for '%s' to get default tuning",
                        agent_cfg.id,
                    )
            if not tuning:
                logger.warning(
                    "[AGENTS] Skipping static agent '%s' restore: missing tuning.",
                    agent_cfg.id,
                )
                continue

            settings_with_tuning = agent_cfg.model_copy(update={"tuning": tuning})

            if force_overwrite:
                try:
                    await self.store.delete(agent_cfg.id)
                    logger.info(
                        "[AGENTS] Overwrite restore: deleted persisted agent '%s'",
                        agent_cfg.id,
                    )
                except Exception:
                    logger.exception(
                        "[AGENTS] Overwrite restore: failed to delete persisted agent '%s'",
                        agent_cfg.id,
                    )

            try:
                await self.store.save(settings_with_tuning, tuning)
                logger.info(
                    "[AGENTS] Restored static agent '%s' into store", agent_cfg.id
                )
            except Exception:
                logger.exception(
                    "[AGENTS] Failed to restore static agent '%s'", agent_cfg.id
                )

        await self.store.mark_static_seeded()
        # Re-bootstrap to reconcile static agents with the store
        await self.bootstrap()
