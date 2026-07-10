from __future__ import annotations

from datetime import datetime
from typing import Literal

from fred_core.common import TeamId
from fred_sdk.contracts.models import TuningValue
from pydantic import BaseModel, Field

from control_plane_backend.config.models import (
    FrontendFeatureFlags,
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
    ManagedMcpServerRef,
)
from control_plane_backend.product.prompt_category import PromptCategory
from control_plane_backend.teams.schemas import Team, TeamWithPermissions
from control_plane_backend.users.schemas import UserSummary


class PermissionSummary(BaseModel):
    """Frontend-friendly permission projection for product bootstrap flows."""

    items: list[str] = Field(default_factory=list)
    can_view_team_agents: bool = False
    can_manage_team_agents: bool = False
    can_manage_mcp_servers: bool = False
    can_view_feedback: bool = False
    can_submit_feedback: bool = False
    can_create_sessions: bool = False
    is_platform_admin: bool = Field(
        default=False,
        description=(
            "OpenFGA-derived platform-admin flag (organization `can_manage_platform`). "
            "The single source of truth for gating admin-only UI surfaces — never "
            "derive admin UI access from Keycloak roles directly."
        ),
    )
    is_platform_observer: bool = Field(
        default=False,
        description=(
            "OpenFGA-derived platform-observer flag (organization `platform_observer` "
            "relation, checked directly). Grants read-only platform observability "
            "surfaces without full platform-admin rights."
        ),
    )


class FrontendBootstrap(BaseModel):
    """Small frontend bootstrap payload owned by control-plane."""

    current_user: UserSummary
    active_team: TeamWithPermissions
    available_teams: list[Team] = Field(default_factory=list)
    gcu_version: str | None = None
    feature_flags: FrontendFeatureFlags
    permissions: PermissionSummary


class FrontendUserAuthConfig(BaseModel):
    """Public pre-auth user-authentication config for frontend bootstrap.

    Mirrors `fred_core` `SecurityConfiguration.user`. Served unauthenticated so the
    frontend can decide whether to initialize Keycloak *before* any login. Carries
    only public OIDC client values (`realm_url`, `client_id`) — never secrets, and
    `realm_url`/`client_id` are emitted only when auth is enabled.
    """

    enabled: bool
    realm_url: str | None = None
    client_id: str | None = None


class FrontendConfig(BaseModel):
    """Public pre-auth frontend configuration surface.

    Served by an unauthenticated endpoint and consumed at Stage 0 of frontend
    startup, before the auth decision. Kept intentionally minimal — user auth
    plus the Terms-of-Use (CGU) gating switch. No product/session/team state
    (that stays on `FrontendBootstrap`).
    """

    user_auth: FrontendUserAuthConfig
    gcu_version: str | None = None
    """Active Terms-of-Use / CGU version the deployment requires, or `None` when
    gating is off. This is the **authoritative** source the frontend GCU guard
    reads: it must be available *before* authentication, because the
    authenticated `/frontend/bootstrap` is itself GCU-gated (it 403s with
    `user_not_accept_gcu` until the user accepts) — a chicken-and-egg that would
    otherwise hide the very version needed to render the acceptance page. The
    value is `None` whenever gating is effectively disabled (user auth off, per
    `security.user.enabled`, or `app.gcu_version` unset), so deployments without
    CGU are never routed to the acceptance screen."""


class AgentTemplateSummary(BaseModel):
    """Catalog summary for one instantiable managed-agent template."""

    template_id: str
    source_runtime_id: str
    source_agent_id: str
    display_name: str
    description: str
    description_by_lang: dict[str, str] | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    team_instantiable: bool = True
    status: Literal["available", "unavailable"] = "available"
    default_tuning_fields: list[ManagedAgentFieldSpec] = Field(
        default_factory=list,
        description=(
            "Tunable field descriptors declared by the template. "
            "The frontend renders these dynamically at enrollment time. "
            "Empty when the template declares no tunable fields."
        ),
    )
    mcp_servers: list[ManagedMcpServerRef] = Field(
        default_factory=list,
        description=(
            "MCP server references advertised by this template. "
            "Empty when the template declares no MCP dependencies."
        ),
    )


class EffectiveChatOptions(BaseModel):
    """Resolved chat options derived from the managed instance configuration."""

    attach_files: bool = False
    libraries_selection: bool = False
    documents_selection: bool = False
    search_policy_selection: bool = False
    default_search_policy: Literal["strict", "hybrid", "semantic"] = "hybrid"
    rag_scope_selection: bool = False
    default_search_rag_scope: Literal["corpus_only", "hybrid", "general_only"] = (
        "hybrid"
    )
    bound_library_ids: list[str] | None = Field(
        default=None,
        description=(
            "When non-null, the agent is configured to use exactly these library IDs. "
            "The frontend must render the library picker as read-only and send exactly "
            "this list in RuntimeContext.selected_document_libraries_ids. "
            "Null means the user can freely select from all available libraries."
        ),
    )


class ManagedAgentInstanceSummary(BaseModel):
    """Primary team-visible managed agent identity exposed to the frontend."""

    agent_instance_id: str
    team_id: TeamId
    template_id: str
    display_name: str
    description: str | None = None
    status: Literal["enabled", "disabled"]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    tuning_field_values: dict[str, TuningValue] = Field(
        default_factory=dict,
        description=(
            "Current user-set values for this instance's tunable fields. "
            "Keyed by ManagedAgentFieldSpec.key. Empty when no fields have been customised."
        ),
    )
    mcp_config_values: dict[str, dict[str, TuningValue]] = Field(
        default_factory=dict,
        description=(
            "Per-server MCP configuration values keyed first by server id and "
            "then by ManagedAgentFieldSpec.key. Empty when no MCP options have "
            "been customised."
        ),
    )
    selected_mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Admin-chosen MCP server activation policy for this instance. "
            "Null means inherit the template default selection (all declared "
            "servers active); [] means activate no MCP servers; a non-empty "
            "list means activate exactly that subset."
        ),
    )
    runtime_status: Literal["ok", "unavailable"] = Field(
        default="ok",
        description=(
            "ok when the pod is reachable at listing time; "
            "unavailable when the pod cannot be contacted."
        ),
    )
    catalog_warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-empty when stored MCP server IDs are absent from the live pod catalog. "
            "Admin must delete and recreate the instance to resolve."
        ),
    )
    effective_chat_options: EffectiveChatOptions = Field(
        default_factory=EffectiveChatOptions,
        description=(
            "Resolved chat affordances for this instance, computed from active MCP "
            "server config_fields and tuning values. Tells the frontend which composer "
            "controls to show without waiting for prepare-execution."
        ),
    )


class RuntimeAgentExecutionPreparation(BaseModel):
    """
    Execution preparation for a direct runtime agent target (not a managed instance).

    Returned by POST /teams/{team_id}/runtimes/{runtime_id}/prepare-execution.
    Gives the evaluation worker an ingress-safe URL and a short-lived grant
    without exposing cluster-internal hostnames.
    """

    runtime_id: str
    agent_id: str
    team_id: TeamId
    evaluate_url: str = Field(
        ..., description="Ingress-relative URL for POST /agents/evaluate."
    )


class ExecutionPreparation(BaseModel):
    """
    Control-plane contract returned by prepare-execution.

    Gives the frontend everything needed to call one runtime pod securely
    without learning cluster topology.

    URL fields (execute_url, execute_stream_url, messages_url_template) MUST be:
    - relative, ingress-facing, opaque to the frontend
    - MUST NOT be *.svc.cluster.local, Pod IPs, or cluster-internal hostnames

    messages_url_template uses RFC 6570 Level 1 URI Template syntax.
    Example: /runtime/agents-v2/agents/sessions/{session_id}/messages
    """

    agent_instance_id: str
    team_id: TeamId
    runtime_id: str
    execution_transport: Literal["sse"] = "sse"
    execute_url: str = Field(
        ..., description="Ingress-relative URL for non-streaming execution."
    )
    execute_stream_url: str = Field(
        ..., description="Ingress-relative URL for SSE streaming execution."
    )
    messages_url_template: str = Field(
        ...,
        description=(
            "RFC 6570 Level 1 URI Template for runtime history. "
            "Example: /runtime/agents-v2/agents/sessions/{session_id}/messages"
        ),
    )
    supports_streaming: bool = True
    supports_hitl: bool = True
    supports_ui_parts: bool = True
    effective_chat_options: EffectiveChatOptions = Field(
        default_factory=EffectiveChatOptions,
        description=(
            "Resolved chat-option surface derived from the stored managed-agent "
            "configuration. The frontend should render only the affordances "
            "enabled here rather than hard-code agent- or tool-specific rules."
        ),
    )
    runtime_display_name: str | None = None
    max_session_idle_seconds: int | None = None
    context_prompt_text: str | None = Field(
        default=None,
        description=(
            "Resolved text of the session's context prompt, if one is set. "
            "The runtime injects this as a conversation-level context. "
            "Null when no context prompt is configured for the session."
        ),
    )


class SessionListItem(BaseModel):
    """One session entry in the sidebar session list."""

    session_id: str
    team_id: TeamId
    agent_instance_id: str | None = None
    title: str | None = None
    context_prompt_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered prompt-library ids attached to this session as chat context "
            "(personal/team prompt UUIDs or 'default:{category}'). Empty when none "
            "are attached. Concatenated in order as conversation context at "
            "execution time."
        ),
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionAttachmentSummary(BaseModel):
    """Persisted conversation-level attachment metadata owned by control-plane."""

    attachment_id: str
    name: str
    mime: str | None = None
    size_bytes: int | None = None
    summary_md: str
    document_uid: str | None = None
    storage_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateSessionAttachmentRequest(BaseModel):
    """Payload used to persist one attachment after upload and fast-ingest."""

    attachment_id: str
    name: str
    mime: str | None = None
    size_bytes: int | None = None
    summary_md: str
    document_uid: str | None = None
    storage_key: str | None = None


class PromptSummary(BaseModel):
    """Small team-scoped prompt-library projection used for listings."""

    id: str
    name: str
    description: str | None = None
    category: PromptCategory | None = None
    emoji: str | None = None
    tags: list[str] = []
    text_preview: str | None = None
    is_default: bool = False
    created_by: str | None = None
    version: int = 1
    import_count: int = 0
    session_count: int = 0
    score: float | None = None
    avg_input_tokens: int | None = None
    avg_output_tokens: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PromptDetail(PromptSummary):
    """Full team-scoped prompt-library payload including prompt text."""

    team_id: TeamId
    text: str


class ContextPromptSummary(BaseModel):
    """One prompt entry in the chat-context picker (union of personal + team + defaults)."""

    id: str
    name: str
    description: str | None = None
    scope: Literal["personal", "team", "default"]
    category: PromptCategory | None = None
    version: int
    session_count: int
    score: float | None = None
    # Full prompt text — only populated for scope="default" so the frontend can
    # apply the text without a second API call (default IDs are synthetic, not DB rows).
    text: str | None = None


class PromptScoreUpdateRequest(BaseModel):
    """Request body for updating the quality score of one prompt."""

    score: float = Field(..., ge=0.0, le=5.0)


class PromptPromoteRequest(BaseModel):
    """Request body for promoting (copy-by-value) one prompt to another team."""

    target_team_id: str = Field(..., min_length=1)


class CreatePromptRequest(BaseModel):
    """Request body for creating one team-scoped prompt-library record."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    category: PromptCategory = Field(default=PromptCategory.OTHER)
    emoji: str | None = Field(default=None, max_length=8)
    tags: list[str] = Field(default_factory=list)
    text: str = Field(..., min_length=1)


class UpdatePromptRequest(BaseModel):
    """Request body for replacing one team-scoped prompt-library record."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    category: PromptCategory = Field(default=PromptCategory.OTHER)
    emoji: str | None = Field(default=None, max_length=8)
    tags: list[str] = Field(default_factory=list)
    text: str = Field(..., min_length=1)


class CreateSessionRequest(BaseModel):
    """Register session metadata in control-plane at session creation time."""

    session_id: str = Field(..., min_length=1, description="Frontend-generated UUID.")
    agent_instance_id: str | None = Field(default=None)
    title: str | None = Field(default=None, max_length=500)


class UpdateSessionRequest(BaseModel):
    """Update control-plane-owned session metadata.

    All fields are optional — send only what needs changing.
    Typical callers:
    - frontend after a completed turn: ``{ "updated_at": "<iso>" }``
    - user renames a session: ``{ "title": "My analysis" }``
    - user sets chat context: ``{ "context_prompt_ids": ["<id1>", "<id2>"] }``
    - user clears chat context: ``{ "context_prompt_ids": [] }``
    """

    updated_at: datetime | None = Field(
        default=None,
        description=(
            "Frontend-observed last activity timestamp. Used only for "
            "control-plane session metadata freshness, not runtime message history."
        ),
    )
    title: str | None = Field(
        default=None,
        max_length=500,
        description="Human-readable session title shown in the sidebar.",
    )
    context_prompt_ids: list[str] | None = Field(
        default=None,
        description=(
            "Full ordered replacement set of prompt-library ids to attach as chat "
            "context (personal/team prompt UUIDs or 'default:{category}'). The "
            "server diffs against the current set: removed ids are detached, new "
            "ids attached, order rewritten. An empty list clears the context. "
            "Omit the field entirely to leave the context unchanged (e.g. on a "
            "freshness-only PATCH); a present null is treated as a clear."
        ),
    )


class CreateAgentInstanceRequest(BaseModel):
    """Request body for enrolling a discovered template for a team."""

    template_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Composite template identity: '{source_runtime_id}:{source_agent_id}'. "
            "Obtained from GET /teams/{team_id}/agent-templates."
        ),
    )
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    tuning_field_values: dict[str, TuningValue] | None = Field(
        default=None,
        description=(
            "Optional initial values for the template's tunable fields. "
            "Keys must match ManagedAgentFieldSpec.key values from the template. "
            "Unknown keys are ignored. Known values are validated against the "
            "declared field type and constraints."
        ),
    )
    mcp_config_values: dict[str, dict[str, TuningValue]] | None = Field(
        default=None,
        description=(
            "Optional per-server MCP configuration values keyed first by "
            "server id and then by ManagedAgentFieldSpec.key. Only selected "
            "or inherited-active servers may be configured; unknown server ids "
            "or option keys are rejected with HTTP 422."
        ),
    )
    mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional MCP server activation policy for this instance. "
            "None means inherit the template default selection (all declared "
            "servers active); [] means activate no MCP servers; a non-empty "
            "list means activate exactly that subset. Unknown IDs are rejected "
            "with HTTP 422."
        ),
    )


class UpdateAgentInstanceRequest(BaseModel):
    """Request body for patching a managed agent instance's metadata and field values."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    status: Literal["enabled", "disabled"] | None = Field(
        default=None,
        description="Set to 'enabled' or 'disabled' to toggle the instance. None leaves the current status unchanged.",
    )
    tuning_field_values: dict[str, TuningValue] | None = Field(
        default=None,
        description=(
            "Replaces the stored field values for this instance. "
            "Keys must match ManagedAgentFieldSpec.key values frozen at enrollment. "
            "Unknown keys are ignored. Known values are validated against the "
            "declared field type and constraints. "
            "Omit the field to leave existing values unchanged; pass null to "
            "clear the stored agent tuning values."
        ),
    )
    mcp_config_values: dict[str, dict[str, TuningValue]] | None = Field(
        default=None,
        description=(
            "Replaces the stored per-server MCP configuration values. Omit the "
            "field to leave the current MCP config unchanged; pass null to "
            "clear all stored MCP config for the instance."
        ),
    )
    mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Replaces the MCP server activation policy for this instance. "
            "Omit the field to leave the current selection unchanged; pass "
            "null to reset to the template default selection (all declared "
            "servers active); pass [] to activate no MCP servers; pass a "
            "non-empty list to activate exactly that subset. Unknown IDs are "
            "rejected with HTTP 422."
        ),
    )


class ManagedAgentRuntimeBinding(BaseModel):
    """Internal control-plane mapping consumed by fred-runtime resolution flows."""

    agent_instance_id: str
    template_agent_id: str
    display_name: str
    owner_scope: Literal["team"] = "team"
    owner_user_id: str | None = None
    owner_team_id: TeamId
    enabled: bool = True
    tuning: ManagedAgentTuning
