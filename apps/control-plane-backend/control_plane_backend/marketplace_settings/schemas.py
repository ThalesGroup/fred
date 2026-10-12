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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fred_core.common import TeamId
from pydantic import BaseModel, ConfigDict, Field


class AgentsMarketplaceDefault(BaseModel):
    """The default every team without an override follows."""

    agents_publishing_enabled: bool
    agents_publish_quota: int
    updated_by: str | None = None
    updated_at: datetime | None = Field(
        default=None, description="Null while the built-in defaults apply."
    )


class TeamMarketplaceSettings(BaseModel):
    """One team's overrides, the values that apply, and its marketplace counts."""

    team_id: TeamId
    team_name: str
    agents_publishing_enabled_override: bool | None = Field(
        default=None, description="Null when the team follows the default."
    )
    agents_publish_quota_override: int | None = Field(
        default=None, description="Null when the team follows the default."
    )
    agents_publishing_enabled: bool
    agents_publish_quota: int
    published_count: int


class MarketplaceSettings(BaseModel):
    default: AgentsMarketplaceDefault
    teams: list[TeamMarketplaceSettings]


class MarketplaceSettingsImpact(BaseModel):
    """What a change turning effective switches off removes, summed over teams."""

    affected_team_ids: list[TeamId] = Field(default_factory=list)
    removed_published_agents: int = 0


class MarketplaceSettingsUpdateResult(BaseModel):
    settings: MarketplaceSettings
    impact: MarketplaceSettingsImpact


class SetAgentsMarketplaceDefaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents_publishing_enabled: bool
    agents_publish_quota: int = Field(ge=1)


class SetTeamMarketplaceSettingsRequest(BaseModel):
    """Replaces both overrides; null puts that setting back to Default."""

    model_config = ConfigDict(extra="forbid")

    agents_publishing_enabled: bool | None
    agents_publish_quota: int | None = Field(ge=1)


class TeamMarketplaceView(BaseModel):
    """The team's effective agents marketplace settings and counts, on `TeamWithPermissions`."""

    agents_publishing_enabled: bool
    agents_publish_quota: int
    published_count: int


@dataclass(frozen=True)
class EffectiveMarketplaceSettings:
    agents_publishing_enabled: bool
    agents_publish_quota: int
