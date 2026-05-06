from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fred_core.common import TeamId
from fred_sdk.contracts.execution import ExecutionGrant
from pydantic import BaseModel, Field

from control_plane_backend.config.models import (
    FrontendFeatureFlags,
    FrontendUiSettings,
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
    ManagedMcpServerRef,
)
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


class FrontendBootstrap(BaseModel):
    """Small frontend bootstrap payload owned by control-plane."""

    current_user: UserSummary
    active_team: TeamWithPermissions
    available_teams: list[Team] = Field(default_factory=list)
    gcu_version: str | None = None
    feature_flags: FrontendFeatureFlags
    ui_settings: FrontendUiSettings
    permissions: PermissionSummary


class AgentTemplateSummary(BaseModel):
    """Catalog summary for one instantiable managed-agent template."""

    template_id: str
    source_runtime_id: str
    source_agent_id: str
    display_name: str
    description: str
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
    tuning_field_values: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Current user-set values for this instance's tunable fields. "
            "Keyed by ManagedAgentFieldSpec.key. Empty when no fields have been customised."
        ),
    )
    selected_mcp_server_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Admin-chosen MCP server IDs active for this instance. "
            "Empty list means all servers declared by the template are active."
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
    execution_grant: ExecutionGrant
    supports_streaming: bool = True
    supports_hitl: bool = True
    supports_ui_parts: bool = True
    expires_at: datetime
    runtime_display_name: str | None = None
    grant_refresh_required: bool = False
    max_session_idle_seconds: int | None = None


class SessionListItem(BaseModel):
    """One session entry in the sidebar session list."""

    session_id: str
    team_id: TeamId
    agent_instance_id: str | None = None
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    tuning_field_values: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional initial values for the template's tunable fields. "
            "Keys must match ManagedAgentFieldSpec.key values from the template. "
            "Unknown keys are ignored. Known values are validated against the "
            "declared field type and constraints."
        ),
    )
    mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional subset of MCP server IDs to activate for this instance. "
            "None means all servers declared by the template are active. "
            "Unknown IDs are rejected with HTTP 422."
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
    tuning_field_values: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Replaces the stored field values for this instance. "
            "Keys must match ManagedAgentFieldSpec.key values frozen at enrollment. "
            "Unknown keys are ignored. Known values are validated against the "
            "declared field type and constraints. "
            "Pass null to leave existing values unchanged."
        ),
    )
    mcp_server_ids: list[str] | None = Field(
        default=None,
        description=(
            "Replaces the active MCP server selection for this instance. "
            "None means leave the existing selection unchanged. "
            "Unknown IDs (not in the instance's declared mcp_servers) are rejected with 422."
        ),
    )


class ManagedAgentRuntimeBinding(BaseModel):
    """Internal control-plane mapping consumed by fred-runtime resolution flows."""

    agent_instance_id: str
    template_agent_id: str
    owner_scope: Literal["team"] = "team"
    owner_user_id: str | None = None
    owner_team_id: TeamId
    enabled: bool = True
    tuning: ManagedAgentTuning
