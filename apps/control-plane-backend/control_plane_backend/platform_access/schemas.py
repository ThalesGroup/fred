# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Literal
from uuid import UUID

from fred_pod.security.platform_access import PlatformAccessPolicy
from pydantic import BaseModel, ConfigDict, Field


class PlatformAccessState(BaseModel):
    filtering_enabled: bool
    t0_completed_at: datetime | None
    policy: PlatformAccessPolicy | None
    revision: int


class SetPlatformFiltering(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filtering_enabled: bool


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
    sources: list[AdmissionSource]


class PlatformAccessUsersPage(BaseModel):
    items: list[PlatformAccessUser]
    total: int


class PlatformAccessTeam(BaseModel):
    team_id: str
    name: str | None
    allowed: bool
    free: bool
    has_enrollment_link: bool


class SetPlatformAccessTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    free: bool


class PlatformEnrollmentLink(BaseModel):
    token: str


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


class PlatformAccessClaim(BaseModel):
    path: list[str]
    types: list[Literal["string", "string_array"]]


class PlatformAccessPolicyPreview(BaseModel):
    matched: bool
    admitted: bool
    conditions: list[
        Literal["matched", "not_matching", "missing", "incompatible", "timeout"]
    ]


class GrantPlatformAccessUsers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[UUID] = Field(min_length=1, max_length=100)
