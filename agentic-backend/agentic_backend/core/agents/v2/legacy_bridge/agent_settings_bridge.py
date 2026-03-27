# Copyright Thales 2026
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
Bridge between pure v2 definitions and legacy `AgentSettings`.

Why this module exists:
- the runtime and authoring layers now use typed v2 `AgentDefinition` classes
- the store, UI, and part of the API stack still persist and exchange
  `AgentSettings`
- this module isolates that migration tax so pure v2 runtime code does not need
  to know the legacy settings model

How to use it:
- use `definition_to_agent_settings(...)` when a v2 definition must be exposed
  through the legacy store/UI shape
- use `build_definition_from_settings(...)` when loading a persisted agent back
  into a typed v2 definition
- use `apply_profile_defaults_to_settings(...)` when callers need the effective
  settings view after profile defaults and user overrides are merged

Example:
- `definition = build_definition_from_settings(definition_class=MyDefinition, settings=settings)`
- `effective = apply_profile_defaults_to_settings(definition=definition, settings=settings)`
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from agentic_backend.common.structures import Agent, AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, MCPServerRef

from ..contracts.models import (
    AgentDefinition,
    GraphAgentDefinition,
    ReActAgentDefinition,
    ToolRefRequirement,
)
from .react_profile_bridge import (
    PROFILE_MANAGED_MODEL_FIELDS,
    ReActProfile,
    get_react_profile,
    list_react_profiles,
)

DefinitionT = TypeVar("DefinitionT", bound=AgentDefinition)
logger = logging.getLogger(__name__)


def definition_to_agent_tuning(definition: AgentDefinition) -> AgentTuning:
    """
    Creates an `AgentTuning` object from an `AgentDefinition`.

    This extracts the role, description, tags, fields, and default MCP servers.
    """
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        tags=list(definition.tags),
        fields=[field.model_copy(deep=True) for field in definition.fields],
    )
    tuning.mcp_servers = [
        server.model_copy(deep=True)
        for server in _default_mcp_servers_for_definition(definition)
    ]
    return tuning


def definition_to_agent_settings(
    definition: AgentDefinition,
    *,
    class_path: str | None = None,
    definition_ref: str | None = None,
    enabled: bool = True,
) -> AgentSettings:
    """
    Creates a legacy `AgentSettings` object from a v2 `AgentDefinition`.

    Use this to make a v2 agent compatible with the agent store and UI, which
    still operate on the `AgentSettings` model.
    """
    tuning = definition_to_agent_tuning(definition)
    chat_options = _chat_options_from_definition(definition)
    return Agent(
        id=definition.agent_id,
        name=definition.role,
        class_path=class_path,
        definition_ref=definition_ref,
        enabled=enabled,
        tuning=tuning,
        chat_options=chat_options,
    )


def build_definition_from_settings(
    *,
    definition_class: type[DefinitionT],
    settings: AgentSettings,
) -> DefinitionT:
    """
    Hydrate a v2 definition instance from persisted `AgentSettings`.

    This function reconstructs a `Definition` object by applying the stored
    `tuning` values from `AgentSettings` over the base definition's class defaults.
    It also handles the application of ReAct profiles if one is selected.
    """
    base_definition = instantiate_definition_class(definition_class)
    logger.debug(
        "[V2][HYDRATE] base_definition class=%s agent_id=%s declared_tool_refs=%r toolset_key=%r",
        definition_class.__name__,
        base_definition.agent_id,
        [r.tool_ref for r in getattr(base_definition, "declared_tool_refs", ())],
        getattr(base_definition, "toolset_key", None),
    )

    tuning = settings.tuning or definition_to_agent_tuning(base_definition)
    field_defaults = _field_defaults_by_key(tuning.fields)
    profiled_definition = _apply_profile_to_definition(
        base_definition,
        field_defaults=field_defaults,
    )
    logger.debug(
        "[V2][HYDRATE] after_profile class=%s declared_tool_refs=%r",
        definition_class.__name__,
        [r.tool_ref for r in getattr(profiled_definition, "declared_tool_refs", ())],
    )

    updates: dict[str, Any] = {
        "agent_id": settings.id,
        "role": _profiled_identity_value(
            current_value=tuning.role,
            base_value=base_definition.role,
            profile_value=profiled_definition.role,
        ),
        "description": _profiled_identity_value(
            current_value=tuning.description,
            base_value=base_definition.description,
            profile_value=profiled_definition.description,
        ),
        "tags": tuple(
            _profiled_identity_value(
                current_value=tuple(tuning.tags),
                base_value=base_definition.tags,
                profile_value=profiled_definition.tags,
            )
        ),
        "fields": tuple(field.model_copy(deep=True) for field in tuning.fields),
    }
    if _supports_declared_tool_refs(profiled_definition):
        updates["declared_tool_refs"] = tuple(
            ref.model_copy(deep=True)
            for ref in _declared_tool_refs_for_definition(profiled_definition)
        )

    model_field_names = set(base_definition.__class__.model_fields.keys())
    for field_name, value in field_defaults.items():
        if field_name in model_field_names:
            if field_name in PROFILE_MANAGED_MODEL_FIELDS:
                base_value = getattr(base_definition, field_name, None)
                profile_value = getattr(profiled_definition, field_name, None)
                if field_name == "react_profile_id" and not _is_known_react_profile_id(
                    value
                ):
                    updates[field_name] = profile_value
                    continue
                updates[field_name] = _profiled_field_value(
                    current_value=value,
                    base_value=base_value,
                    profile_value=profile_value,
                )
            else:
                updates[field_name] = value

    result = base_definition.model_copy(update=updates)
    logger.debug(
        "[V2][HYDRATE] final class=%s agent_id=%s declared_tool_refs=%r toolset_key=%r",
        definition_class.__name__,
        result.agent_id,
        [r.tool_ref for r in getattr(result, "declared_tool_refs", ())],
        getattr(result, "toolset_key", None),
    )
    return result


def apply_profile_defaults_to_settings(
    *,
    definition: AgentDefinition,
    settings: AgentSettings,
) -> AgentSettings:
    """
    Build the effective `AgentSettings` view for a v2 definition.

    This is what the UI and runtime adapters should consume. It computes the final
    state of an agent's settings after applying any selected profile defaults
    (e.g., for ReAct agents) and merging them with user-persisted overrides.
    The result is a single, coherent `AgentSettings` object.
    """

    base_definition = instantiate_definition_class(type(definition))
    current_tuning = settings.tuning or definition_to_agent_tuning(definition)
    effective_tuning = AgentTuning(
        role=_profiled_identity_value(
            current_value=current_tuning.role,
            base_value=base_definition.role,
            profile_value=definition.role,
        ),
        description=_profiled_identity_value(
            current_value=current_tuning.description,
            base_value=base_definition.description,
            profile_value=definition.description,
        ),
        tags=list(
            _profiled_identity_value(
                current_value=tuple(current_tuning.tags),
                base_value=base_definition.tags,
                profile_value=definition.tags,
            )
        ),
        fields=_merge_profiled_fields(
            current_fields=current_tuning.fields,
            base_definition=base_definition,
            effective_definition=definition,
        ),
        mcp_servers=_effective_mcp_servers(
            current_tuning=current_tuning,
            definition=definition,
        ),
    )

    current_chat_options = settings.chat_options
    default_chat_options = _chat_options_from_definition(definition)
    effective_chat_options = (
        default_chat_options
        if current_chat_options == AgentChatOptions()
        else current_chat_options
    )

    return settings.model_copy(
        update={
            "tuning": effective_tuning,
            "chat_options": effective_chat_options,
        }
    )


def instantiate_definition_class(definition_class: type[DefinitionT]) -> DefinitionT:
    """Create a default instance of a definition class.

    This uses `model_validate({})` to correctly initialize a Pydantic model
    from its class-level field defaults.
    """
    return definition_class.model_validate({})


def apply_react_profile_to_definition(
    definition: DefinitionT,
    profile_id: str | None,
) -> DefinitionT:
    """
    Apply a named ReAct profile to a definition instance.

    This returns a new definition instance with defaults (role, description,
    prompts, etc.) overridden by the selected profile. This is used during agent
    creation to provide a starting point.
    """
    if not isinstance(profile_id, str) or not profile_id.strip():
        return definition
    profiled_definition = _apply_profile_to_definition(
        definition,
        field_defaults={"react_profile_id": profile_id.strip()},
    )
    profiled_fields: list[FieldSpec] = []
    for field in definition.fields:
        key = field.key.strip()
        if (
            key in PROFILE_MANAGED_MODEL_FIELDS
            and key in profiled_definition.__class__.model_fields
        ):
            profiled_fields.append(
                field.model_copy(
                    update={"default": getattr(profiled_definition, key, None)}
                )
            )
        else:
            profiled_fields.append(field.model_copy(deep=True))
    return profiled_definition.model_copy(update={"fields": tuple(profiled_fields)})


def _field_defaults_by_key(
    fields: list[FieldSpec] | tuple[FieldSpec, ...],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in fields:
        key = field.key.strip()
        if not key or "." in key:
            continue
        values[key] = field.default
    return values


def _selected_react_profile(definition: AgentDefinition) -> ReActProfile | None:
    model_field_names = set(definition.__class__.model_fields.keys())
    if "react_profile_id" not in model_field_names:
        return None

    raw_profile_id = getattr(definition, "react_profile_id", None)
    if not isinstance(raw_profile_id, str) or not raw_profile_id.strip():
        return None
    return _resolve_react_profile(raw_profile_id)


def _apply_profile_to_definition(
    definition: DefinitionT,
    *,
    field_defaults: dict[str, Any],
) -> DefinitionT:
    """
    Apply a ReAct profile's defaults to a definition instance.

    Why this exists:
    - Generic agent families (e.g. `BasicReActDefinition`) get both their
      tools and system prompt from a profile; this function merges those
      defaults in.
    - Authored `ReActAgent` subclasses (those with `tools = (...)` and a
      class-level `system_prompt_template`) declare their own tools and
      prompts at definition time.  The profile must not overwrite them.

    How to distinguish authored vs generic:
    - `toolset_key` is set by `ReActAgent.__pydantic_init_subclass__` when
      `tools = (...)` is non-empty; it is empty-string for all generic families.
    - `declared_tool_refs`: use the class-defined refs when non-empty; fall back
      to the profile refs only for generic families.
    - `system_prompt_template`: preserved as-is for authored agents
      (`has_authored_tools=True`); replaced by the profile prompt for generic
      families where profile-switching must work correctly.

    How to use:
    - call from `build_definition_from_settings` after loading base defaults
    - do not call directly for new code; prefer `build_definition_from_settings`

    Example:
    - `profiled = _apply_profile_to_definition(definition, field_defaults={})`
    """
    profile_id = field_defaults.get("react_profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        profile = _selected_react_profile(definition)
        if profile is None:
            # Only apply a fallback profile to definitions that actually support
            # profiles (i.e. have a react_profile_id field).  Custom agents like
            # PptFillerReActV2Definition define their own system prompt and tools;
            # overwriting them with a generic fallback profile is wrong.
            if "react_profile_id" not in definition.__class__.model_fields:
                return definition
            profile = _fallback_react_profile()
            if profile is None:
                return definition
    else:
        profile = _resolve_react_profile(profile_id)
        if profile is None:
            profile = _selected_react_profile(definition)
            if profile is None:
                profile = _fallback_react_profile()
                if profile is None:
                    return definition

    # Authored ReActAgent subclasses own their tool refs AND their system prompt via
    # class-level declarations (`tools = (...)` and `system_prompt_template = ui_field(...)`).
    # Profiles are designed for generic families like BasicReActDefinition where both come
    # from the profile. We distinguish authored agents by the presence of a non-empty
    # `toolset_key` (set automatically by ReActAgent.__pydantic_init_subclass__).
    #
    # - declared_tool_refs: use the class-defined refs if non-empty, else fall back to profile.
    # - system_prompt_template: preserve the class-defined prompt for authored agents;
    #   for generic families (no toolset_key), always use the profile prompt because
    #   their system_prompt_template is set from the fallback profile and profile switching
    #   must work correctly.
    has_authored_tools = bool(getattr(definition, "toolset_key", "").strip())
    existing_tool_refs = getattr(definition, "declared_tool_refs", ())
    effective_tool_refs = (
        existing_tool_refs if existing_tool_refs else profile.declared_tool_refs
    )
    existing_system_prompt = getattr(definition, "system_prompt_template", "")
    effective_system_prompt = (
        existing_system_prompt
        if (has_authored_tools and existing_system_prompt)
        else profile.system_prompt_template
    )
    logger.debug(
        "[V2][PROFILE] applying profile=%s to class=%s has_authored_tools=%s "
        "profile_tool_refs=%r effective_tool_refs=%r "
        "using_authored_prompt=%s",
        profile.profile_id,
        definition.__class__.__name__,
        has_authored_tools,
        [r.tool_ref for r in profile.declared_tool_refs],
        [r.tool_ref for r in effective_tool_refs],
        has_authored_tools and bool(existing_system_prompt),
    )
    updates: dict[str, Any] = {
        "react_profile_id": profile.profile_id,
        "role": profile.role,
        "description": profile.agent_description,
        "tags": profile.tags,
        "system_prompt_template": effective_system_prompt,
        "enable_tool_approval": profile.enable_tool_approval,
        "approval_required_tools": profile.approval_required_tools,
        "guardrails": profile.guardrails,
        "declared_tool_refs": effective_tool_refs,
    }
    supported_updates = {
        key: value
        for key, value in updates.items()
        if key in definition.__class__.model_fields
    }
    return definition.model_copy(update=supported_updates)


def _resolve_react_profile(profile_id: str) -> ReActProfile | None:
    try:
        return get_react_profile(profile_id)
    except ValueError:
        logger.warning(
            "[V2_CATALOG] Unknown ReAct profile '%s'. Falling back to a known profile.",
            profile_id,
        )
        return None


def _is_known_react_profile_id(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        get_react_profile(value.strip())
    except ValueError:
        return False
    return True


def _fallback_react_profile() -> ReActProfile | None:
    profiles = list_react_profiles()
    if not profiles:
        return None
    for profile in profiles:
        if profile.profile_id == "base_assistant":
            return profile
    return profiles[0]


def _profiled_identity_value(
    *,
    current_value: Any,
    base_value: Any,
    profile_value: Any,
) -> Any:
    if _equivalent_profile_values(current_value, base_value):
        return profile_value
    return current_value


def _profiled_field_value(
    *,
    current_value: Any,
    base_value: Any,
    profile_value: Any,
) -> Any:
    if _equivalent_profile_values(current_value, base_value):
        return profile_value
    return current_value


def _equivalent_profile_values(left: Any, right: Any) -> bool:
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return tuple(left) == tuple(right)
    return left == right


def _merge_profiled_fields(
    *,
    current_fields: list[FieldSpec] | tuple[FieldSpec, ...],
    base_definition: AgentDefinition,
    effective_definition: AgentDefinition,
) -> list[FieldSpec]:
    base_field_defaults = {
        field.key: field.default
        for field in base_definition.fields
        if field.key and "." not in field.key
    }
    effective_field_specs = {
        field.key: field
        for field in effective_definition.fields
        if field.key and "." not in field.key
    }

    merged_fields: list[FieldSpec] = []
    for field in current_fields:
        key = field.key.strip()
        if key not in effective_field_specs:
            merged_fields.append(field.model_copy(deep=True))
            continue

        effective_spec = effective_field_specs[key].model_copy(deep=True)
        current_default = field.default
        base_default = base_field_defaults.get(key)
        if key in PROFILE_MANAGED_MODEL_FIELDS and not _equivalent_profile_values(
            current_default, base_default
        ):
            effective_spec = effective_spec.model_copy(
                update={"default": current_default}
            )
        merged_fields.append(effective_spec)

    seen_keys = {field.key for field in merged_fields}
    for key, spec in effective_field_specs.items():
        if key not in seen_keys:
            merged_fields.append(spec.model_copy(deep=True))

    return merged_fields


def _effective_mcp_servers(
    *,
    current_tuning: AgentTuning,
    definition: AgentDefinition,
) -> list[MCPServerRef]:
    """
    Resolve the MCP servers that should be attached for one effective agent.

    Why this exists:
    - stored tuning may already carry user-selected MCP servers
    - when no explicit tuning exists, the settings bridge should fall back to the
      defaults declared by the agent family

    How to use:
    - call when translating one v2 definition and its current tuning into legacy
      `AgentSettings`

    Example:
    - `servers = _effective_mcp_servers(current_tuning=tuning, definition=definition)`
    """

    if current_tuning.mcp_servers:
        return [server.model_copy(deep=True) for server in current_tuning.mcp_servers]
    return [
        server.model_copy(deep=True)
        for server in _default_mcp_servers_for_definition(definition)
    ]


def _default_mcp_servers_for_definition(
    definition: AgentDefinition,
) -> tuple[MCPServerRef, ...]:
    """
    Return the default MCP servers declared by one tool-aware v2 agent.

    Why this exists:
    - only executable agent families should own MCP defaults in the authoring
      contract
    - catalog code still needs one shared way to read those defaults when building
      legacy settings

    How to use:
    - call when the settings bridge needs family-owned MCP defaults
    - prefer this helper over direct field access on `AgentDefinition`

    Example:
    - `servers = _default_mcp_servers_for_definition(definition)`
    """

    profile = _selected_react_profile(definition)
    if profile is not None and profile.mcp_servers:
        return profile.mcp_servers
    if isinstance(definition, (ReActAgentDefinition, GraphAgentDefinition)):
        return definition.default_mcp_servers
    return ()


def _supports_declared_tool_refs(definition: AgentDefinition) -> bool:
    """
    Tell whether one v2 agent family exposes declared Fred tool refs.

    Why this exists:
    - only executable tool-aware families should carry `declared_tool_refs`
    - catalog code should not assume proxy-style agents expose the same authoring
      surface

    How to use:
    - call before reading or updating `declared_tool_refs` on a definition

    Example:
    - `if _supports_declared_tool_refs(definition): ...`
    """

    return isinstance(definition, (ReActAgentDefinition, GraphAgentDefinition))


def _declared_tool_refs_for_definition(
    definition: AgentDefinition,
) -> tuple[ToolRefRequirement, ...]:
    """
    Return the declared Fred tool refs for one tool-aware v2 agent definition.

    Why this exists:
    - catalog code needs one small shared way to read declared tool refs without
      broadening the base `AgentDefinition` contract again
    - this keeps the generic settings bridge aligned with the narrower authoring model

    How to use:
    - call only after `_supports_declared_tool_refs(definition)` returned `True`

    Example:
    - `refs = _declared_tool_refs_for_definition(definition)`
    """

    if isinstance(definition, (ReActAgentDefinition, GraphAgentDefinition)):
        return definition.declared_tool_refs
    return ()


def _chat_options_from_fields(
    fields: tuple[FieldSpec, ...] | list[FieldSpec],
) -> AgentChatOptions:
    overrides: dict[str, bool] = {}
    for field in fields:
        if not field.key.startswith("chat_options."):
            continue
        option_name = field.key.split(".", 1)[1]
        if isinstance(field.default, bool):
            overrides[option_name] = field.default
    return AgentChatOptions(**overrides)


def _chat_options_from_definition(definition: AgentDefinition) -> AgentChatOptions:
    profile = _selected_react_profile(definition)
    if profile is None:
        return _chat_options_from_fields(definition.fields)
    return profile.chat_options.model_copy(deep=True)
