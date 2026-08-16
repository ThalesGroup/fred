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
from typing import Literal

from fred_core.common import TeamId
from fred_sdk.contracts.context import ModelBinding
from pydantic import BaseModel, Field


class TeamRoutingPolicy(BaseModel):
    """One team's resolved routing policy.

    `GET` always returns this shape — an empty policy (`version=0`, both
    fields empty/None) when the team has never written one, resolving to
    runtime defaults, never a 404 ("GET returns the stored policy or an empty
    policy that resolves to runtime defaults").
    """

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None = None
    agent_profile_overrides: dict[str, str] = Field(default_factory=dict)


class UpdateTeamRoutingPolicyRequest(BaseModel):
    """`PATCH` body — a full typed replacement, no per-field patch semantics."""

    chat_default_profile_id: str | None = None
    agent_profile_overrides: dict[str, str] = Field(default_factory=dict)


class AvailableModelProfile(BaseModel):
    """One chat profile this team may reference from its routing policy.

    It is `can_use`-enabled and advertised by every model-capable pod; the
    server derives this set from declared capability, never the profile id.
    """

    profile_id: str
    capability_id: str
    name: str = Field(description="i18n key, same as CapabilityCatalogEntry.name")


class AvailableModelProfileList(BaseModel):
    profiles: list[AvailableModelProfile] = Field(default_factory=list)


class ProfileNotUsableError(Exception):
    """One or more profile ids in a routing-policy write are not `can_use`-enabled
    for this team (RFC §7.2) — the write-time counterpart of the runtime's
    fail-closed `ModelNotUsableError`. Names every offending profile id so the
    caller can fix all of them in one round trip instead of one-at-a-time."""

    def __init__(self, *, team_id: TeamId, profile_ids: list[str]) -> None:
        self.team_id = team_id
        self.profile_ids = profile_ids
        super().__init__(
            f"Team {team_id!r} may not use profile id(s) {profile_ids!r} — "
            "not enabled for this team."
        )


class UnknownProfileError(Exception):
    """A routing-policy write references an invalid chat profile.

    The id is unknown, non-chat, or absent from at least one enabled
    model-capable pod. These cases share one client contract: the profile is
    not selectable by the deployment-wide chat policy.
    """

    def __init__(self, *, profile_ids: list[str]) -> None:
        self.profile_ids = profile_ids
        super().__init__(f"Unknown profile id(s): {profile_ids!r}.")


class PlatformModelBinding(BaseModel):
    """The platform-wide `chat` model-binding admin state — chat-only;
    `language`/`embedding`/`image` have no production consumer and are not
    representable through this API.

    `GET/PUT/DELETE /admin/platform/model-bindings` always return this shape
    — `binding=None` means chat has no platform override and every pod
    resolves it locally as it always has. `model_capability` is a
    route-local constant, not the global `ModelCapability` enum: this API
    surface can only ever describe `chat`, so there is no vocabulary to
    reuse or duplicate.
    """

    model_capability: Literal["chat"] = "chat"
    binding: ModelBinding | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class SetPlatformModelBindingRequest(BaseModel):
    """`PUT` body — wraps `ModelBinding` (its own strict `settings` contract,
    `ModelBindingSettings`, rejects any credential-shaped or unknown key at
    request-parsing time, before the service layer even runs)."""

    binding: ModelBinding
