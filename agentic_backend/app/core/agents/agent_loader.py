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

"""
AgentLoader — creates AgentFlow instances from multiple sources
(static config, persisted store, and Knowledge-Flow resources) and runs
their bounded async setup (`async_init()`).

Design contract:
- Loader is **pure creation** + **bounded init** only.
- Loader never starts long-lived work (streams/pollers) — that’s Supervisor’s job.
- Loader never mutates the registry — AgentManager (or a Registry) decides
  how to register/unregister/replace after instances are returned.

Public API:
- load_static() -> (instances, failed_map)
- load_persisted() -> instances
- load_resource_agents(...) -> (instances_to_add_or_update, names_to_replace)
"""

from __future__ import annotations

import importlib
import logging
from typing import Dict, Type

from app.common.structures import (
    AgentSettings,
    Configuration,
)
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)

SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


class AgentLoader:
    """
    Loads agents from static configuration and persistent storage. This
    class does not create or activate any agent instance, it only loads and check
    that configured or persisted agent settings are correct and still valid
    """

    def __init__(self, config: Configuration, store: BaseAgentStore):
        self.config = config
        self.store = store

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def load_static(self) -> Dict[str, AgentSettings]:
        """
        Build agents declared in configuration (enabled only), run `async_init()`,
        and return `(instances, failed_map)`. `failed_map` contains AgentSettings
        for static agents that failed to import/instantiate/init (so a retry loop
        can attempt later).
        """
        failed: Dict[str, AgentSettings] = {}
        successful: Dict[str, AgentSettings] = {}
        for agent_cfg in self.config.ai.agents:
            if not agent_cfg.enabled:
                continue
            if not agent_cfg.class_path:
                logger.warning(
                    "No class_path for static agent '%s' — skipping.",
                    agent_cfg.name,
                )
                failed[agent_cfg.name] = agent_cfg
                continue
            try:
                cls = self._import_agent_class(agent_cfg.class_path)
                if not issubclass(cls, AgentFlow):
                    logger.error(
                        "Class '%s' is not AgentFlow for '%s'",
                        agent_cfg.class_path,
                        agent_cfg.name,
                    )
                    failed[agent_cfg.name] = agent_cfg
                    continue
                logger.info("✅ Static agent ready: %s", agent_cfg.name)
                successful[agent_cfg.name] = agent_cfg
            except Exception as e:
                logger.exception(
                    "❌ Failed to construct static agent '%s': %s", agent_cfg.name, e
                )
                failed[agent_cfg.name] = agent_cfg

        return successful

    def load_persisted(self) -> Dict[str, AgentSettings]:
        """
        Build agents from persistent storage (e.g., DuckDB), run `async_init()`,
        and return ready instances. Agents with missing/invalid class_path are skipped.
        """
        out: Dict[str, AgentSettings] = {}

        for agent_settings in self.store.load_all():
            if not agent_settings.class_path:
                logger.warning(
                    "No class_path for agent '%s' — skipping.", agent_settings.name
                )
                continue

            if not agent_settings.enabled:
                logger.info(
                    "↪️ Skipping disabled persisted agent: %s", agent_settings.name
                )
                continue

            try:
                cls = self._import_agent_class(agent_settings.class_path)
                if not issubclass(cls, AgentFlow):
                    logger.error(
                        "Class '%s' is not AgentFlow for '%s'",
                        agent_settings.class_path,
                        agent_settings.name,
                    )
                    continue

                logger.info(
                    "✅ Persisted agent loaded: %s (%s)",
                    agent_settings.name,
                    agent_settings.class_path,
                )
                out[agent_settings.name] = agent_settings
            except ModuleNotFoundError:
                logger.error(
                    "❌ Failed to load persisted agent '%s' (ModuleNotFoundError). Removing stale entry from store.",
                    agent_settings.name,
                )
                try:
                    self.store.delete(agent_settings.name)
                    logger.info(
                        "🗑️ Successfully deleted stale agent '%s' from persistent store.",
                        agent_settings.name,
                    )
                except Exception:
                    logger.exception(
                        "⚠️ Failed to delete stale agent '%s' from persistent store.",
                        agent_settings.name,
                    )
            except Exception as e:
                logger.exception(
                    "❌ Failed to load persisted agent '%s': %s",
                    agent_settings.name,
                    e,
                )

        return out

    def _import_agent_class(self, class_path: str) -> Type[AgentFlow]:
        """
        Dynamically import an agent class from its full class path.
        Raises ImportError if the class cannot be found.

        This method is only used to check class validity during loading;
        actual instantiation is done elsewhere.
        """
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        if class_name == "Leader":
            raise ImportError(f"Class '{class_name}' not found in '{module_name}'")
        return getattr(module, class_name)
