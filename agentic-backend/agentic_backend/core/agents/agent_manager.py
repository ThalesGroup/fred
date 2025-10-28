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

from agentic_backend.application_context import get_mcp_configuration
from agentic_backend.common.structures import AgentSettings, Configuration, Leader
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    MCPServerConfiguration,
    MCPServerRef,
)
from agentic_backend.core.agents.store.base_agent_store import (
    SCOPE_GLOBAL,
    SCOPE_USER,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)


# agentic_backend/core/agents/agent_service.py (or exceptions.py if you have one)


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
        self.agent_settings: Dict[str, AgentSettings] = {}
        self.agent_instances: Dict[str, AgentFlow] = {}
        self.use_static_config_only = config.ai.use_static_config_only
        logger.info(
            "[AGENTS] AgentManager initialized with static_config_only=%s",
            self.use_static_config_only,
        )

    def get_agent_settings(self, name: str) -> AgentSettings | None:
        return self.agent_settings.get(name)

    def get_agentic_flows(self) -> List[AgentSettings]:
        return list(self.agent_settings.values())

    def get_mcp_servers_configuration(self) -> List[MCPServerConfiguration]:
        return get_mcp_configuration().servers

    def log_current_settings(self):
        for name, settings in self.agent_settings.items():
            tuning = settings.tuning
            logger.debug(
                "[AGENTS] agent=%s current_tuning=%s",
                name,
                tuning.dump() if tuning else "N/A",
            )

    def create_dynamic_agent(
        self, agent_settings: AgentSettings, agent_tuning: AgentTuning
    ) -> None:
        """
        Registers a new dynamic agent into the runtime catalog.
        Note: This does not persist the agent; use the AgentService for that.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        existing = self.store.get(agent_settings.name)
        if existing:
            raise AgentAlreadyExistsException(
                f"Agent '{agent_settings.name}' already exists."
            )

        self.store.save(agent_settings, agent_tuning)

        self.agent_settings[agent_settings.name] = agent_settings
        logger.info(
            "[AGENTS] agent=%s registered as dynamic agent.", agent_settings.name
        )

    async def update_agent(self, new_settings: AgentSettings, is_global: bool) -> bool:
        """
        Contract:
        - Update tuning/settings in memory + persist.
        - If `enabled=False`: close & unregister.
        - Leaders: crew changes are honored by a deterministic rewire pass.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        if new_settings.type == "leader":
            new_leader_settings = cast(Leader, new_settings)
            old_leader_settings = cast(
                Leader, self.agent_settings.get(new_settings.name)
            )
            if old_leader_settings:
                old_crew = set(old_leader_settings.crew or [])
                new_crew = set(new_leader_settings.crew or [])
                if old_crew != new_crew:
                    logger.info(
                        "[AGENTS] leader=%s crew changed from %s to %s",
                        new_settings.name,
                        old_crew,
                        new_crew,
                    )
                    # If the crew has changed, we need to rewire the agent's connections

        name = new_settings.name
        tunings = new_settings.tuning
        if not tunings:
            return False
        logger.info("[AGENTS] agent=%s new_tuning=%s", name, tunings.dump())
        # 1) Persist source of truth (DB)
        try:
            self.store.save(
                new_settings, tunings, scope=SCOPE_GLOBAL if is_global else SCOPE_USER
            )
        except Exception:
            logger.exception(
                "Failed to persist agent '%s'; continuing with runtime update.", name
            )
            return False

        self.agent_settings[name] = new_settings
        return True

    async def delete_agent(self, name: str) -> bool:
        """
        Deletes an agent from the persistent store and unregisters it from runtime.
        """
        if self.use_static_config_only:
            raise AgentUpdatesDisabled()

        settings = self.agent_settings.pop(name, None)
        if not settings:
            logger.warning("[AGENTS] agent=%s deleted but not found in memory.", name)
            return False

        try:
            self.store.delete(name)
        except Exception:
            logger.exception(
                "[AGENTS] agent=%s could not be deleted from persistent store.", name
            )
            # We don't return False here because it's still removed from runtime
            # and in-memory catalogs, which is the primary goal.

        return True

    async def bootstrap(self):
        """
        Bootstraps the agent manager by loading agents from both static configuration
        and persisted storage, reconciling any conflicts, and registering them into
        the runtime catalog.

        The principles are simple:
        1. Static agents (from configuration.yaml) define the base settings. They provide together with their hard-coded defaults the default tunings.
        2. Persisted agents (from the database) override tunings for static agents.
        3. Dynamically created agents (persisted-only) are loaded as-is from the database.

        """
        # 1. Load and Map Data
        static_instances = self.loader.load_static()
        if self.use_static_config_only:
            logger.warning(
                "[AGENTS] 'use_static_config_only' is ENABLED. Skipping all persistent agent configuration (DB)."
            )
            persisted_instances = []
        else:
            persisted_instances = self.loader.load_persisted()

        static_catalogue: Dict[str, Tuple[AgentSettings, AgentTuning]] = {}
        persisted_state: Dict[str, Tuple[AgentSettings, AgentTuning]] = {}
        agents_to_load: Dict[str, AgentSettings] = {}
        for instance in static_instances:
            # Assuming instance structure is accessible like a dictionary or simple object
            name = instance.get_name()
            settings = instance.get_agent_settings()
            tunings = instance.get_agent_tunings()
            static_catalogue[name] = (settings, tunings)
            logger.info(
                "[AGENTS] agent=%s loaded from YAML. Class: %s",
                name,
                settings.class_path,
            )

        for instance in persisted_instances:
            name = instance.get_name()
            settings = instance.get_agent_settings()
            tunings = instance.get_agent_tunings()
            persisted_state[name] = (settings, tunings)
            logger.info(
                "[AGENTS] agent=%s loaded from persistent store. Class: %s",
                name,
                settings.class_path,
            )

        # ----------------------------------------------------------------------
        # 2. Reconcile and Log Decisions
        # ----------------------------------------------------------------------

        all_names = set(static_catalogue.keys()) | set(persisted_state.keys())
        for name in sorted(list(all_names)):
            is_static = name in static_catalogue
            is_persisted = name in persisted_state

            if is_static and is_persisted:
                # CONFLICT: Static agent exists AND user has saved a persisted state (usually tuning)
                static_settings, _ = static_catalogue[name]
                _, persisted_tunings = persisted_state[name]

                logger.info(
                    "[AGENTS] agent=%s found in YAML and persistent store with global scope tunings. Using persisted tunings.",
                    name,
                )
                final_settings = static_settings.model_copy(
                    update={"tuning": persisted_tunings}
                )
                agents_to_load[name] = final_settings

            elif is_static and not is_persisted:
                # STATIC-ONLY: Agent is defined in code but has no user changes
                static_settings, static_tunings = static_catalogue[name]

                logger.info(
                    "[AGENTS] agent=%s is only defined in YAML configuration. Using it as is.",
                    name,
                )
                final_settings = static_settings.model_copy(
                    update={"tuning": static_tunings}
                )
                agents_to_load[name] = final_settings

            elif is_persisted and not is_static:
                # PERSISTED-ONLY: Agent was created dynamically (e.g., via UI) and stored in DB
                persisted_settings, persisted_tunings = persisted_state[name]

                logger.info(
                    "[AGENTS] agent=%s loaded from persistent store. Delete it from the database to remove it from runtime.",
                    name,
                )
                agents_to_load[name] = persisted_settings
                final_settings = persisted_settings.model_copy(
                    update={"tuning": persisted_tunings}
                )
                agents_to_load[name] = final_settings

        for name, settings in agents_to_load.items():
            logger.info(
                "[AGENTS] agent=%s registered with global scope tunings into runtime catalog",
                name,
            )
            logger.info(
                "[AGENTS] agent=%s tuning=%s",
                name,
                settings.tuning.dump() if settings.tuning else "N/A",
            )
            self.agent_settings[name] = settings
