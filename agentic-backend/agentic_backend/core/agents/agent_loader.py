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

from __future__ import annotations

import importlib
import logging
from typing import List, Type

from agentic_backend.common.structures import (
    Configuration,
)
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)


class AgentLoader:
    """
    Loads agents from startu configuration.yaml and persistent storage. This
    class does not create or activate any agent instance, it only loads and check
    that configured or persisted agent settings are correct and still valid.

    Instances are only created to provide the agent manager with easy access to
    their class defaults (tunings) as well as the settings defined in the configuration.yaml
    """

    def __init__(self, config: Configuration, store: BaseAgentStore):
        self.config = config
        self.store = store

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def load_static(self) -> List[AgentFlow]:
        """
        Build agents declared in configuration (enabled only), run `async_init()`,
        and return `(instances, failed_map)`. `failed_map` contains AgentSettings
        for static agents that failed to import/instantiate/init (so a retry loop
        can attempt later).
        """
        instances: List[AgentFlow] = []
        for agent_cfg in self.config.ai.agents:
            if not agent_cfg.enabled:
                continue
            if not agent_cfg.class_path:
                logger.warning(
                    "No class_path for static agent '%s' — skipping.",
                    agent_cfg.id,
                )
                continue
            try:
                cls = self._import_agent_class(agent_cfg.class_path)
                if not issubclass(cls, AgentFlow):
                    logger.error(
                        "Class '%s' is not AgentFlow for '%s'",
                        agent_cfg.class_path,
                        agent_cfg.id,
                    )
                    continue
                inst: AgentFlow = cls(agent_settings=agent_cfg)
                instances.append(inst)
            except Exception as e:
                logger.exception(
                    "❌ Failed to construct static agent '%s': %s", agent_cfg.id, e
                )

        return instances

    async def load_persisted(self) -> List[AgentFlow]:
        """
        Build agents from persistent storage (e.g., DuckDB), run `async_init()`,
        and return ready instances. Agents with missing/invalid class_path are skipped.
        """
        out: List[AgentFlow] = []

        for agent_settings in await self.store.load_all():
            if not agent_settings.class_path:
                logger.warning(
                    "agent=%s No class_path found — deleting stale entry from store.",
                    agent_settings.id,
                )
                try:
                    await self.store.delete(agent_settings.id)
                except Exception:
                    logger.exception(
                        "agent=%s Failed to delete stale entry without class_path",
                        agent_settings.id,
                    )
                continue

            try:
                cls = self._import_agent_class(agent_settings.class_path)
                if not issubclass(cls, AgentFlow):
                    logger.error(
                        "agent=%s class=%s is not AgentFlow",
                        agent_settings.id,
                        agent_settings.class_path,
                    )
                    continue

                logger.debug(
                    "agent=%s class=%s loaded",
                    agent_settings.id,
                    agent_settings.class_path,
                )
                inst: AgentFlow = cls(agent_settings=agent_settings)
                out.append(inst)
            except ModuleNotFoundError:
                logger.error(
                    "agent=%s Failed to load persisted agent (ModuleNotFoundError). Removing stale entry from store.",
                    agent_settings.id,
                )
                try:
                    await self.store.delete(agent_settings.id)
                    logger.info(
                        "agent=%s Successfully deleted stale agent from persistent store.",
                        agent_settings.id,
                    )
                except Exception:
                    logger.exception(
                        "agent=%s Failed to delete stale agent from persistent store.",
                        agent_settings.id,
                    )
            except Exception as e:
                logger.exception(
                    "agent=%s Failed to load persisted agent: %s",
                    agent_settings.id,
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
