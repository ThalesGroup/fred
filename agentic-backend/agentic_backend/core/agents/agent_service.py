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
from typing import List, Literal, Optional, Union
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
    AgentChatOptions,
    AgentSettings,
)
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_class,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.v2.catalog import (
    apply_profile_defaults_to_settings,
    apply_react_profile_to_definition,
    build_definition_from_settings,
    definition_to_agent_settings,
    definition_to_agent_tuning,
    instantiate_definition_class,
)
from agentic_backend.core.agents.v2.react_profiles import (
    get_react_profile,
    is_react_profile_allowed,
)

logger = logging.getLogger(__name__)

LEGACY_V1_REACT_CLASS_PATH = (
    "agentic_backend.core.agents.basic_react_agent.BasicReActAgent"
)


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

        if resolved.implementation_kind == AgentImplementationKind.FLOW:
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

    async def create_agent(
        self,
        user: KeycloakUser,
        name: str,
        *,
        agent_type: Literal["basic"] = "basic",
        team_id: Optional[str] = None,
        class_path: Optional[str] = None,
        definition_ref: Optional[str] = None,
        profile_id: Optional[str] = None,
    ):
        """
        Builds, registers, and stores the MCP agent, including updating app context and saving to DuckDB.
        """
        # If team_id is provided, check user has permission to manage team agents
        if team_id:
            await self.rebac.check_user_team_permission_or_raise(
                user=user,
                permission=TeamPermission.CAN_UPDATE_AGENTS,
                team_id=team_id,
            )

        # If class_path/definition_ref is provided, validate and resolve target class
        resolved_agent_cls: type[object] | None = None
        resolved_definition_ref: str | None = None
        resolved_class_path: str | None = None
        basic_react_class_path = _class_path(BasicReActDefinition)
        basic_react_definition_ref = BASIC_REACT_DEFINITION_REF
        normalized_profile_id = profile_id.strip() if profile_id else None
        normalized_definition_ref = (
            definition_ref.strip() if isinstance(definition_ref, str) else None
        )
        normalized_class_path = (
            class_path.strip() if isinstance(class_path, str) else None
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
        if normalized_class_path and normalized_definition_ref:
            raise InvalidClassPathError(
                "Provide either class_path or definition_ref, not both."
            )

        if normalized_definition_ref:
            try:
                resolved = resolve_agent_reference(
                    class_path=None,
                    definition_ref=normalized_definition_ref,
                )
            except Exception as exc:
                raise InvalidClassPathError(str(exc)) from exc
            resolved_agent_cls = resolved.cls
            resolved_definition_ref = resolved.definition_ref
            resolved_class_path = resolved.class_path
            if (
                normalized_profile_id
                and resolved_definition_ref != basic_react_definition_ref
            ):
                raise InvalidClassPathError(
                    "profile_id is only supported for v2.react.basic."
                )
        elif normalized_class_path:
            is_safe_builtin = normalized_class_path in {
                basic_react_class_path,
                LEGACY_V1_REACT_CLASS_PATH,
            }
            if not is_safe_builtin:
                await self.rebac.check_user_permission_or_raise(
                    user,
                    OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH,
                    ORGANIZATION_ID,
                )
            resolved_agent_cls = _validate_class_path(normalized_class_path)
            resolved_class_path = normalized_class_path
            if (
                normalized_profile_id
                and normalized_class_path != basic_react_class_path
            ):
                raise InvalidClassPathError(
                    "profile_id is only supported for BasicReActDefinition"
                )

        agent_id = str(uuid4())

        if resolved_agent_cls is None:
            base_definition = instantiate_definition_class(BasicReActDefinition)
            effective_definition = apply_react_profile_to_definition(
                base_definition,
                normalized_profile_id,
            )
            base_settings = definition_to_agent_settings(
                base_definition,
                class_path=None,
                definition_ref=basic_react_definition_ref,
                enabled=True,
            )
            default_settings = apply_profile_defaults_to_settings(
                definition=effective_definition,
                settings=base_settings,
            )
            default_tuning = default_settings.tuning or AgentTuning(
                role=effective_definition.role,
                description=effective_definition.description,
            )
            default_chat_options = default_settings.chat_options
            default_class_path = None
            default_definition_ref = basic_react_definition_ref
        else:
            assert resolved_class_path is not None
            resolved = resolve_agent_class(resolved_class_path)
            if resolved.implementation_kind == AgentImplementationKind.FLOW:
                default_tuning = resolved.cls.tuning
                default_chat_options = AgentChatOptions()
                default_class_path = resolved_class_path
                default_definition_ref = None
            else:
                base_definition = instantiate_definition_class(resolved.cls)
                effective_definition = (
                    apply_react_profile_to_definition(
                        base_definition,
                        normalized_profile_id,
                    )
                    if resolved_class_path == basic_react_class_path
                    else base_definition
                )
                base_settings = definition_to_agent_settings(
                    base_definition,
                    class_path=None if resolved_definition_ref else resolved_class_path,
                    definition_ref=resolved_definition_ref,
                    enabled=True,
                )
                default_settings = apply_profile_defaults_to_settings(
                    definition=effective_definition,
                    settings=base_settings,
                )
                default_tuning = default_settings.tuning or definition_to_agent_tuning(
                    effective_definition
                )
                default_chat_options = default_settings.chat_options
                default_class_path = (
                    None if resolved_definition_ref else resolved_class_path
                )
                default_definition_ref = resolved_definition_ref
        agent_settings = Agent(
            id=agent_id,
            name=name,
            team_id=team_id,
            class_path=default_class_path,
            definition_ref=default_definition_ref,
            enabled=True,
            tuning=default_tuning,
            chat_options=default_chat_options,
            mcp_servers=[],  # Empty list by default; to be configured later
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
