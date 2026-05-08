from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Literal, Sequence, cast
from uuid import uuid4

import httpx
from fred_core import KeycloakUser, RBACProvider
from fred_core.common import PERSONAL_TEAM_ID, TeamId
from fred_sdk.contracts.execution import ExecutionGrant, ExecutionGrantAction
from fred_sdk.contracts.prompt_utils import validate_prompt_template

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.config.models import (
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
)
from control_plane_backend.prompts.store import (
    PromptAlreadyExistsError,
    PromptRecord,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    CreatePromptRequest,
    CreateSessionRequest,
    EffectiveChatOptions,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PermissionSummary,
    PromptDetail,
    PromptSummary,
    SessionListItem,
    UpdateAgentInstanceRequest,
    UpdatePromptRequest,
    UpdateSessionRequest,
)
from control_plane_backend.sessions.store import (
    SessionMetadataAlreadyExistsError,
    SessionMetadataRecord,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams.service import list_teams as list_teams_from_service
from control_plane_backend.users.schemas import UserSummary

logger = logging.getLogger(__name__)

_rbac_provider = RBACProvider()


class _RuntimeTemplatePayload:
    """Runtime `/agents/templates` payload consumed by control-plane aggregation."""

    def __init__(
        self,
        *,
        template_agent_id: str,
        title: str,
        description: str,
        kind: str,
        default_tuning: ManagedAgentTuning | None = None,
    ) -> None:
        self.template_agent_id = template_agent_id
        self.title = title
        self.description = description
        self.kind = kind
        self.default_tuning = default_tuning or ManagedAgentTuning(
            role=title,
            description=description,
        )

    @classmethod
    def model_validate(cls, data: dict) -> "_RuntimeTemplatePayload":
        """
        Build one control-plane template payload from the runtime response shape.

        Why this function exists:
        - control-plane keeps its own typed managed-agent models, so runtime
          template payloads need one normalization step before aggregation
        - MCP catalog metadata such as `display_name` and `config_fields` is
          enriched here onto each declared `ManagedMcpServerRef`

        How to use it:
        - call with one raw `/agents/templates` item returned by a runtime pod
        - the method returns a `_RuntimeTemplatePayload` ready for
          `AgentTemplateSummary` projection

        Example:
        - `template = _RuntimeTemplatePayload.model_validate(raw_template)`
        """
        tuning = ManagedAgentTuning.model_validate(
            data.get("default_tuning")
            or {
                "role": data["title"],
                "description": data["description"],
            }
        )
        # Enrich mcp_server refs with display_name and config_fields from the MCP catalog
        catalog_entries: dict[str, dict] = {
            s["id"]: s
            for s in data.get("available_mcp_servers", [])
            if isinstance(s, dict) and "id" in s
        }
        if catalog_entries:
            tuning = tuning.model_copy(
                update={
                    "mcp_servers": [
                        ref.model_copy(
                            update={
                                "display_name": catalog_entries[ref.id].get(
                                    "name", ref.id
                                )
                                if ref.id in catalog_entries
                                else ref.id,
                                "config_fields": [
                                    ManagedAgentFieldSpec.model_validate(f)
                                    for f in catalog_entries.get(ref.id, {}).get(
                                        "config_fields", []
                                    )
                                    if isinstance(f, dict)
                                ],
                            }
                        )
                        for ref in tuning.mcp_servers
                    ]
                }
            )
        return cls(
            template_agent_id=data["template_agent_id"],
            title=data["title"],
            description=data["description"],
            kind=data["kind"],
            default_tuning=tuning,
        )


def _build_permission_summary(user: KeycloakUser) -> PermissionSummary:
    items = _rbac_provider.list_permissions_for_user(user)
    allowed = set(items)
    return PermissionSummary(
        items=items,
        can_view_team_agents="agents:read" in allowed,
        can_manage_team_agents=bool(
            {"agents:create", "agents:update", "agents:delete"} & allowed
        ),
        can_manage_mcp_servers=bool(
            {
                "mcp_servers:create",
                "mcp_servers:update",
                "mcp_servers:delete",
            }
            & allowed
        ),
        can_view_feedback="feedback:read" in allowed,
        can_submit_feedback="feedback:create" in allowed,
        can_create_sessions="sessions:create" in allowed,
    )


async def build_frontend_bootstrap(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> FrontendBootstrap:
    """Build the frontend bootstrap from the shared selectable-team services.

    Why this function exists:
    - bootstrap should consume the same team resolution contract as `/teams` and
      `/teams/{team_id}` so `personal` is not shaped differently per endpoint

    How to use it:
    - call from the frontend bootstrap controller after authentication

    Example:
    - `payload = await build_frontend_bootstrap(user, deps)`
    """
    active_team, available_teams = await asyncio.gather(
        get_team_by_id_from_service(
            user,
            PERSONAL_TEAM_ID,
            deps.team_dependencies,
        ),
        list_teams_from_service(user, deps.team_dependencies),
    )
    return FrontendBootstrap(
        current_user=UserSummary.from_keycloak_user(user),
        active_team=active_team,
        available_teams=available_teams,
        gcu_version=deps.configuration.app.gcu_version,
        feature_flags=deps.configuration.platform.frontend.feature_flags,
        ui_settings=deps.configuration.platform.frontend.ui_settings,
        permissions=_build_permission_summary(user),
    )


async def _fetch_runtime_templates(base_url: str) -> list[_RuntimeTemplatePayload]:
    url = f"{base_url.rstrip('/')}/agents/templates"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    return [_RuntimeTemplatePayload.model_validate(item) for item in payload]


async def _fetch_mcp_catalog(base_url: str) -> dict[str, bool] | None:
    """
    Fetch the live MCP catalog from one runtime pod.

    Returns a mapping of {server_id: enabled} for all declared servers.
    Returns None when the pod is unreachable — callers must distinguish this
    from an empty catalog (pod reachable but no servers configured).
    """
    url = f"{base_url.rstrip('/')}/agents/mcp-catalog"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        return {
            entry["id"]: bool(entry.get("enabled", True))
            for entry in payload.get("servers", [])
            if isinstance(entry, dict) and "id" in entry
        }
    except Exception as exc:
        logger.warning("Failed to fetch MCP catalog from %s: %s", base_url, exc)
        return None


def _validate_tuning_field_values(
    *,
    field_specs: Sequence[ManagedAgentFieldSpec],
    submitted_values: dict[str, Any],
    context_label: str,
    reject_unknown_keys: bool = False,
) -> dict[str, Any]:
    """
    Filter and validate submitted tuning values against one frozen field-spec list.

    Why this function exists:
    - managed-agent writes already constrain values to declared field keys, but
      they also need one shared validator so prompt/settings/chat-option values
      respect the authored field contract before control-plane persists them

    How to use it:
    - pass the frozen `ManagedAgentFieldSpec` list from the template or stored
      instance together with the submitted values dict
    - unknown keys are ignored by default to preserve current write
      compatibility; pass `reject_unknown_keys=True` for dedicated typed
      contracts such as `mcp_config_values`
    - invalid values raise `EnrollmentError(http_status=422)`

    Example:
    - `values = _validate_tuning_field_values(field_specs=tuning.fields, submitted_values={"settings.verbose": True}, context_label="agent enrollment")`
    """
    specs_by_key: dict[str, ManagedAgentFieldSpec] = {
        field.key: field for field in field_specs
    }
    validated: dict[str, Any] = {}
    scalar_string_types = {
        "string",
        "text",
        "text-multiline",
        "prompt",
        "secret",
        "url",
    }

    def _fail(field_key: str, reason: str) -> None:
        raise EnrollmentError(
            f"Invalid value for tuning field {field_key!r} during {context_label}: {reason}.",
            http_status=422,
        )

    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _validate_array_item(
        *, field_key: str, item_type: str | None, value: object
    ) -> None:
        if item_type is None:
            if isinstance(value, (str, int, float, bool)):
                return
            _fail(field_key, "array items must be scalar values")
        if item_type in scalar_string_types or item_type == "select":
            if not isinstance(value, str):
                _fail(field_key, f"array items for type {item_type!r} must be strings")
            return
        if item_type == "boolean":
            if not isinstance(value, bool):
                _fail(field_key, "array items for type 'boolean' must be booleans")
            return
        if item_type == "integer":
            if not (isinstance(value, int) and not isinstance(value, bool)):
                _fail(field_key, "array items for type 'integer' must be integers")
            return
        if item_type == "number":
            if not _is_numeric(value):
                _fail(field_key, "array items for type 'number' must be numeric")
            return
        _fail(field_key, f"unsupported array item_type {item_type!r}")

    for key, value in submitted_values.items():
        field = specs_by_key.get(key)
        if field is None:
            if reject_unknown_keys:
                _fail(key, "unknown key")
            continue
        if value is None:
            continue
        numeric_value: float | None = None

        if field.type in scalar_string_types:
            if not isinstance(value, str):
                _fail(key, f"expected a string for type {field.type!r}")
            if field.pattern is not None and re.fullmatch(field.pattern, value) is None:
                _fail(key, f"value does not match pattern {field.pattern!r}")
            if field.type == "prompt":
                prompt_errors = validate_prompt_template(value)
                if prompt_errors:
                    details = "; ".join(
                        f"'{e.pattern}': {e.reason}" for e in prompt_errors
                    )
                    _fail(key, f"invalid template syntax — {details}")
        elif field.type == "select":
            if not isinstance(value, str):
                _fail(key, "expected a string for type 'select'")
        elif field.type == "boolean":
            if not isinstance(value, bool):
                _fail(key, "expected a boolean")
        elif field.type == "integer":
            if not (isinstance(value, int) and not isinstance(value, bool)):
                _fail(key, "expected an integer")
            numeric_value = float(value)
        elif field.type == "number":
            if not _is_numeric(value):
                _fail(key, "expected a number")
            numeric_value = float(value)
        elif field.type == "array":
            if not isinstance(value, list):
                _fail(key, "expected an array")
            for item in value:
                _validate_array_item(
                    field_key=key, item_type=field.item_type, value=item
                )
        elif field.type == "object":
            if not isinstance(value, dict):
                _fail(key, "expected an object")
            if not all(
                isinstance(obj_key, str)
                and isinstance(obj_value, (str, int, float, bool))
                for obj_key, obj_value in value.items()
            ):
                _fail(key, "object keys must be strings and values must be scalars")
        else:
            _fail(key, f"unsupported field type {field.type!r}")

        if field.enum is not None and value not in field.enum:
            _fail(key, f"value must be one of {field.enum!r}")
        if numeric_value is not None:
            if field.min is not None and numeric_value < field.min:
                _fail(key, f"value must be >= {field.min}")
            if field.max is not None and numeric_value > field.max:
                _fail(key, f"value must be <= {field.max}")

        validated[key] = value
    return validated


def _validate_mcp_server_ids(
    *,
    submitted_ids: list[str],
    available_ids: frozenset[str],
    context_label: str,
) -> list[str]:
    """
    Validate submitted MCP server IDs against the template's declared servers.

    Unknown IDs raise EnrollmentError(422); known IDs are returned as-is.
    """
    unknown = [sid for sid in submitted_ids if sid not in available_ids]
    if unknown:
        raise EnrollmentError(
            f"Unknown MCP server ID(s) in {context_label}: {unknown!r}. "
            "Only server IDs declared by the template are allowed.",
            http_status=422,
        )
    return submitted_ids


def _selected_mcp_servers(
    *,
    declared_servers: Sequence[Any],
    selected_server_ids: list[str] | None,
) -> list[Any]:
    """
    Resolve the active MCP server refs for one managed instance.

    Why this function exists:
    - the managed-agent contract now distinguishes three states for MCP
      selection: inherit template defaults (`None`), activate none (`[]`), or
      activate one exact subset (non-empty list)

    How to use it:
    - pass the declared server list and the stored selection value
    - the returned list preserves the template order for deterministic UI and
      effective-chat-option resolution

    Example:
    - `_selected_mcp_servers(declared_servers=tuning.mcp_servers, selected_server_ids=None)`
    """

    if selected_server_ids is None:
        return list(declared_servers)
    selected = frozenset(selected_server_ids)
    return [server for server in declared_servers if server.id in selected]


def _prune_inactive_mcp_config_values(
    *,
    declared_servers: Sequence[Any],
    selected_server_ids: list[str] | None,
    stored_values: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Drop stored MCP config for servers that are no longer active.

    Why this function exists:
    - changing the MCP selection should not leave behind hidden config for
      servers that are no longer active for the instance

    How to use it:
    - call after applying a new `selected_mcp_server_ids` value and before
      persisting the updated tuning payload

    Example:
    - `_prune_inactive_mcp_config_values(..., selected_server_ids=["mcp-search"], stored_values=base.mcp_config_values)`
    """

    active_ids = {
        server.id
        for server in _selected_mcp_servers(
            declared_servers=declared_servers,
            selected_server_ids=selected_server_ids,
        )
    }
    return {
        server_id: values
        for server_id, values in stored_values.items()
        if server_id in active_ids
    }


def _validate_mcp_config_values(
    *,
    declared_servers: Sequence[Any],
    selected_server_ids: list[str] | None,
    submitted_values: dict[str, dict[str, Any]],
    context_label: str,
) -> dict[str, dict[str, Any]]:
    """
    Validate one dedicated per-server MCP configuration payload.

    Why this function exists:
    - MCP tool options are no longer generic tuning-field keys; they need a
      dedicated typed validator keyed by server id and then by config-field key

    How to use it:
    - pass the declared MCP server refs, the target selected-server policy, and
      the nested submitted values map
    - unknown or inactive server ids raise HTTP 422
    - unknown config keys raise HTTP 422 because `mcp_config_values` is a
      dedicated typed contract, not a compatibility bag

    Example:
    - `_validate_mcp_config_values(declared_servers=tuning.mcp_servers, selected_server_ids=None, submitted_values={"mcp-search": {"chat_options.search_policy": "hybrid"}}, context_label="agent enrollment")`
    """

    active_servers = {
        server.id: server
        for server in _selected_mcp_servers(
            declared_servers=declared_servers,
            selected_server_ids=selected_server_ids,
        )
    }
    validated: dict[str, dict[str, Any]] = {}
    for server_id, server_values in submitted_values.items():
        server = active_servers.get(server_id)
        if server is None:
            raise EnrollmentError(
                f"Unknown or inactive MCP server ID {server_id!r} in {context_label}.",
                http_status=422,
            )
        if not isinstance(server_values, dict):
            raise EnrollmentError(
                f"Invalid mcp_config_values entry for server {server_id!r} during {context_label}: expected an object.",
                http_status=422,
            )
        typed_values = _validate_tuning_field_values(
            field_specs=server.config_fields,
            submitted_values=server_values,
            context_label=f"{context_label} for MCP server {server_id!r}",
            reject_unknown_keys=True,
        )
        if typed_values:
            validated[server_id] = typed_values
    return validated


def _as_bool(value: object) -> bool:
    """
    Return a strict boolean view of one stored tuning value.

    Why this function exists:
    - resolved chat options combine values coming from generic tuning and
      per-tool config, both of which are stored as union-typed payloads
    - the frontend contract should only treat literal `True` / `False` values
      as booleans, never truthy strings or numbers

    How to use it:
    - pass any stored tuning value before assigning it to a boolean field on a
      typed outward-facing contract

    Example:
    - `_as_bool(tuning.values.get("chat_options.attach_files"))`
    """

    return isinstance(value, bool) and value


def _resolve_effective_chat_options(
    tuning: ManagedAgentTuning,
) -> EffectiveChatOptions:
    """
    Resolve the chat-option surface exposed by one managed agent instance.

    Why this function exists:
    - the managed chat UI must consume one explicit typed contract instead of
      inferring search controls from hard-coded agent or MCP ids
    - prompts/settings and tool config have different ownership, but the UI
      still needs one merged chat-affordance view

    How to use it:
    - call when building frontend-facing execution-preparation payloads
    - template order decides precedence when multiple active MCP servers expose
      the same option key

    Example:
    - `options = _resolve_effective_chat_options(instance.tuning)`
    """

    options = EffectiveChatOptions(
        attach_files=_as_bool(tuning.values.get("chat_options.attach_files"))
    )
    active_servers = _selected_mcp_servers(
        declared_servers=tuning.mcp_servers,
        selected_server_ids=tuning.selected_mcp_server_ids,
    )

    for server in active_servers:
        field_defaults = {field.key: field.default for field in server.config_fields}
        server_values = tuning.mcp_config_values.get(server.id, {})

        if "chat_options.libraries_selection" in field_defaults:
            value = server_values.get(
                "chat_options.libraries_selection",
                field_defaults["chat_options.libraries_selection"],
            )
            options.libraries_selection = options.libraries_selection or _as_bool(value)

        if (
            not options.search_policy_selection
            and "chat_options.search_policy" in field_defaults
        ):
            value = server_values.get(
                "chat_options.search_policy",
                field_defaults["chat_options.search_policy"],
            )
            if value in {"strict", "hybrid", "semantic"}:
                options.search_policy_selection = True
                options.default_search_policy = cast(
                    Literal["strict", "hybrid", "semantic"], value
                )

        if (
            not options.rag_scope_selection
            and "chat_options.search_rag_scope" in field_defaults
        ):
            value = server_values.get(
                "chat_options.search_rag_scope",
                field_defaults["chat_options.search_rag_scope"],
            )
            if value in {"corpus_only", "hybrid", "general_only"}:
                options.rag_scope_selection = True
                options.default_search_rag_scope = cast(
                    Literal["corpus_only", "hybrid", "general_only"], value
                )

    return options


async def list_agent_templates(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> list[AgentTemplateSummary]:
    """
    Aggregate template summaries from all enabled configured runtime pods.

    Why this function exists:
    - template discovery is a control-plane product concern that must merge the
      live catalogs exposed by configured runtime pods

    How to use it:
    - call from the team template-listing route for one team context
    - pass request-scoped product dependencies when available

    Example:
    - `templates = await list_agent_templates(team_id, deps)`
    """
    templates: list[AgentTemplateSummary] = []
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            runtime_templates = await _fetch_runtime_templates(source.base_url)
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Failed to fetch runtime templates from %s for team %s: %s",
                source.base_url,
                team_id,
                exc,
            )
            continue

        for template in runtime_templates:
            templates.append(
                AgentTemplateSummary(
                    template_id=f"{source.runtime_id}:{template.template_agent_id}",
                    source_runtime_id=source.runtime_id,
                    source_agent_id=template.template_agent_id,
                    display_name=template.title,
                    description=template.description,
                    category=template.kind,
                    capabilities=[template.kind],
                    default_tuning_fields=template.default_tuning.fields,
                    mcp_servers=template.default_tuning.mcp_servers,
                )
            )
    return templates


async def list_managed_agent_instances(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> list[ManagedAgentInstanceSummary]:
    """
    Return the enrolled managed agent instances for one team, with drift detection.

    Why this function exists:
    - the product surface must expose managed agent instances by stable
      `agent_instance_id`, separate from live runtime catalog discovery
    - drift detection surfaces MCP server selection mismatches to the admin
      before they cause silent execution failures

    How to use it:
    - call from the team agent-instances route
    - pass request-scoped product dependencies when available

    Example:
    - `instances = await list_managed_agent_instances(team_id, deps)`
    """
    store = deps.get_agent_instance_store()
    records = await store.list_by_team(team_id)

    # Build a catalog-per-source map for drift detection; failures → "unavailable".
    catalog_by_source: dict[str, dict[str, bool] | None] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        catalog_by_source[source.runtime_id] = await _fetch_mcp_catalog(source.base_url)

    summaries: list[ManagedAgentInstanceSummary] = []
    for record in records:
        catalog = catalog_by_source.get(record.source_runtime_id)
        if catalog is None:
            summaries.append(_record_to_summary(record, runtime_status="unavailable"))
            continue

        warnings: list[str] = []
        active_servers = _selected_mcp_servers(
            declared_servers=record.tuning.mcp_servers,
            selected_server_ids=record.tuning.selected_mcp_server_ids,
        )
        for sid in (server.id for server in active_servers):
            if sid not in catalog:
                warnings.append(f"MCP server '{sid}' is no longer in the pod catalog.")
            elif not catalog[sid]:
                warnings.append(f"MCP server '{sid}' is disabled in the pod catalog.")
        summaries.append(_record_to_summary(record, catalog_warnings=warnings))

    return summaries


def _record_to_summary(
    record: AgentInstanceRecord,
    *,
    runtime_status: Literal["ok", "unavailable"] = "ok",
    catalog_warnings: list[str] | None = None,
) -> ManagedAgentInstanceSummary:
    """
    Build one frontend-facing summary from a DB-backed agent instance record.

    Why this function exists:
    - the product listing surface needs one canonical projection from stored
      managed-agent records to the summary contract returned to the UI

    How to use it:
    - pass one store record plus optional runtime-status/warning annotations
      computed by the caller

    Example:
    - `_record_to_summary(record, runtime_status="unavailable")`
    """
    return ManagedAgentInstanceSummary(
        agent_instance_id=record.agent_instance_id,
        team_id=record.team_id,
        template_id=record.template_id,
        display_name=record.display_name,
        description=record.description,
        status="enabled" if record.enabled else "disabled",
        created_at=record.created_at,
        updated_at=record.updated_at,
        created_by=record.created_by,
        tuning_field_values=record.tuning.values,
        mcp_config_values=record.tuning.mcp_config_values,
        selected_mcp_server_ids=(
            list(record.tuning.selected_mcp_server_ids)
            if record.tuning.selected_mcp_server_ids is not None
            else None
        ),
        runtime_status=runtime_status,
        catalog_warnings=catalog_warnings or [],
    )


_EXECUTION_GRANT_TTL_SECONDS = 300  # 5 minutes


class ExecutionPreparationError(Exception):
    """Raised when execution preparation cannot be completed."""

    def __init__(self, message: str, *, http_status: int = 404) -> None:
        super().__init__(message)
        self.http_status = http_status


class EnrollmentError(Exception):
    """Raised when agent instance enrollment fails."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


class PromptRequestError(Exception):
    """Raised when prompt-library CRUD cannot be completed as requested."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


class SessionAlreadyExistsError(Exception):
    """Raised when control-plane session metadata already exists."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id!r} already exists.")
        self.session_id = session_id


async def enroll_agent_instance(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateAgentInstanceRequest,
    deps: ProductServiceDependencies,
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for a team, creating a DB-backed managed instance.

    Why this function exists:
    - enrollment turns one live template into a DB-backed managed instance that
      can later be prepared for team-scoped execution

    How to use it:
    - pass a validated team, the authenticated user, and the typed enrollment
      request
    - pass request-scoped product dependencies when available
    - `tuning_field_values` configures agent-authored fields only
    - `mcp_server_ids` and `mcp_config_values` configure tool activation and
      per-tool options through dedicated typed surfaces

    Example:
    - `item = await enroll_agent_instance(user=user, team_id=team_id, request=body, deps=deps)`
    """
    parts = request.template_id.split(":", 1)
    if len(parts) != 2:
        raise EnrollmentError(
            f"Invalid template_id {request.template_id!r}. "
            "Expected format: '{source_runtime_id}:{source_agent_id}'."
        )
    source_runtime_id, source_agent_id = parts

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise EnrollmentError(
            f"Runtime source {source_runtime_id!r} is not available or not enabled.",
            http_status=404,
        )

    agent_instance_id = str(uuid4())
    runtime_templates = await _fetch_runtime_templates(source.base_url)
    template = next(
        (
            item
            for item in runtime_templates
            if item.template_agent_id == source_agent_id
        ),
        None,
    )
    if template is None:
        raise EnrollmentError(
            f"Template {request.template_id!r} was not found on runtime source "
            f"{source_runtime_id!r}.",
            http_status=404,
        )

    tuning = template.default_tuning.model_copy(
        update={
            "role": request.display_name,
            "description": request.description or request.display_name,
        }
    )
    if request.tuning_field_values:
        tuning = tuning.model_copy(
            update={
                "values": _validate_tuning_field_values(
                    field_specs=tuning.fields,
                    submitted_values=request.tuning_field_values,
                    context_label="agent enrollment",
                )
            }
        )
    if request.mcp_server_ids is not None:
        available = frozenset(srv.id for srv in tuning.mcp_servers)
        validated_ids = _validate_mcp_server_ids(
            submitted_ids=request.mcp_server_ids,
            available_ids=available,
            context_label="agent enrollment",
        )
        tuning = tuning.model_copy(update={"selected_mcp_server_ids": validated_ids})
    if request.mcp_config_values:
        tuning = tuning.model_copy(
            update={
                "mcp_config_values": _validate_mcp_config_values(
                    declared_servers=tuning.mcp_servers,
                    selected_server_ids=tuning.selected_mcp_server_ids,
                    submitted_values=request.mcp_config_values,
                    context_label="agent enrollment",
                )
            }
        )
    record = AgentInstanceRecord(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        template_id=request.template_id,
        source_runtime_id=source_runtime_id,
        source_agent_id=source_agent_id,
        display_name=request.display_name,
        description=request.description,
        enabled=True,
        created_by=user.uid,
        tuning=tuning,
    )

    store = deps.get_agent_instance_store()
    created = await store.create(record)
    return _record_to_summary(created)


async def update_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    request: UpdateAgentInstanceRequest,
    deps: ProductServiceDependencies,
) -> ManagedAgentInstanceSummary | None:
    """
    Update display_name, description, or tuning field values for one managed instance.

    Why this function exists:
    - teams need to be able to customise display metadata and per-instance field
      values after enrollment without re-enrolling from scratch

    How to use it:
    - pass only the fields to change
    - omitted fields are left unchanged
    - `tuning_field_values=None` clears stored agent tuning values
    - `mcp_server_ids=None` resets the instance to the template default MCP
      selection; `mcp_server_ids=[]` activates no MCP servers
    - `mcp_config_values=None` clears stored per-server MCP config

    Policy — frozen snapshot:
    - field specs (ManagedAgentFieldSpec) are frozen at enrollment time
    - they are never re-merged with the current template when the instance is edited
    - only known keys (present in instance.tuning.fields) are accepted

    Example:
    - `result = await update_agent_instance(team_id=team_id, agent_instance_id=id, request=req, deps=deps)`
    """
    store = deps.get_agent_instance_store()
    record = await store.get_for_team(agent_instance_id, team_id)
    if record is None:
        return None

    tuning_fields_set = request.model_fields_set
    new_tuning: ManagedAgentTuning | None = None
    if {
        "tuning_field_values",
        "mcp_server_ids",
        "mcp_config_values",
    } & tuning_fields_set:
        base = record.tuning
        if "mcp_server_ids" in tuning_fields_set:
            if request.mcp_server_ids is None:
                base = base.model_copy(update={"selected_mcp_server_ids": None})
            else:
                available = frozenset(srv.id for srv in base.mcp_servers)
                validated_ids = _validate_mcp_server_ids(
                    submitted_ids=request.mcp_server_ids,
                    available_ids=available,
                    context_label="agent update",
                )
                base = base.model_copy(
                    update={"selected_mcp_server_ids": validated_ids}
                )
            base = base.model_copy(
                update={
                    "mcp_config_values": _prune_inactive_mcp_config_values(
                        declared_servers=base.mcp_servers,
                        selected_server_ids=base.selected_mcp_server_ids,
                        stored_values=base.mcp_config_values,
                    )
                }
            )
        if "tuning_field_values" in tuning_fields_set:
            if request.tuning_field_values is None:
                base = base.model_copy(update={"values": {}})
            else:
                base = base.model_copy(
                    update={
                        "values": _validate_tuning_field_values(
                            field_specs=base.fields,
                            submitted_values=request.tuning_field_values,
                            context_label="agent update",
                        )
                    }
                )
        if "mcp_config_values" in tuning_fields_set:
            if request.mcp_config_values is None:
                base = base.model_copy(update={"mcp_config_values": {}})
            else:
                base = base.model_copy(
                    update={
                        "mcp_config_values": _validate_mcp_config_values(
                            declared_servers=base.mcp_servers,
                            selected_server_ids=base.selected_mcp_server_ids,
                            submitted_values=request.mcp_config_values,
                            context_label="agent update",
                        )
                    }
                )
        new_tuning = base

    updated = await store.update(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        display_name=request.display_name,
        description=request.description,
        enabled=request.status == "enabled" if request.status is not None else None,
        tuning=new_tuning,
    )
    return _record_to_summary(updated) if updated is not None else None


async def unenroll_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Unenroll (delete) one managed agent instance for a team.

    Why this function exists:
    - managed agent lifecycle stays in control-plane, so unbinding is a local
      metadata deletion rather than a runtime call

    How to use it:
    - call after team authorization has already been checked
    - pass request-scoped product dependencies when available

    Example:
    - `deleted = await unenroll_agent_instance(team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()
    return await store.delete(agent_instance_id, team_id)


async def prepare_execution(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> ExecutionPreparation:
    """
    Prepare one authorized runtime execution context for one managed agent instance.

    Why this function exists:
    - control-plane must issue team-scoped execution context and ingress-safe
      runtime URLs without taking over runtime execution itself

    How to use it:
    - call after team membership has already been validated
    - pass request-scoped product dependencies when available
    - the returned payload now includes `effective_chat_options`, the typed
      chat-affordance surface resolved from the stored managed-agent config

    Example:
    - `prep = await prepare_execution(user=user, team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()

    instance = await store.get_for_team(agent_instance_id, team_id)
    if instance is None:
        raise ExecutionPreparationError(
            f"Unknown agent instance {agent_instance_id!r} for team {team_id!r}."
        )
    if not instance.enabled:
        raise ExecutionPreparationError(
            f"Agent instance {agent_instance_id!r} is disabled.",
            http_status=409,
        )

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == instance.source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} is not available.",
            http_status=503,
        )
    if not source.ingress_prefix:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} has no ingress_prefix "
            "configured. Set ingress_prefix in platform.runtime_catalog_sources.",
            http_status=503,
        )

    prefix = source.ingress_prefix.rstrip("/")
    now = int(time.time())
    grant = ExecutionGrant(
        user_id=user.uid,
        team_id=str(team_id),
        agent_instance_id=agent_instance_id,
        action=ExecutionGrantAction.EXECUTE,
        audience=prefix,
        issued_at=now,
        expires_at=now + _EXECUTION_GRANT_TTL_SECONDS,
    )

    return ExecutionPreparation(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        runtime_id=source.runtime_id,
        execute_url=f"{prefix}/agents/execute",
        execute_stream_url=f"{prefix}/agents/execute/stream",
        messages_url_template=f"{prefix}/agents/sessions/{{session_id}}/messages",
        execution_grant=grant,
        effective_chat_options=_resolve_effective_chat_options(instance.tuning),
        expires_at=datetime.fromtimestamp(grant.expires_at, tz=timezone.utc),
        runtime_display_name=source.runtime_id,
    )


async def get_runtime_binding(
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> ManagedAgentRuntimeBinding | None:
    """
    Resolve one managed agent instance into the runtime-facing binding payload.

    Why this function exists:
    - operators and internal flows need a typed way to inspect how one managed
      instance maps back to its runtime-facing identity

    How to use it:
    - call with one `agent_instance_id`
    - pass request-scoped product dependencies when available

    Example:
    - `binding = await get_runtime_binding("inst-1", deps)`
    """
    store = deps.get_agent_instance_store()
    instance = await store.get(agent_instance_id)
    if instance is None:
        return None
    return ManagedAgentRuntimeBinding(
        agent_instance_id=instance.agent_instance_id,
        template_agent_id=instance.source_agent_id,
        owner_team_id=instance.team_id,
        enabled=instance.enabled,
        tuning=instance.tuning,
    )


# ---------------------------------------------------------------------------
# Prompt library
# ---------------------------------------------------------------------------


def _validate_prompt_library_text(
    *,
    text: str,
    context_label: str,
) -> None:
    """
    Validate one saved prompt-library text payload before persistence.

    Why this function exists:
    - managed-agent tuning validation already protects inline `prompts.*`
      values, but the prompt library needs the same persistence-time safety at
      its own CRUD boundary

    How to use it:
    - call before creating or updating one `Prompt` record
    - invalid template syntax raises `PromptRequestError(http_status=422)`

    Example:
    - `_validate_prompt_library_text(text=request.text, context_label="prompt create")`
    """

    prompt_errors = validate_prompt_template(text)
    if not prompt_errors:
        return
    details = "; ".join(f"'{error.pattern}': {error.reason}" for error in prompt_errors)
    raise PromptRequestError(
        f"Invalid prompt template during {context_label}: {details}.",
        http_status=422,
    )


def _prompt_record_to_summary(record: PromptRecord) -> PromptSummary:
    """Project one stored prompt record into the list/command summary shape.

    Why this function exists:
    - prompt list surfaces should hide the full prompt text by default while
      keeping one consistent typed projection

    How to use it:
    - call after reading prompt records from the store for list/create/update
      responses

    Example:
    - `summary = _prompt_record_to_summary(record)`
    """

    return PromptSummary(
        id=record.prompt_id,
        name=record.name,
        description=record.description,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _prompt_record_to_detail(record: PromptRecord) -> PromptDetail:
    """Project one stored prompt record into the full detail response shape.

    Why this function exists:
    - prompt inspection flows need the saved text, team scope, and metadata in
      one stable outward-facing contract

    How to use it:
    - call after reading one prompt record for the detail endpoint or CLI
      inspection flows

    Example:
    - `detail = _prompt_record_to_detail(record)`
    """

    return PromptDetail(
        id=record.prompt_id,
        team_id=record.team_id,
        name=record.name,
        description=record.description,
        text=record.text,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def create_prompt(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreatePromptRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary:
    """
    Create one team-scoped prompt-library record.

    Why this function exists:
    - prompt authoring must become a first-class control-plane product surface
      instead of staying buried inside managed-agent instance forms

    How to use it:
    - call from the prompt-library POST route after team membership is checked
    - invalid template syntax raises `PromptRequestError(422)`
    - duplicate prompt names inside the same team raise `PromptRequestError(409)`

    Example:
    - `summary = await create_prompt(user=user, team_id=team_id, request=body, deps=deps)`
    """

    _validate_prompt_library_text(
        text=request.text,
        context_label=f"prompt create for team {team_id!r}",
    )
    record = PromptRecord(
        prompt_id=str(uuid4()),
        team_id=team_id,
        name=request.name,
        description=request.description,
        text=request.text,
        created_by=user.username if user else None,
    )
    try:
        created = await deps.get_prompt_store().create(record)
    except PromptAlreadyExistsError as exc:
        raise PromptRequestError(
            f"Prompt name {request.name!r} already exists for team {team_id!r}.",
            http_status=409,
        ) from exc
    return _prompt_record_to_summary(created)


async def list_prompts(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    *,
    limit: int = 100,
) -> list[PromptSummary]:
    """
    List prompt-library records for one team, newest first.

    Why this function exists:
    - prompt management needs a stable control-plane listing surface separate
      from managed-agent CRUD

    How to use it:
    - call from the team prompts route after team membership is checked

    Example:
    - `prompts = await list_prompts(team_id, deps, limit=100)`
    """

    records = await deps.get_prompt_store().list_by_team(team_id, limit=limit)
    return [_prompt_record_to_summary(record) for record in records]


async def get_prompt(
    team_id: TeamId,
    prompt_id: str,
    deps: ProductServiceDependencies,
) -> PromptDetail | None:
    """
    Return one full prompt-library record for one team.

    Why this function exists:
    - operators need to inspect saved prompt text independently from agent
      bindings

    How to use it:
    - call from the prompt detail route with the resolved team scope

    Example:
    - `detail = await get_prompt(team_id, prompt_id, deps)`
    """

    record = await deps.get_prompt_store().get_for_team(prompt_id, team_id)
    if record is None:
        return None
    return _prompt_record_to_detail(record)


async def update_prompt(
    team_id: TeamId,
    prompt_id: str,
    request: UpdatePromptRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary | None:
    """
    Replace one team-scoped prompt-library record.

    Why this function exists:
    - the initial prompt-library slice intentionally keeps one simple mutable
      record model instead of version graphs or per-field patch semantics

    How to use it:
    - call from the prompt PUT route after team membership is checked
    - returns `None` when the prompt does not belong to `team_id`
    - invalid template syntax raises `PromptRequestError(422)`
    - duplicate names raise `PromptRequestError(409)`

    Example:
    - `summary = await update_prompt(team_id, prompt_id, request, deps)`
    """

    _validate_prompt_library_text(
        text=request.text,
        context_label=f"prompt update for team {team_id!r}",
    )
    try:
        updated = await deps.get_prompt_store().update(
            prompt_id,
            team_id,
            name=request.name,
            description=request.description,
            text=request.text,
        )
    except PromptAlreadyExistsError as exc:
        raise PromptRequestError(
            f"Prompt name {request.name!r} already exists for team {team_id!r}.",
            http_status=409,
        ) from exc
    if updated is None:
        return None
    return _prompt_record_to_summary(updated)


async def delete_prompt(
    team_id: TeamId,
    prompt_id: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Delete one team-scoped prompt-library record.

    Why this function exists:
    - prompt-library cleanup belongs to control-plane product lifecycle, not to
      managed-agent instance writes

    How to use it:
    - call from the prompt DELETE route after team membership is checked

    Example:
    - `deleted = await delete_prompt(team_id, prompt_id, deps)`
    """

    return await deps.get_prompt_store().delete(prompt_id, team_id)


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


async def create_session(
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateSessionRequest,
    deps: ProductServiceDependencies,
) -> SessionListItem:
    """
    Register one new control-plane-owned session metadata record.

    Why this function exists:
    - the frontend needs a lightweight control-plane row as soon as a team
      session starts, before later activity refreshes
    - duplicate `session_id` creation should surface as a domain conflict
      rather than a storage-specific exception

    How to use it:
    - call once when a team starts a brand-new session id
    - catch `SessionAlreadyExistsError` when a duplicate should map to HTTP 409

    Example:
    - `item = await create_session(user, team_id, request, deps)`
    """
    record = SessionMetadataRecord(
        session_id=request.session_id,
        team_id=team_id,
        agent_instance_id=request.agent_instance_id,
        user_id=user.username if user else None,
        title=request.title,
    )
    try:
        created = await deps.get_session_metadata_store().create(record)
    except SessionMetadataAlreadyExistsError as exc:
        raise SessionAlreadyExistsError(request.session_id) from exc
    return _record_to_item(created)


async def list_sessions(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    limit: int = 50,
) -> list[SessionListItem]:
    """
    List session metadata records for one team, newest first.

    Why this function exists:
    - the frontend sidebar needs a lightweight control-plane list, separate from
      runtime-owned message history

    How to use it:
    - call from the team sessions route
    - pass request-scoped product dependencies when available

    Example:
    - `sessions = await list_sessions(team_id, limit=50, deps=deps)`
    """
    records = await deps.get_session_metadata_store().list_by_team(
        team_id,
        limit=limit,
    )
    return [_record_to_item(r) for r in records]


async def update_session_activity(
    team_id: TeamId,
    session_id: str,
    request: UpdateSessionRequest,
    deps: ProductServiceDependencies,
) -> SessionListItem | None:
    """
    Refresh control-plane metadata for one completed managed turn.

    Why this function exists:
    - The sidebar sorts sessions by control-plane-owned `updated_at`, while
      runtime remains the only owner of message content.

    How to use it:
    - call from the PATCH session metadata endpoint after runtime reports a
      completed turn.

    Example:
    - `await update_session_activity(team_id, session_id, request, deps)`
    """
    record = await deps.get_session_metadata_store().update_metadata(
        session_id=session_id,
        team_id=team_id,
        title=request.title,
        updated_at=request.updated_at,
    )
    if record is None:
        return None
    return _record_to_item(record)


async def delete_session(
    team_id: TeamId,
    session_id: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Remove one control-plane session metadata record.

    Returns True when a row was deleted, False when the session did not exist.
    """
    return await deps.get_session_metadata_store().delete(
        session_id=session_id,
        team_id=team_id,
    )


def _record_to_item(record: SessionMetadataRecord) -> SessionListItem:
    return SessionListItem(
        session_id=record.session_id,
        team_id=record.team_id,
        agent_instance_id=record.agent_instance_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
