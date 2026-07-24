from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fred_core.common import TeamId
from fred_sdk.contracts.capability import CapabilityCatalogEntry, ChatControlDescriptor
from fred_sdk.contracts.models import TuningValue
from pydantic import BaseModel, Field

from control_plane_backend.agent_instances.suspension import SuspensionReason
from control_plane_backend.config.models import (
    FrontendFeatureFlags,
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
    UploadWarning,
)
from control_plane_backend.product.prompt_category import PromptCategory
from control_plane_backend.teams.schemas import Team, TeamWithPermissions
from control_plane_backend.users.schemas import UserSummary


class PermissionSummary(BaseModel):
    """Frontend-friendly permission projection for product bootstrap flows.

    AUTHZ-05 review item 11: this used to also carry `items` (a flattened
    `resource:action` list from `list_display_permissions()`, itself derived
    from Keycloak app roles) plus six always-`False` placeholder booleans
    (`can_view_team_agents`, `can_manage_team_agents`, `can_manage_mcp_servers`,
    `can_view_feedback`, `can_submit_feedback`, `can_create_sessions`). Both
    were dead: Keycloak app roles were removed platform-wide in item 8a, so
    `items` was permanently `[]` for every user, and the six booleans were
    never populated by anything. Org-scoped gating is exactly the two fields
    below; team-scoped gating goes through `TeamWithPermissions.permissions`
    (already OpenFGA-derived, see `teams/service.py::_get_team_permissions_for_user`)
    instead of a bespoke org-level flag per feature.
    """

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
    upload_warning: UploadWarning | None = Field(
        default=None,
        description=(
            "Deployer-configured banner for upload surfaces (document upload "
            "drawer, chat attachments), from `platform.frontend.upload_warning` "
            "(MIGR-01.01). `None` when the deployment configures none — the "
            "frontend then renders nothing. Deliberately on the authenticated "
            "bootstrap, not the pre-auth `FrontendConfig`: upload surfaces only "
            "render post-auth, and `FrontendConfig` stays minimal."
        ),
    )


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
    root_bootstrap_completed: bool = Field(
        ...,
        description=(
            "Whether POST /bootstrap/platform-admin (AUTHZ-07) has ever "
            "succeeded on this deployment. True once the durable "
            "PlatformBootstrapStore marker is set, permanently — never "
            "re-derived from live OpenFGA state, so removing every "
            "platform_admin relation later does not flip this back to False "
            "(same rationale as BootstrapAlreadyCompletedError). Not "
            "sensitive: it reveals only 'has anyone ever bootstrapped this "
            "instance', never who, never the secret, never any identity — "
            "safe on this public/unauthenticated surface, same as gcu_version."
        ),
    )
    root_bootstrap_required: bool = Field(
        ...,
        description=(
            "The authoritative frontend gating decision for BootstrapGuard — "
            "true only when `security.user.enabled AND security.rebac.enabled "
            "AND NOT root_bootstrap_completed`. Deliberately distinct from "
            "`root_bootstrap_completed`, which stays the truthful durable "
            "historical marker and is never reinterpreted: on deployments "
            "where user authentication or ReBAC is disabled, "
            "`root_bootstrap_completed` is still False on a fresh database "
            "even though `POST /bootstrap/platform-admin` deliberately "
            "refuses with 503 there, so the frontend must not treat "
            "'not completed' alone as 'must show the bootstrap page'. The "
            "frontend must gate on this field, not re-derive the ReBAC/auth "
            "predicate itself."
        ),
    )


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
    available_capabilities: list[CapabilityCatalogEntry] = Field(
        default_factory=list,
        description=(
            "Capabilities installed on this template's source pod (#1974/#1978, "
            "RFC AGENT-CAPABILITY §3.8), aggregated from the pod's manifest "
            "advertisement. MCP servers surface here as ordinary capabilities "
            "keyed by their plain catalog server id (#1988). Drives the one "
            "Tools tab in agent creation; config_fields render through the "
            "metadata-driven form."
        ),
    )


class ManagedAgentInstanceSummary(BaseModel):
    """Primary team-visible managed agent identity exposed to the frontend."""

    agent_instance_id: str
    team_id: TeamId
    template_id: str
    display_name: str
    description: str | None = None
    role: str = Field(
        description=(
            "Short one-line summary of what this agent does, distinct from "
            "the longer `description` — shown on the agent card so a "
            "teammate can recall the agent's purpose without reading the "
            "full description. Server-set to `display_name` at enrollment "
            "until independently edited (#2076)."
        ),
    )
    usage_statement: str = Field(
        default="",
        description=(
            "User-authored intended-use statement (purpose, target/impacted "
            "users, data handled, outputs, error impact) captured in the "
            "agent form's Engagement tab, used to screen for platform/"
            "organization risk (#2105). Empty for agents enrolled before "
            "#2105 until independently edited — required at creation and "
            "enforced by the agent edit form on save, but omittable on "
            "`UpdateAgentInstanceRequest` (like `role`) so partial updates "
            "such as the enable/disable toggle are unaffected."
        ),
    )
    status: Literal["enabled", "disabled"]
    suspension_reason: SuspensionReason | None = Field(
        default=None,
        description=(
            "Platform-forced suspension reason (#1975, RFC §3.9), or null when "
            "the instance is not suspended. Distinct from `status` (the "
            "editor's enable/disable toggle): a suspended instance is hidden "
            "from chat-only members and shows editors a warning with a locked "
            "enable toggle. One of capability_unavailable / "
            "capability_access_revoked / capability_config_invalid."
        ),
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = Field(
        default=None,
        description=(
            "Uid of the last user who edited the instance (#1952). "
            "Server-authoritative and read-only; null when the instance was "
            "never user-edited (seed/startup saves have no acting user)."
        ),
    )
    tuning_field_values: dict[str, TuningValue] = Field(
        default_factory=dict,
        description=(
            "Current user-set values for this instance's tunable fields. "
            "Keyed by ManagedAgentFieldSpec.key. Empty when no fields have been customised."
        ),
    )
    selected_capability_ids: list[str] | None = Field(
        default=None,
        description=(
            "Capability activation policy for this instance (#1974). Null "
            "means inherit the template default selection; [] means no "
            "capabilities; a non-empty list means exactly that set."
        ),
    )
    capability_config: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-capability stored config envelopes "
            "({'schema_version', 'config'}) keyed by capability id, as "
            "validated by the pod at save time. The edit form re-renders the "
            "capability's config_fields from the inner 'config' object."
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
    chat_controls: list[ChatControlDescriptor] = Field(
        default_factory=list,
        description=(
            "Computed chat-time composer controls for this instance (CAPAB-01 "
            "#1976, RFC §3.3/§3.7), evaluated per capability on the pod at "
            "session prep and flattened in capability-registration then "
            "returned-list order. Supersedes the retired `effective_chat_options`: "
            "the composer resolves each `widget` id against the owning "
            "capability's plugin registry (§9) and silently skips unknown ids. "
            "Never persisted — a cache-aside projection of stored config."
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
    capability_base_urls: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Ingress-relative base URL of each selected capability's auto-mounted "
            "router, keyed by capability id (AGENT-CAPABILITY-RFC §9.1, #1979). "
            "The instance-bound (in-session) counterpart of the template catalog's "
            "route_base_url: the frontend calls these pod routes directly (no "
            "proxy), with the same bearer it already uses for execution."
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
    role: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description=(
            "Optional short one-line summary of what this agent does. "
            "Defaults to `display_name` when omitted (#2076)."
        ),
    )
    usage_statement: str = Field(
        ...,
        min_length=1,
        description=(
            "Required intended-use statement (purpose, target/impacted users, "
            "data handled, outputs, error impact) — used to screen for "
            "platform/organization risk (#2105). Hard-required at creation, "
            "unlike the optional `role`."
        ),
    )
    tuning_field_values: dict[str, TuningValue] | None = Field(
        default=None,
        description=(
            "Optional initial values for the template's tunable fields. "
            "Keys must match ManagedAgentFieldSpec.key values from the template. "
            "Unknown keys are ignored. Known values are validated against the "
            "declared field type and constraints."
        ),
    )
    capability_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional capability activation policy (#1974). None means "
            "inherit the template default selection; [] means activate no "
            "capabilities; a non-empty list means activate exactly that set. "
            "IDs not advertised by the template's source pod are rejected "
            "with HTTP 422."
        ),
    )
    capability_config_values: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Optional per-capability configuration values keyed by capability "
            "id (the capability's config_fields values). Each selected "
            "capability's slice is round-tripped to the source pod for "
            "validation; the pod-returned stored envelope is persisted "
            "verbatim. Values for unselected capabilities are ignored."
        ),
    )


class UpdateAgentInstanceRequest(BaseModel):
    """Request body for patching a managed agent instance's metadata and field values."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    role: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description=(
            "Short one-line summary of what this agent does. Omit to leave "
            "the current role unchanged (#2076)."
        ),
    )
    usage_statement: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Intended-use statement (#2105). Omit to leave the current value "
            "unchanged — same convention as `role`, so partial updates like "
            "the enable/disable toggle (which PATCHes only `status`) are not "
            "forced to resupply it. The agent edit form always submits it "
            "(enforced client-side, same as `display_name`), so in practice "
            "every full-form save keeps this current, including for agents "
            "enrolled before #2105 whose stored value starts out empty."
        ),
    )
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
    capability_ids: list[str] | None = Field(
        default=None,
        description=(
            "Replaces the capability activation policy (#1974). Omit to leave "
            "the current selection unchanged; pass null to reset to the "
            "template default; pass [] to deactivate all capabilities; pass a "
            "non-empty list to activate exactly that set. IDs not advertised "
            "by the source pod are rejected with HTTP 422."
        ),
    )
    capability_config_values: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Replaces the per-capability configuration values (keyed by "
            "capability id). Omit to keep the stored configs; pass null to "
            "reset every selected capability to its defaults. Each selected "
            "capability's effective config is re-validated by the source pod "
            "and the returned stored envelope is persisted verbatim."
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
    # Per-team enablement settings resolved at session prep (CAPAB-01 / #1980,
    # RFC §8.2), keyed by capability id and restricted to the instance's
    # selected capabilities. The pod carries each slice to its capability as
    # `CapabilityContext.team_settings` — it never enters an LLM tool signature.
    team_capability_settings: dict[str, dict[str, Any]] = Field(default_factory=dict)
