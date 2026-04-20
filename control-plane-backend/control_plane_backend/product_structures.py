from __future__ import annotations

from datetime import datetime
from typing import Literal

from fred_core.common import TeamId
from fred_sdk.contracts.execution import ExecutionGrant
from pydantic import BaseModel, Field

from control_plane_backend.common.structures import (
    FrontendFeatureFlags,
    FrontendUiSettings,
    ManagedAgentTuning,
)
from control_plane_backend.teams_structures import Team, TeamWithPermissions
from control_plane_backend.users_structures import UserSummary


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


class ManagedAgentRuntimeBinding(BaseModel):
    """Internal control-plane mapping consumed by fred-runtime resolution flows."""

    agent_instance_id: str
    template_agent_id: str
    owner_scope: Literal["team"] = "team"
    owner_user_id: str | None = None
    owner_team_id: TeamId
    enabled: bool = True
    tuning: ManagedAgentTuning
