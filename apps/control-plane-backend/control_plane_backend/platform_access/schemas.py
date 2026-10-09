# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Literal
from uuid import UUID

from fred_pod.security.platform_access import PlatformAccessPolicy
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)


class PlatformAccessState(BaseModel):
    filtering_enabled: bool
    t0_completed_at: datetime | None
    policy: PlatformAccessPolicy | None
    revision: int
    has_admission_sources: bool


class SetPlatformFiltering(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filtering_enabled: bool
    expected_revision: int | None = Field(default=None, ge=0)


class AdmissionSource(BaseModel):
    kind: Literal["attribute", "manual", "t0", "team", "free"]
    team_id: str | None = None
    team_name: str | None = None
    granted_by: str | None = None
    granted_at: datetime | None = None


class PlatformAccessUser(BaseModel):
    user_id: str
    username: str | None
    email: str | None
    first_name: str | None = None
    last_name: str | None = None
    sources: list[AdmissionSource]


class PlatformAccessUsersPage(BaseModel):
    items: list[PlatformAccessUser]
    total: int


class PlatformAccessActivationUser(PlatformAccessUser):
    outcome: Literal["allowed", "blocked", "unknown"]


class PlatformAccessActivationPreview(BaseModel):
    users: list[PlatformAccessActivationUser]
    allowed: int
    blocked: int
    unknown: int
    revision: int
    checked_at: datetime


class PlatformAccessTeam(BaseModel):
    team_id: str
    name: str | None
    allowed: bool
    free: bool


class SetPlatformAccessTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    free: bool


class PlatformEnrollmentLink(BaseModel):
    token: str


class CreatePlatformEnrollmentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=512)
    expires_at: AwareDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value: datetime | None) -> datetime | None:
        from datetime import timezone

        if value is not None and value <= datetime.now(timezone.utc):
            raise ValueError("Expiration must be in the future")
        return value


PlatformEnrollmentLinkStatus = Literal["active", "suspended", "expired", "revoked"]


class PlatformEnrollmentLinkInfo(BaseModel):
    id: UUID
    note: str | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    status: PlatformEnrollmentLinkStatus
    opening_count: int
    last_opened_at: datetime | None
    recoverable: bool


class PlatformEnrollmentLinksPage(BaseModel):
    items: list[PlatformEnrollmentLinkInfo]
    total: int
    inactive_count: int


class DeletedPlatformEnrollmentLinks(BaseModel):
    deleted_count: int


class PlatformT0Preview(BaseModel):
    candidates: int
    matching: int
    completed_at: datetime | None


class PlatformAccessStatus(BaseModel):
    admitted: bool
    cgu_required: bool


class FreeEnrollmentPreview(BaseModel):
    team_name: str
    cgu_required: bool


class AcceptFreeEnrollmentCgu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=64)


class SetPlatformAccessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    policy: PlatformAccessPolicy


class PlatformAccessOwnClaims(BaseModel):
    claims: dict[str, JsonValue]
    selectable_paths: list[list[str]]
    truncated: bool


class PlatformAccessPolicyPreview(BaseModel):
    matched: bool
    admitted: bool
    conditions: list[
        Literal[
            "matched",
            "not_matching",
            "missing",
            "incompatible",
            "timeout",
            "unavailable",
        ]
    ]


class GrantPlatformAccessUsers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[UUID] = Field(min_length=1)
