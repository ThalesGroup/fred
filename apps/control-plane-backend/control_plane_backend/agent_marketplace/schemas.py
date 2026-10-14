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

from datetime import datetime

from fred_core.common import TeamId
from fred_sdk.contracts.models import TuningValue
from pydantic import BaseModel, ConfigDict, Field

from control_plane_backend.agent_instances.names import CopyLocale
from control_plane_backend.product.schemas import (
    AgentCopyResult,
    AgentCopyTarget,
)


class PublishAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(
        default=None,
        description=(
            "The entry version the card shows (`marketplace.version`); absent "
            "for a first publication. A mismatch answers 409."
        ),
    )


class UnpublishAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Free text shown to the team; accepted from a platform admin only.",
    )


class MarketplaceAgentCapability(BaseModel):
    """A capability of the snapshot, as i18n keys captured at publication."""

    id: str
    name: str
    description: str | None = None


class MarketplaceAgentFile(BaseModel):
    """A configuration file of the snapshot: metadata only, never its content."""

    capability_id: str
    filename: str
    size: int


class MarketplaceAgentSummary(BaseModel):
    entry_id: str
    team_id: TeamId
    team_name: str | None = Field(
        default=None, description="The publishing team's current name."
    )
    template_id: str
    display_name: str
    description: str | None = None
    role: str
    version: int
    first_published_at: datetime
    published_at: datetime = Field(description="Date of the current version.")
    like_count: int = 0
    import_count: int = 0
    liked_by_me: bool = False


class MarketplaceAgentDetail(MarketplaceAgentSummary):
    """Read-only "ID card" of a published snapshot."""

    agent_instance_id: str = Field(
        description="The published agent, addressed by a platform admin's removal."
    )
    likes_since_update: int = Field(
        default=0, description="Likes given on the current version."
    )
    usage_statement: str = ""
    tuning_field_values: dict[str, TuningValue] = Field(default_factory=dict)
    capabilities: list[MarketplaceAgentCapability] = Field(default_factory=list)
    files: list[MarketplaceAgentFile] = Field(default_factory=list)


class MarketplaceAgentImportTargetsResponse(BaseModel):
    """Destinations the caller can import into; the publishing team is excluded."""

    targets: list[AgentCopyTarget]


class MarketplaceAgentImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_team_ids: list[str] = Field(..., min_length=1)
    locale: CopyLocale | None = Field(
        default=None,
        description="Caller's UI language, picking the word of a renamed copy (`copie`/`copy`); English when absent.",
    )


class MarketplaceAgentImportResponse(BaseModel):
    results: list[AgentCopyResult]
