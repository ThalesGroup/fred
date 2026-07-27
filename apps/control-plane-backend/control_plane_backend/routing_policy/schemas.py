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

from fred_core.common import TeamId
from fred_sdk.contracts.context import TeamOperationRouteRule
from pydantic import BaseModel, Field


class TeamRoutingPolicy(BaseModel):
    """One team's resolved routing policy (`TEAM-ROUTING-POLICY-RFC.md` §3).

    `GET` always returns this shape — an empty policy (`version=0`, both
    fields empty/None) when the team has never written one, resolving to
    runtime defaults, never a 404 (RFC §10 "GET returns the stored policy or
    an empty policy that resolves to runtime defaults").
    """

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None = None
    operation_rules: list[TeamOperationRouteRule] = Field(default_factory=list)


class UpdateTeamRoutingPolicyRequest(BaseModel):
    """`PATCH` body — a full typed replacement, no per-field patch semantics
    (RFC §10)."""

    chat_default_profile_id: str | None = None
    operation_rules: list[TeamOperationRouteRule] = Field(default_factory=list)


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
    """A routing-policy write references a `target_profile_id` this deployment's
    aggregated model catalog has never advertised (typo, or a profile that
    exists in one pod's YAML but not the one(s) actually reachable)."""

    def __init__(self, *, profile_ids: list[str]) -> None:
        self.profile_ids = profile_ids
        super().__init__(f"Unknown profile id(s): {profile_ids!r}.")


class DuplicateOperationRuleError(Exception):
    """Two operation rules in the same write share an (operation, purpose) pair
    (RFC §3.2 invariant) — the resolver has no defined tie-break for that, so
    reject rather than silently pick one."""

    def __init__(self, *, operation: str, purpose: str | None) -> None:
        self.operation = operation
        self.purpose = purpose
        super().__init__(
            f"Duplicate operation rule for (operation={operation!r}, purpose={purpose!r})."
        )
