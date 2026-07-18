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

from typing import Any, Literal

from fred_sdk.contracts.capability.manifest import TeamScopePolicy
from fred_sdk.contracts.models import FieldSpec
from pydantic import BaseModel, Field

PersonalScope = Literal["enabled", "disabled", "default"]


class ImpactedInstanceSummary(BaseModel):
    """One agent instance affected by a capability change (admin drill-down)."""

    agent_instance_id: str
    team_id: str
    display_name: str


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
    total_personal_space_count: int = Field(
        default=0,
        description=(
            "Platform-wide personal-space count (= realm user count; one "
            "personal space per user) — the denominator for personal-class "
            "access (RFC §8.4), as total_team_count is for default_on."
        ),
    )
    personal_scope: PersonalScope = Field(
        default="default",
        description=(
            "Personal-space class position (RFC §8.4): `enabled` = usable by all "
            "personal spaces (`personal_on` tuple present); `disabled` = blocked "
            "for all personal spaces (`personal_disabled` present); `default` = "
            "neither, personal spaces follow `default_on` like any team."
        ),
    )
    team_settings_fields: list[FieldSpec] = Field(
        default_factory=list,
        description="The enable-with-settings form (rendered like config fields).",
    )
    kind: Literal["tool", "agent"] = Field(
        default="tool",
        description=(
            '"tool": a pod-advertised capability. "agent": a control-plane'
            "-side projection of an agent template into this same catalog"
            " (CAPAB-01, RFC §8.6) — every team's access to every agent is an"
            " explicit admin grant, exactly like a tool."
        ),
    )
    suspended_instances: int = Field(
        default=0,
        description=(
            "Agent instances this capability breaks AT REST, across every team "
            "(#1975 health). DERIVED per request — `suspension_reason` records "
            "why an instance is suspended, never which capability did it, so an "
            "instance broken by capa1 while also selecting capa2 must not count "
            "against capa2. An instance is counted when it selects this "
            "capability AND its team lacks `can_use` on it OR its pod no longer "
            "advertises it."
        ),
    )
    health_unknown_instances: int = Field(
        default=0,
        description=(
            "Instances selecting this capability whose runtime pod was "
            "unreachable, so their health is UNKNOWN rather than broken. Kept "
            "separate from `suspended_instances`: the reconciliation sweep skips "
            "an unreachable pod rather than suspending on a transient outage "
            "(#1975, RFC §3.9), and this count reports the same way."
        ),
    )
    suspended_instance_details: list[ImpactedInstanceSummary] = Field(
        default_factory=list,
        description=(
            "The agents behind `suspended_instances`, named for the health-column "
            "drill-down (which agents, in which team). Same derivation as the "
            "count — one entry per (instance, this capability) the instance is "
            "broken by at rest. Empty for a healthy capability; carries `team_id` "
            "so the admin surface can group by team."
        ),
    )


class CapabilityEnablementList(BaseModel):
    items: list[CapabilityEnablementItem] = Field(default_factory=list)


class EnableTeamCapabilityRequest(BaseModel):
    """Enable-with-settings payload; validated against team_settings_fields."""

    settings: dict[str, Any] = Field(default_factory=dict)


class SetCapabilityDefaultOnRequest(BaseModel):
    default_on: bool


class SetCapabilityPersonalScopeRequest(BaseModel):
    """Set the personal-space class tri-state for a capability (RFC §8.4)."""

    scope: PersonalScope


class TeamCapabilityEnablementResult(BaseModel):
    capability_id: str
    team_id: str
    enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)
    suspended_instances: int = Field(
        default=0,
        description="Dependent agent instances suspended by this change (#1975).",
    )
    revived_instances: int = Field(
        default=0,
        description=(
            "Dependent agent instances whose suspension this GRANT cleared "
            "(#1975). Only availability suspensions are cleared; an instance "
            "still missing another capability stays suspended, and a "
            "`capability_config_invalid` one is never touched here (RFC §3.9)."
        ),
    )


class CapabilityDefaultOnResult(BaseModel):
    capability_id: str
    default_on: bool
    suspended_instances: int = 0
    revived_instances: int = Field(
        default=0,
        description="Dependent instances revived by turning default-on ON (#1975).",
    )


class CapabilityPersonalScopeResult(BaseModel):
    capability_id: str
    scope: PersonalScope
    suspended_instances: int = Field(
        default=0,
        description=(
            "Dependent PERSONAL-space instances suspended by this change (#1975)."
        ),
    )


class CapabilityImpactPreview(BaseModel):
    """What a pending revoke WOULD break — the pre-disable dialog (#1975)."""

    capability_id: str
    suspended_instances: int = Field(
        default=0,
        description=(
            "Agents that work today and would be suspended by this change. "
            "Excludes agents already broken by this capability — revoking it "
            "again does not newly break them."
        ),
    )
    health_unknown_instances: int = Field(
        default=0,
        description="Selecting instances whose pod is unreachable (impact unknown).",
    )
    instances: list[ImpactedInstanceSummary] = Field(
        default_factory=list,
        description="The affected agents, for the admin drill-down.",
    )
