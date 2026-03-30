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
from dataclasses import dataclass
from typing import List, Type

from agentic_backend.common.structures import (
    AgentSettings,
    Configuration,
)
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.base_agent_store import BaseAgentStore
from agentic_backend.core.agents.v2.legacy_bridge.agent_settings_bridge import (
    apply_profile_defaults_to_settings,
    build_definition_from_settings,
    definition_to_agent_settings,
    definition_to_agent_tuning,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoadedAgentCatalogueEntry:
    settings: AgentSettings
    tuning: AgentTuning


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

    def load_static(self) -> List[LoadedAgentCatalogueEntry]:
        """
        Resolve static agent declarations into catalogue entries.

        For legacy `AgentFlow`, the class instance remains the source of truth for
        default settings and tuning.
        For v2 definitions, we derive the current `AgentSettings` compatibility
        view directly from the pure definition.
        """
        entries: List[LoadedAgentCatalogueEntry] = []
        for agent_cfg in self.config.ai.agents:
            if not agent_cfg.enabled:
                continue
            if not agent_cfg.class_path and not agent_cfg.definition_ref:
                logger.warning(
                    "No class_path/definition_ref for static agent '%s' — skipping.",
                    agent_cfg.id,
                )
                continue
            try:
                resolved = resolve_agent_reference(
                    class_path=agent_cfg.class_path,
                    definition_ref=agent_cfg.definition_ref,
                )
                if resolved.implementation_kind == AgentImplementationKind.FLOW:
                    cls = self._import_agent_class(resolved.class_path)
                    inst: AgentFlow = cls(agent_settings=agent_cfg)
                    entries.append(
                        LoadedAgentCatalogueEntry(
                            settings=inst.get_agent_settings(),
                            tuning=inst.get_agent_tunings(),
                        )
                    )
                    continue

                definition = build_definition_from_settings(
                    definition_class=resolved.cls,
                    settings=agent_cfg,
                )
                effective_settings = apply_profile_defaults_to_settings(
                    definition=definition,
                    settings=agent_cfg,
                )
                derived = definition_to_agent_settings(
                    definition,
                    class_path=(
                        None
                        if resolved.definition_ref is not None
                        else resolved.class_path
                    ),
                    definition_ref=resolved.definition_ref,
                    enabled=agent_cfg.enabled,
                ).model_copy(
                    update={
                        "id": agent_cfg.id,
                        "name": agent_cfg.name,
                        "team_id": agent_cfg.team_id,
                        "enabled": agent_cfg.enabled,
                        "metadata": agent_cfg.metadata,
                        "definition_ref": resolved.definition_ref,
                        "chat_options": effective_settings.chat_options,
                    }
                )
                effective_tuning = (
                    effective_settings.tuning or definition_to_agent_tuning(definition)
                )
                entries.append(
                    LoadedAgentCatalogueEntry(
                        settings=derived.model_copy(
                            update={"tuning": effective_tuning}
                        ),
                        tuning=effective_tuning,
                    )
                )
            except Exception as e:
                logger.exception(
                    "❌ Failed to construct static agent '%s': %s", agent_cfg.id, e
                )

        return entries

    async def load_persisted(self) -> List[AgentFlow]:
        """
        Build agents from persistent storage (e.g., DuckDB), run `async_init()`,
        and return ready instances. Agents with missing/invalid class_path are skipped.
        """
        out: List[AgentFlow] = []

        for agent_settings in await self.store.load_all():
            if not agent_settings.class_path and not agent_settings.definition_ref:
                logger.warning(
                    "agent=%s No class_path/definition_ref found — deleting stale entry from store.",
                    agent_settings.id,
                )
                try:
                    await self.store.delete(agent_settings.id)
                except Exception:
                    logger.exception(
                        "agent=%s Failed to delete stale entry without class_path/definition_ref",
                        agent_settings.id,
                    )
                continue

            try:
                resolved = resolve_agent_reference(
                    class_path=agent_settings.class_path,
                    definition_ref=agent_settings.definition_ref,
                )
                if resolved.implementation_kind != AgentImplementationKind.FLOW:
                    logger.debug(
                        "agent=%s persisted entry is v2 definition; AgentLoader.load_persisted() skips runtime instantiation.",
                        agent_settings.id,
                    )
                    continue

                cls = self._import_agent_class(resolved.class_path)
                if not issubclass(cls, AgentFlow):
                    logger.error(
                        "agent=%s class=%s is not AgentFlow",
                        agent_settings.id,
                        resolved.class_path,
                    )
                    continue

                logger.debug(
                    "agent=%s class=%s loaded",
                    agent_settings.id,
                    resolved.class_path,
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
        if class_name in {"Leader", "LeaderFlow"}:
            raise ImportError(
                f"Class '{class_name}' is deprecated and no longer supported."
            )
        return getattr(module, class_name)
