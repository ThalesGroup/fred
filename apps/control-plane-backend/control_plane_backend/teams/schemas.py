from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from fred_core import JoiningMode, RelationType, TeamPermission
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


class TeamAdminConstraintError(Exception):
    """Raised when an operation would leave a team with no team_admin."""

    def __init__(self, detail: str):
        super().__init__(detail)


class TeamMemberRoleNotHeldError(Exception):
    """AUTHZ-06 (RFC Part 7 §35): raised when revoking a role the member does
    not currently hold — nothing to revoke."""

    def __init__(self, team_id: TeamId, user_id: str, relation: UserTeamRelation):
        self.team_id = team_id
        self.user_id = user_id
        self.relation = relation
        super().__init__(
            f"User '{user_id}' does not hold '{relation.value}' on team "
            f"'{team_id}'; nothing to revoke."
        )


class TeamMemberLastRoleError(Exception):
    """AUTHZ-06 (RFC Part 7 §35): raised when revoking a role would leave the
    member with none. Revoking a role is a distinct, deliberately narrower
    action than removing a member — silently emptying someone's last role
    would be a removal in disguise. Use `remove_team_member` instead."""

    def __init__(self, team_id: TeamId, user_id: str, relation: UserTeamRelation):
        self.team_id = team_id
        self.user_id = user_id
        self.relation = relation
        super().__init__(
            f"'{relation.value}' is the only role user '{user_id}' holds on "
            f"team '{team_id}'; revoking it would silently remove them from "
            "the team. Use remove_team_member instead."
        )


class TeamAlreadyExistsError(Exception):
    """Raised when team creation collides with an existing `team_metadata.name`
    (no Keycloak group involved — teams are `team_metadata` rows)."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Team '{name}' already exists.")


class RetentionUpdateError(Exception):
    """Raised when a per-team retention update violates the platform cap.

    The team update surface maps this to HTTP 422 (`http_status`): a team may
    only *tighten* retention below the platform cap (RFC §3.B), so a value above
    the cap — or a value with no platform cap configured — is refused server-side.
    """

    http_status = 422

    def __init__(self, detail: str):
        super().__init__(detail)


class TeamNotOpenForJoiningError(Exception):
    """Raised by `POST /teams/{team_id}/join` (TEAM-09) when the team's
    `joining_mode` is not `OPEN`. Self-service join is the only membership
    write path that does not require the caller to already hold an
    administer-permission over the team, so this check happens server-side
    against the stored value — the client's belief about the mode is never
    trusted."""

    http_status = 403

    def __init__(self, team_id: TeamId, joining_mode: JoiningMode):
        self.team_id = team_id
        self.joining_mode = joining_mode
        super().__init__(
            f"Team '{team_id}' is not open for self-service joining "
            f"(joining_mode={joining_mode.value})."
        )


class TeamRescueNotOrphanedError(Exception):
    """Raised when rescue-admin is attempted on a team that still has a team_admin.

    AUTHZ-05 review item 9 (RFC Part 6 §32): this guard is the load-bearing
    safety property that makes `can_rescue_team_admin` structurally different
    from the `§24.7` escalation that was tried and reverted — mechanically
    inert against any team with an active admin, never a standing grant.
    """

    def __init__(self, team_id: TeamId, existing_admin_ids: set[str]):
        self.team_id = team_id
        self.existing_admin_ids = existing_admin_ids
        admins = ", ".join(sorted(existing_admin_ids))
        super().__init__(
            f"Team '{team_id}' already has team_admin(s) ({admins}); they must "
            "handle membership changes themselves — rescue only applies to a "
            "team with zero team_admin."
        )


class Team(BaseModel):
    id: TeamId
    name: str
    member_count: int | None = None
    admins: list[UserSummary] = Field(default_factory=list)
    is_member: bool = False
    description: str | None = None
    joining_mode: JoiningMode = JoiningMode.REQUEST_ONLY
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
    TEAM_ADMIN = RelationType.TEAM_ADMIN.value
    TEAM_EDITOR = RelationType.TEAM_EDITOR.value
    TEAM_ANALYST = RelationType.TEAM_ANALYST.value
    TEAM_MEMBER = RelationType.TEAM_MEMBER.value

    def to_relation(self) -> RelationType:
        return RelationType(self.value)


class TeamMember(BaseModel):
    type: Literal["user"] = "user"
    # AUTHZ-06 (RFC Part 7 §36): a member may hold more than one team role
    # simultaneously (e.g. team_admin + team_editor + team_analyst on a small
    # team) — this is the full set currently held, not a single "primary" role.
    relations: list[UserTeamRelation]
    user: UserSummary


class CreateTeamRequest(BaseModel):
    """Platform-admin-gated team bootstrap request (RFC §28).

    ``initial_team_admin_ids`` must name at least one Keycloak user `sub` —
    an adminless team cannot be created. The requesting platform admin
    receives no relation on the created team unless they name themselves.
    """

    name: str = Field(min_length=1, max_length=180)
    initial_team_admin_ids: list[str] = Field(min_length=1)


class RescueTeamAdminRequest(BaseModel):
    """AUTHZ-05 review item 9 (RFC §32): `POST /teams/{team_id}/rescue-admin`.

    Only succeeds when the team currently has zero `team_admin` — see
    `TeamRescueNotOrphanedError`.
    """

    user_id: str = Field(min_length=1)


class AddTeamMemberRequest(BaseModel):
    user_id: str
    relation: UserTeamRelation


class GrantTeamMemberRoleRequest(BaseModel):
    """AUTHZ-06 (RFC Part 7 §34): grants exactly one additional role to an
    existing member — never a bulk role-set replace. See
    `POST /teams/{team_id}/members/{user_id}/roles`."""

    relation: UserTeamRelation


class UpdateTeamRequest(BaseModel):
    description: str | None = Field(default=None, max_length=180)
    joining_mode: JoiningMode | None = None
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
