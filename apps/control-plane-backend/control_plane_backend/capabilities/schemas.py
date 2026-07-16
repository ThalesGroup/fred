# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Admin capability-enablement API contract (CAPAB-01 / #1980, RFC §8.5)."""

from __future__ import annotations

from typing import Any

from fred_sdk.contracts.capability.manifest import TeamScopePolicy
from fred_sdk.contracts.models import FieldSpec
from pydantic import BaseModel, Field


class CapabilityEnablementItem(BaseModel):
    """One capability's admin-facing scope + enablement state (RFC §8.5)."""

    id: str
    name: str = Field(description="i18n key")
    version: str
    icon: str
    team_scope: TeamScopePolicy
    default_on: bool = Field(
        description="Whether the platform-wide default_on marker is set."
    )
    enabled_team_ids: list[str] = Field(
        default_factory=list,
        description="Teams carrying an explicit `enabled` grant.",
    )
    disabled_team_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Teams carrying an explicit `disabled` opt-out (the tri-state "
            "'disabled' position). For a default_on capability it also "
            "subtracts from the inherited roster."
        ),
    )
    total_team_count: int = Field(
        default=0,
        description=(
            "Platform-wide team count — the denominator for a default_on "
            "capability's inherited access. Counts every team in the org, not "
            "just the ones the calling admin belongs to."
        ),
    )
    team_settings_fields: list[FieldSpec] = Field(
        default_factory=list,
        description="The enable-with-settings form (rendered like config fields).",
    )


class CapabilityEnablementList(BaseModel):
    items: list[CapabilityEnablementItem] = Field(default_factory=list)


class EnableTeamCapabilityRequest(BaseModel):
    """Enable-with-settings payload; validated against team_settings_fields."""

    settings: dict[str, Any] = Field(default_factory=dict)


class SetCapabilityDefaultOnRequest(BaseModel):
    default_on: bool


class TeamCapabilityEnablementResult(BaseModel):
    capability_id: str
    team_id: str
    enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)
    suspended_instances: int = Field(
        default=0,
        description="Dependent agent instances suspended by this change (#1975).",
    )


class CapabilityDefaultOnResult(BaseModel):
    capability_id: str
    default_on: bool
    suspended_instances: int = 0
