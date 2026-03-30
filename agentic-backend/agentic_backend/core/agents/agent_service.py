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
import logging
from typing import List, Optional, Union
from uuid import uuid4

from fred_core import (
    ORGANIZATION_ID,
    Action,
    AgentPermission,
    KeycloakUser,
    OrganizationPermission,
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    authorize,
)
from fred_core.common import OwnerFilter

from agentic_backend.agents.v2 import BasicReActDefinition
from agentic_backend.agents.v2.definition_refs import BASIC_REACT_DEFINITION_REF
from agentic_backend.application_context import get_agent_store, get_rebac_engine
from agentic_backend.common.structures import (
    Agent,
    AgentSettings,
)
from agentic_backend.core.agents.agent_class_resolver import (
    ResolvedFlowAgentClass,
    ResolvedV2AgentClass,
    resolve_agent_class,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.v2.legacy_bridge.agent_settings_bridge import (
    apply_profile_defaults_to_settings,
    apply_react_profile_to_definition,
    build_definition_from_settings,
    definition_to_agent_settings,
    definition_to_agent_tuning,
    instantiate_definition_class,
)
from agentic_backend.core.agents.v2.legacy_bridge.react_profile_bridge import (
    get_react_profile,
    is_react_profile_allowed,
)

logger = logging.getLogger(__name__)


class MissingTeamIdError(Exception):
    """Raised when owner_filter is 'team' but no team_id is provided."""

    pass


class InvalidClassPathError(Exception):
    """Raised when a class_path is not a valid, importable module.Class."""

    pass


class ImmutableTeamIdError(Exception):
    """Raised when an update attempts to change an agent team ownership field."""

    pass


def _validate_class_path(class_path: str) -> type[object]:
    """Validate that class_path is importable and supported by Fred.

    Returns the resolved class on success.
    Raises InvalidClassPathError if the path is invalid.
    """
    try:
        return resolve_agent_class(class_path).cls
    except ValueError as exc:
        raise InvalidClassPathError(
            f"Invalid class_path format (expected module.Class): {class_path}"
        ) from exc
    except Exception as exc:
        raise InvalidClassPathError(str(exc)) from exc


def _class_path(obj_or_type: Union[type, object]) -> str:
    """Return fully-qualified class path, e.g. 'agentic_backend.agents.basic_react_agent.BasicReActAgent'."""
    t: type = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
    return f"{t.__module__}.{t.__name__}"


class AgentService:
    def __init__(self, agent_manager: AgentManager):
        self.agent_store = get_agent_store()
        self.agent_manager = agent_manager
        self.rebac = get_rebac_engine()

    def _enrich_settings_with_class_tuning_defaults(
        self, agent_settings: AgentSettings
    ) -> AgentSettings:
        """
        Backward-compat enrichment:
        - add missing tuning fields from class defaults (by key)
        - recompute chat_options from the effective tuning
        """
        if not agent_settings.class_path and not agent_settings.definition_ref:
            return agent_settings

        try:
            resolved = resolve_agent_reference(
                class_path=agent_settings.class_path,
                definition_ref=agent_settings.definition_ref,
            )
        except Exception:
            return agent_settings

        if (
            agent_settings.definition_ref
            and agent_settings.class_path != resolved.class_path
        ):
            agent_settings = agent_settings.model_copy(update={"class_path": None})

        agent_cls = resolved.cls

        if isinstance(resolved, ResolvedFlowAgentClass):
            class_tuning = getattr(agent_cls, "tuning", None)
            if class_tuning is None:
                return agent_settings
        else:
            definition = build_definition_from_settings(
                definition_class=resolved.cls,
                settings=agent_settings,
            )
            effective_settings = apply_profile_defaults_to_settings(
                definition=definition,
                settings=agent_settings,
            )
            class_tuning = effective_settings.tuning or definition_to_agent_tuning(
                definition
            )
            if (
                agent_settings.chat_options != effective_settings.chat_options
                or agent_settings.tuning != effective_settings.tuning
            ):
                agent_settings = agent_settings.model_copy(
                    update={
                        "tuning": effective_settings.tuning,
                        "chat_options": effective_settings.chat_options,
                    }
                )

        current_tuning = agent_settings.tuning or class_tuning
        current_fields = list(current_tuning.fields or [])
        seen_keys = {f.key for f in current_fields if f.key}
        changed = agent_settings.tuning is None

        for spec in class_tuning.fields or []:
            if spec.key and spec.key not in seen_keys:
                current_fields.append(spec.model_copy(deep=True))
                seen_keys.add(spec.key)
                changed = True

        effective_tuning = current_tuning
        if changed:
            effective_tuning = current_tuning.model_copy(
                update={"fields": current_fields}
            )

        derived_chat_options = AgentManager._chat_options_from_tuning(effective_tuning)
        if agent_settings.chat_options != derived_chat_options or changed:
            return agent_settings.model_copy(
                update={
                    "tuning": effective_tuning,
                    "chat_options": derived_chat_options,
                }
            )
        return agent_settings

    async def _enrich_settings_with_authoritative_team_id(
        self, agent_settings: AgentSettings
    ) -> AgentSettings:
        """Backfill missing team_id from ReBAC ownership for legacy agents."""
        if agent_settings.team_id:
            return agent_settings

        try:
            owner_teams = await self.rebac.lookup_subjects(
                resource=RebacReference(type=Resource.AGENT, id=agent_settings.id),
                relation=RelationType.OWNER,
                subject_type=Resource.TEAM,
            )
        except Exception:
            logger.exception(
                "[AGENTS] Failed to resolve authoritative team owner for agent '%s'",
                agent_settings.id,
            )
            return agent_settings

        if (
            isinstance(owner_teams, RebacDisabledResult)
            or not owner_teams
            or len(owner_teams) == 0
        ):
            return agent_settings

        team_ids = [ref.id for ref in owner_teams]

        if len(team_ids) > 1:
            logger.warning(
                "[AGENTS] agent='%s' has multiple team owners in ReBAC (%s); using '%s'",
                agent_settings.id,
                team_ids,
                team_ids[0],
            )

        return agent_settings.model_copy(update={"team_id": team_ids[0]})

    async def _enrich_agent_settings(
        self, agent_settings: AgentSettings
    ) -> AgentSettings:
        with_team_id = await self._enrich_settings_with_authoritative_team_id(
            agent_settings
        )
        return self._enrich_settings_with_class_tuning_defaults(with_team_id)

    async def list_agents(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        agents = await self.agent_store.load_all()

        authorized_ids = await self._resolve_authorized_agent_ids(
            user, owner_filter, team_id
        )
        if authorized_ids is not None:
            agents = [a for a in agents if a.id in authorized_ids]
        return list(
            await asyncio.gather(
                *(self._enrich_agent_settings(agent) for agent in agents),
                return_exceptions=False,
            )
        )

    async def list_declared_class_paths(self, user: KeycloakUser) -> List[str]:
        """
        Return all unique class paths declared in the static configuration.

        Why:
        - The UI can use this list as a controlled source for class_path autocomplete.
        - Permissions stay aligned with class_path edition permissions.
        """
        await self.rebac.check_user_permission_or_raise(
            user,
            OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH,
            ORGANIZATION_ID,
        )

        class_paths = {
            agent_cfg.class_path.strip()
            for agent_cfg in self.agent_manager.config.ai.agents
            if agent_cfg.class_path and agent_cfg.class_path.strip()
        }
        return sorted(class_paths)

    async def list_declared_definition_refs(self, user: KeycloakUser) -> List[str]:
        """
        Return v2 definition refs declared in the static catalog.

        Why:
        - Only refs explicitly listed in agents_catalog.yaml are presented to the UI.
        - Mirrors list_declared_class_paths: the catalog is the gatekeeper for
          both v1 class paths and v2 definition refs.
        - Permissions stay aligned with advanced agent creation.
        """
        await self.rebac.check_user_permission_or_raise(
            user,
            OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH,
            ORGANIZATION_ID,
        )
        definition_refs = {
            agent_cfg.definition_ref.strip()
            for agent_cfg in self.agent_manager.config.ai.agents
            if agent_cfg.definition_ref and agent_cfg.definition_ref.strip()
        }
        return sorted(definition_refs)

    async def get_agent_by_id(
        self, user: KeycloakUser, agent_id: str
    ) -> AgentSettings | None:
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.READ, agent_id
        )

        settings = await self.agent_manager.get_agent_settings(agent_id)
        if settings is None:
            return None
        return await self._enrich_agent_settings(settings)

    async def create_v2_agent(
        self,
        user: KeycloakUser,
        name: str,
        *,
        team_id: Optional[str] = None,
        definition_ref: Optional[str] = None,
        profile_id: Optional[str] = None,
    ):
        """
        Create a v2 agent. Two choices:

        1. ``definition_ref`` — fixed-behaviour agent wired in code, e.g. ``"v2.react.prometheus_expert"``.
        2. ``profile_id`` only — configurable BasicReAct agent with a starting profile, e.g. ``"custodian"``.
           Omitting both falls back to a blank BasicReAct agent.

        ``profile_id`` is only valid when ``definition_ref`` is omitted or is ``v2.react.basic``.
        """
        if team_id:
            await self.rebac.check_user_team_permission_or_raise(
                user=user,
                permission=TeamPermission.CAN_UPDATE_AGENTS,
                team_id=team_id,
            )

        normalized_profile_id = profile_id.strip() if profile_id else None
        normalized_definition_ref = (
            definition_ref.strip() if isinstance(definition_ref, str) else None
        )

        if normalized_profile_id:
            if not is_react_profile_allowed(
                normalized_profile_id,
                self.agent_manager.config.ai.react_profile_allowlist,
            ):
                raise InvalidClassPathError(
                    f"ReAct profile '{normalized_profile_id}' is not allowed by current configuration."
                )
            try:
                get_react_profile(normalized_profile_id)
            except ValueError as exc:
                raise InvalidClassPathError(str(exc)) from exc

        agent_id = str(uuid4())

        if normalized_definition_ref:
            # Choice 1: fixed-behaviour v2 agent addressed by stable ref
            try:
                resolved = resolve_agent_reference(
                    class_path=None,
                    definition_ref=normalized_definition_ref,
                )
            except Exception as exc:
                raise InvalidClassPathError(str(exc)) from exc

            if not isinstance(resolved, ResolvedV2AgentClass):
                raise InvalidClassPathError(
                    f"definition_ref '{normalized_definition_ref}' does not resolve to a v2 definition."
                )

            if (
                normalized_profile_id
                and resolved.definition_ref != BASIC_REACT_DEFINITION_REF
            ):
                raise InvalidClassPathError(
                    "profile_id is only supported for v2.react.basic."
                )

            base_definition = instantiate_definition_class(resolved.cls)
            effective_definition = (
                apply_react_profile_to_definition(
                    base_definition, normalized_profile_id
                )
                if normalized_profile_id
                else base_definition
            )
            default_definition_ref = resolved.definition_ref
        else:
            # Choice 2: configurable BasicReAct agent (with optional starting profile)
            base_definition = instantiate_definition_class(BasicReActDefinition)
            effective_definition = apply_react_profile_to_definition(
                base_definition, normalized_profile_id
            )
            default_definition_ref = BASIC_REACT_DEFINITION_REF

        base_settings = definition_to_agent_settings(
            base_definition,
            class_path=None,
            definition_ref=default_definition_ref,
            enabled=True,
        )
        default_settings = apply_profile_defaults_to_settings(
            definition=effective_definition,
            settings=base_settings,
        )
        default_tuning = default_settings.tuning or definition_to_agent_tuning(
            effective_definition
        )

        agent_settings = Agent(
            id=agent_id,
            name=name,
            team_id=team_id,
            class_path=None,
            definition_ref=default_definition_ref,
            enabled=True,
            tuning=default_tuning,
            chat_options=default_settings.chat_options,
            mcp_servers=[],
        )
        await self.agent_manager.create_dynamic_agent(agent_settings, default_tuning)

        # Create ReBAC ownership: team owns the agent, or user owns the agent (personal agent)
        if team_id:
            await self.rebac.add_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=team_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.AGENT, id=agent_id),
                )
            )
        else:
            await self.rebac.add_user_relation(
                user,
                RelationType.OWNER,
                resource_type=Resource.AGENT,
                resource_id=agent_id,
            )

        return agent_settings

    async def create_v1_agent(
        self,
        user: KeycloakUser,
        name: str,
        *,
        team_id: Optional[str] = None,
        class_path: str,
    ) -> AgentSettings:
        """
        Create a v1 (AgentFlow) agent by explicit class path.

        Admin-only: requires CAN_EDIT_AGENT_CLASS_PATH permission.
        The class must be a subclass of AgentFlow declared in the static catalog.
        """
        await self.rebac.check_user_permission_or_raise(
            user,
            OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH,
            ORGANIZATION_ID,
        )
        if team_id:
            await self.rebac.check_user_team_permission_or_raise(
                user=user,
                permission=TeamPermission.CAN_UPDATE_AGENTS,
                team_id=team_id,
            )

        try:
            resolved = resolve_agent_class(class_path)
        except Exception as exc:
            raise InvalidClassPathError(str(exc)) from exc

        if not isinstance(resolved, ResolvedFlowAgentClass):
            raise InvalidClassPathError(
                f"'{class_path}' is a v2 definition — use POST /agents/v2/create with a definition_ref instead."
            )

        agent_id = str(uuid4())
        agent_settings = Agent(
            id=agent_id,
            name=name,
            team_id=team_id,
            class_path=class_path,
            definition_ref=None,
            enabled=True,
            tuning=resolved.cls.tuning,
            mcp_servers=[],
        )
        await self.agent_manager.create_dynamic_agent(
            agent_settings, resolved.cls.tuning
        )

        if team_id:
            await self.rebac.add_relation(
                Relation(
                    subject=RebacReference(type=Resource.TEAM, id=team_id),
                    relation=RelationType.OWNER,
                    resource=RebacReference(type=Resource.AGENT, id=agent_id),
                )
            )
        else:
            await self.rebac.add_user_relation(
                user,
                RelationType.OWNER,
                resource_type=Resource.AGENT,
                resource_id=agent_id,
            )

        return agent_settings

    async def update_agent(self, user: KeycloakUser, agent_settings: AgentSettings):
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.UPDATE, agent_settings.id
        )
        if agent_settings.class_path and agent_settings.definition_ref:
            raise InvalidClassPathError(
                "Provide either class_path or definition_ref, not both."
            )

        if agent_settings.definition_ref:
            try:
                resolved = resolve_agent_reference(
                    class_path=None,
                    definition_ref=agent_settings.definition_ref,
                )
            except Exception as exc:
                raise InvalidClassPathError(str(exc)) from exc
            agent_settings = agent_settings.model_copy(
                update={
                    "class_path": None,
                    "definition_ref": resolved.definition_ref,
                }
            )

        current = await self.agent_manager.get_agent_settings(agent_settings.id)
        if current is not None:
            current = await self._enrich_settings_with_authoritative_team_id(current)
        if current is not None and current.team_id != agent_settings.team_id:
            raise ImmutableTeamIdError(
                f"team_id is immutable for agent '{agent_settings.id}'"
            )

        # Check class_path change
        if agent_settings.class_path is not None:
            if current and current.class_path != agent_settings.class_path:
                await self.rebac.check_user_permission_or_raise(
                    user,
                    OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH,
                    ORGANIZATION_ID,
                )
                _validate_class_path(agent_settings.class_path)

        await self.agent_manager.update_agent(new_settings=agent_settings)

    def get_class_path_tuning(
        self,
        class_path: str | None,
        *,
        definition_ref: str | None = None,
    ) -> AgentTuning:
        """Return the default tuning for a given class_path or definition_ref.

        Resolution order:
        1. definition_ref  → resolve v2 definition, return its tuning fields
        2. class_path      → resolve class, return its tuning (v1) or definition fields (v2)
        3. neither         → return blank BasicReAct defaults
        """
        if definition_ref:
            logger.debug(
                "[AGENTS][TUNING] resolving tuning for definition_ref=%r",
                definition_ref,
            )
            try:
                resolved = resolve_agent_reference(
                    class_path=None, definition_ref=definition_ref
                )
            except Exception as exc:
                logger.warning(
                    "[AGENTS][TUNING] definition_ref=%r could not be resolved: %s",
                    definition_ref,
                    exc,
                )
                raise InvalidClassPathError(str(exc)) from exc
            if not isinstance(resolved, ResolvedV2AgentClass):
                raise InvalidClassPathError(
                    f"definition_ref '{definition_ref}' does not resolve to a v2 definition."
                )
            definition = instantiate_definition_class(resolved.cls)
            tuning = definition_to_agent_tuning(definition)
            logger.debug(
                "[AGENTS][TUNING] definition_ref=%r → class=%s fields=%d",
                definition_ref,
                resolved.cls.__name__,
                len(tuning.fields or []),
            )
            return tuning

        if not class_path:
            logger.debug(
                "[AGENTS][TUNING] no class_path/definition_ref → returning BasicReAct defaults"
            )
            definition = instantiate_definition_class(BasicReActDefinition)
            return definition_to_agent_tuning(definition)

        logger.debug("[AGENTS][TUNING] resolving tuning for class_path=%r", class_path)
        resolved = resolve_agent_class(class_path)
        if isinstance(resolved, ResolvedFlowAgentClass):
            logger.debug(
                "[AGENTS][TUNING] class_path=%r → v1 flow agent fields=%d",
                class_path,
                len(resolved.cls.tuning.fields or []),
            )
            return resolved.cls.tuning

        definition = instantiate_definition_class(resolved.cls)
        tuning = definition_to_agent_tuning(definition)
        logger.debug(
            "[AGENTS][TUNING] class_path=%r → v2 definition fields=%d",
            class_path,
            len(tuning.fields or []),
        )
        return tuning

    async def delete_agent(self, user: KeycloakUser, agent_id: str):
        await self.rebac.check_user_permission_or_raise(
            user, AgentPermission.DELETE, agent_id
        )

        await self.agent_manager.delete_agent(agent_id)

    @authorize(action=Action.UPDATE, resource=Resource.AGENTS)
    async def restore_static_agents(
        self, user: KeycloakUser, force_overwrite: bool = True
    ) -> None:
        await self.agent_manager.restore_static_agents(force_overwrite=force_overwrite)

    async def _resolve_authorized_agent_ids(
        self,
        user: KeycloakUser,
        owner_filter: Optional[OwnerFilter],
        team_id: Optional[str],
    ) -> set[str] | None:
        """Return the set of agent IDs the user is allowed to see, or None if ReBAC is disabled.

        When an owner_filter is provided, the result is intersected with the
        owner-filtered agent IDs so only readable agents matching the filter are returned.
        """
        readable_coro = self.rebac.lookup_user_resources(user, AgentPermission.READ)

        if owner_filter is None:
            readable_refs = await readable_coro
            if isinstance(readable_refs, RebacDisabledResult):
                return None
            return {ref.id for ref in readable_refs}

        # Determine the subject reference based on the filter
        if owner_filter == OwnerFilter.TEAM:
            if not team_id:
                raise MissingTeamIdError(
                    "team_id is required when owner_filter is 'team'"
                )
            subject_ref = RebacReference(type=Resource.TEAM, id=team_id)
        else:
            subject_ref = RebacReference(type=Resource.USER, id=user.uid)

        # Run lookups in parallel: security baseline + owner-filtered lookup
        readable_refs, owned = await asyncio.gather(
            readable_coro,
            self.rebac.lookup_resources(
                subject_ref, AgentPermission.OWNER, Resource.AGENT
            ),
        )
        if isinstance(readable_refs, RebacDisabledResult) or isinstance(
            owned, RebacDisabledResult
        ):
            return None

        readable_ids = {ref.id for ref in readable_refs}
        filtered_ids = {ref.id for ref in owned}
        return readable_ids & filtered_ids
