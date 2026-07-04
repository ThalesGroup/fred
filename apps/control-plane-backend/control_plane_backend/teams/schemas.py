from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from fred_core import RelationType, TeamPermission
from fred_core.common import TeamId
from pydantic import BaseModel, Field, field_validator

from control_plane_backend.scheduler.policies.policy_models import (
    _validate_optional_duration,
)
from control_plane_backend.users.schemas import UserSummary


class TeamNotFoundError(Exception):
    """Raised when a team is not found."""

    def __init__(self, team_id: TeamId):
        self.team_id = team_id
        super().__init__(f"Team with id '{team_id}' not found")


class BannerUploadError(Exception):
    """Raised when banner upload validation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class KeycloakM2MDisabledError(Exception):
    """Raised when Keycloak M2M client is disabled for team operations."""

    def __init__(self):
        super().__init__("Keycloak M2M is disabled; cannot perform team operations.")


class TeamMembershipSyncError(Exception):
    """Raised when Control Plane cannot synchronize a team membership in Keycloak."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(detail)


class TeamOwnerConstraintError(Exception):
    """Raised when an operation would leave a team with no owner."""

    def __init__(self, detail: str):
        super().__init__(detail)


class RetentionUpdateError(Exception):
    """Raised when a per-team retention update violates the platform cap.

    The team update surface maps this to HTTP 422 (`http_status`): a team may
    only *tighten* retention below the platform cap (RFC §3.B), so a value above
    the cap — or a value with no platform cap configured — is refused server-side.
    """

    http_status = 422

    def __init__(self, detail: str):
        super().__init__(detail)


class KeycloakGroupSummary(BaseModel):
    id: TeamId
    name: str | None
    member_count: int


class Team(BaseModel):
    id: TeamId
    name: str
    member_count: int | None = None
    owners: list[UserSummary] = Field(default_factory=list)
    is_member: bool = False
    description: str | None = None
    is_private: bool = True
    banner_image_url: str | None = None
    max_resources_storage_size: int | None = None
    current_resources_storage_size: int | None = None


class RetentionFieldView(BaseModel):
    """Resolved view of one governed retention field for one team (CTRLP-12).

    Maps one-to-one from the retention resolver's ``FieldRetentionResolution``:
    - ``platform_max``: the platform cap (read-only; ``None`` = no cap configured)
    - ``team_value``: the team's stored value (``None`` = team set nothing)
    - ``effective``: the value that actually applies (one of the two originals)
    - ``source``: ``"team"`` when the team value applies, else ``"platform"``
    - ``would_exceed``: ``True`` only when the team asked for more than the cap
    """

    platform_max: str | None = None
    team_value: str | None = None
    effective: str | None = None
    source: Literal["platform", "team"]
    would_exceed: bool = False


class TeamRetentionView(BaseModel):
    """Resolved retention view for one team across both governed fields.

    Embedded on ``TeamWithPermissions`` (GET ``/teams/{id}``) for the settings
    "Data & Retention" tab: the platform cap is shown read-only beside the
    per-team value. Resolution (clamp to cap, "platform caps, team may only
    tighten") lives in the retention resolver, never here.
    """

    team_delete_grace: RetentionFieldView
    max_idle: RetentionFieldView


class TeamWithPermissions(Team):
    permissions: list[TeamPermission] = Field(default_factory=list)
    # CTRLP-12 (RFC §3.B): resolved per-team retention (platform cap vs team
    # value). None for system/personal teams, which have no team-editable
    # retention (personal deletes use the platform `personal_delete_grace`).
    retention: TeamRetentionView | None = None


class UserTeamRelation(str, Enum):
    OWNER = RelationType.OWNER.value
    MANAGER = RelationType.MANAGER.value
    MEMBER = RelationType.MEMBER.value

    def to_relation(self) -> RelationType:
        return RelationType(self.value)


class TeamMember(BaseModel):
    type: Literal["user"] = "user"
    relation: UserTeamRelation
    user: UserSummary


class AddTeamMemberRequest(BaseModel):
    user_id: str
    relation: UserTeamRelation


class UpdateTeamMemberRequest(BaseModel):
    relation: UserTeamRelation


class UpdateTeamRequest(BaseModel):
    description: str | None = Field(default=None, max_length=180)
    is_private: bool | None = None
    banner_image_url: str | None = Field(default=None, max_length=300)
    # CTRLP-12 (RFC §3.B): per-team retention, patched through the team surface.
    # Partial semantics (exclude_unset): an omitted field keeps its current
    # stored value, an explicit ``null`` clears it (re-inherit the platform cap).
    # ISO-8601 durations validated here; the cap check ("team may only tighten")
    # is enforced server-side in `update_team` (422 via `RetentionUpdateError`).
    team_delete_grace: str | None = Field(default=None, min_length=1)
    max_idle: str | None = Field(default=None, min_length=1)

    @field_validator("team_delete_grace", "max_idle")
    @classmethod
    def _validate_optional_durations(cls, value: str | None) -> str | None:
        return _validate_optional_duration(value)


class RemoveTeamMemberResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    team_id: str
    user_id: str
    sessions_enqueued: int
    scheduled_delete_at: datetime
    policy_mode: str
    retention_seconds: int
    matched_rule_id: str | None = None
