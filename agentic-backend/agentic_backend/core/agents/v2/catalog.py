"""
Compatibility helpers between v2 definitions and Fred's existing catalog/store.

Why this file exists:
- Fred still persists and exposes `AgentSettings`, while the new authoring model
  is `AgentDefinition`.
- The UI and the store still speak in terms of settings, names, MCP defaults,
  and editable fields.
- The clean v2 move is therefore not to duplicate that world, but to derive it
  from a pure definition in one place.
- That keeps the business meaning stable: a definition says what the agent is,
  and this bridge says how Fred should present and persist it today.
"""

from __future__ import annotations

import os
from typing import Any, TypeVar

from fred_core import KeycloakUser

from agentic_backend.common.structures import Agent, AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, MCPServerRef
from agentic_backend.core.agents.runtime_context import RuntimeContext

from .context import BoundRuntimeContext, PortableContext, PortableEnvironment
from .models import AgentDefinition
from .react_profiles import (
    PROFILE_MANAGED_MODEL_FIELDS,
    ReActProfile,
    get_react_profile,
)

DefinitionT = TypeVar("DefinitionT", bound=AgentDefinition)


def definition_to_agent_tuning(definition: AgentDefinition) -> AgentTuning:
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
    class_path: str,
    enabled: bool = True,
) -> AgentSettings:
    tuning = definition_to_agent_tuning(definition)
    chat_options = _chat_options_from_definition(definition)
    return Agent(
        id=definition.agent_id,
        name=definition.role,
        class_path=class_path,
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
    Hydrate a v2 definition instance from persisted settings.

    The current Fred catalog persists editable values as `FieldSpec.default`.
    For v2 definitions, the convention is:
    - `FieldSpec.key` matches a model field name for editable definition values
    - `role`, `description`, `tags`, and `fields` are derived from the current
      persisted tuning view
    """
    base_definition = instantiate_definition_class(definition_class)
    tuning = settings.tuning or definition_to_agent_tuning(base_definition)
    field_defaults = _field_defaults_by_key(tuning.fields)
    profiled_definition = _apply_profile_to_definition(
        base_definition,
        field_defaults=field_defaults,
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
        "tool_requirements": profiled_definition.tool_requirements,
    }

    model_field_names = set(base_definition.__class__.model_fields.keys())
    for field_name, value in field_defaults.items():
        if field_name in model_field_names:
            if field_name in PROFILE_MANAGED_MODEL_FIELDS:
                base_value = getattr(base_definition, field_name, None)
                profile_value = getattr(profiled_definition, field_name, None)
                updates[field_name] = _profiled_field_value(
                    current_value=value,
                    base_value=base_value,
                    profile_value=profile_value,
                )
            else:
                updates[field_name] = value

    return base_definition.model_copy(update=updates)


def apply_profile_defaults_to_settings(
    *,
    definition: AgentDefinition,
    settings: AgentSettings,
) -> AgentSettings:
    """
    Build the effective settings view for a profiled v2 definition.

    Why this helper exists:
    - runtime adapters and the UI still consume `AgentSettings`
    - some defaults that matter to the business experience, such as MCP
      services or chat affordances, live outside simple model fields
    - the UI should receive one coherent view of "what this agent effectively
      is" instead of trying to rebuild profile logic on the client
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
    """
    Build a pure v2 definition instance from its class defaults.

    We intentionally instantiate through Pydantic validation rather than a raw
    zero-arg constructor call because the base `AgentDefinition` type has
    required fields while concrete subclasses provide defaults.
    """

    return definition_class.model_validate({})


def apply_react_profile_to_definition(
    definition: DefinitionT,
    profile_id: str | None,
) -> DefinitionT:
    """
    Apply one backend-defined ReAct profile to a definition instance.

    Why this helper exists:
    - creation flows should be able to choose a starting profile immediately
    - callers should not need to know about the internal field-default plumbing
    - non-profiled definitions should pass through unchanged
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


def build_bound_runtime_context(
    *,
    user: KeycloakUser,
    runtime_context: RuntimeContext,
    agent_id: str,
    agent_name: str | None = None,
    team_id: str | None = None,
) -> BoundRuntimeContext:
    """
    Build the portable execution context used by v2 runtimes.

    This is the point where a Fred session, user, and agent id are turned into
    the smaller context envelope that tools, tracing, and future SDK-aligned
    capabilities can share consistently.
    """

    tenant = runtime_context.user_id or user.uid or "fred"
    return BoundRuntimeContext(
        runtime_context=runtime_context.model_copy(deep=True),
        portable_context=PortableContext(
            request_id=f"req:{runtime_context.session_id or agent_id}",
            correlation_id=f"corr:{runtime_context.session_id or agent_id}",
            actor=f"user:{user.uid}",
            tenant=tenant,
            environment=_portable_environment_from_env(),
            trace_id=None,
            client_app="fred-ui",
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=runtime_context.session_id,
            user_id=user.uid or runtime_context.user_id,
            user_name=user.username,
            team_id=team_id,
            baggage={},
        ),
    )


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
    return get_react_profile(raw_profile_id)


def _apply_profile_to_definition(
    definition: DefinitionT,
    *,
    field_defaults: dict[str, Any],
) -> DefinitionT:
    profile_id = field_defaults.get("react_profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        profile = _selected_react_profile(definition)
        if profile is None:
            return definition
    else:
        profile = get_react_profile(profile_id)

    updates: dict[str, Any] = {
        "react_profile_id": profile.profile_id,
        "role": profile.role,
        "description": profile.agent_description,
        "tags": profile.tags,
        "system_prompt_template": profile.system_prompt_template,
        "enable_tool_approval": profile.enable_tool_approval,
        "approval_required_tools": profile.approval_required_tools,
        "guardrails": profile.guardrails,
        "tool_requirements": profile.tool_requirements,
    }
    supported_updates = {
        key: value
        for key, value in updates.items()
        if key in definition.__class__.model_fields
    }
    return definition.model_copy(update=supported_updates)


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
    if current_tuning.mcp_servers:
        return [server.model_copy(deep=True) for server in current_tuning.mcp_servers]
    return [
        server.model_copy(deep=True)
        for server in _default_mcp_servers_for_definition(definition)
    ]


def _default_mcp_servers_for_definition(
    definition: AgentDefinition,
) -> tuple[MCPServerRef, ...]:
    profile = _selected_react_profile(definition)
    if profile is not None and profile.mcp_servers:
        return profile.mcp_servers
    return definition.default_mcp_servers


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


def _portable_environment_from_env() -> PortableEnvironment:
    raw = os.getenv("FRED_ENVIRONMENT", "dev").strip().lower()
    if raw == PortableEnvironment.PROD.value:
        return PortableEnvironment.PROD
    if raw == PortableEnvironment.STAGING.value:
        return PortableEnvironment.STAGING
    return PortableEnvironment.DEV
