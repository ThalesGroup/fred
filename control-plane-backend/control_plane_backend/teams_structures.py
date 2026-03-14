from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from fred_core import RelationType, TeamPermission
from fred_core.common import TeamId
from pydantic import BaseModel, Field

from control_plane_backend.users_structures import UserSummary


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


class TeamWithPermissions(Team):
    permissions: list[TeamPermission] = Field(default_factory=list)


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


class RemoveTeamMemberResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    team_id: str
    user_id: str
    sessions_enqueued: int
    scheduled_delete_at: datetime
    policy_mode: str
    retention_seconds: int
    matched_rule_id: str | None = None
