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


class AvailableModelProfile(BaseModel):
    """One `can_use`-enabled model profile this team may reference from its
    routing policy — the option set for the `chat_default_profile_id` /
    `target_profile_id` picker (`TEAM-ROUTING-POLICY-RFC.md` §13, #2167)."""

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
    """A routing-policy write references a `target_profile_id` this
    deployment does not serve uniformly: either no pod has ever advertised
    it (typo), or only some pods have — a profile must be present on every
    enabled, model-capable pod to be deployment-global (RFC §9), or it can
    drift-fail at runtime on whichever pod actually lacks it
    (2026-08-02, MDL#2)."""

    def __init__(self, *, profile_ids: list[str]) -> None:
        self.profile_ids = profile_ids
        super().__init__(f"Unknown profile id(s): {profile_ids!r}.")


class DuplicateOperationRuleError(Exception):
    """Two rules in the same write share an (operation, purpose, agent_id) triplet
    (RFC §3.2 invariant) — the resolver has no defined tie-break for that, so
    reject rather than silently pick one."""

    def __init__(
        self, *, operation: str | None, purpose: str | None, agent_id: str | None = None
    ) -> None:
        self.operation = operation
        self.purpose = purpose
        self.agent_id = agent_id
        super().__init__(
            f"Duplicate rule for (operation={operation!r}, purpose={purpose!r}, agent_id={agent_id!r})."
        )


class DuplicateRuleIdError(Exception):
    """Two rules in the same write share a `rule_id` — always a client bug
    (rule_id is a client-generated stable key, never user-authored), never a
    legitimate routing intent. Reported separately from
    `DuplicateOperationRuleError` so the message names the actual offending
    id instead of a misleading (None, None, None) triplet."""

    def __init__(self, *, rule_id: str) -> None:
        self.rule_id = rule_id
        super().__init__(f"Duplicate rule_id {rule_id!r} in the same write.")


class AmbiguousOperationRuleError(Exception):
    """Two rules in the same write could both match the same request with
    equal specificity (RFC §3.2 resolution is "fixed, deterministic, no
    scoring") — e.g. one rule pinning (operation, agent_id) and another
    pinning (purpose, agent_id) for the same agent_id. The resolver breaks
    such ties by declaration order, which this UI never surfaces to an
    admin, so reject the write instead of leaving an outcome that depends on
    storage order."""

    def __init__(self, *, rule_id_a: str, rule_id_b: str) -> None:
        self.rule_id_a = rule_id_a
        self.rule_id_b = rule_id_b
        super().__init__(
            f"Rules {rule_id_a!r} and {rule_id_b!r} can both match the same request "
            "with equal specificity — remove or narrow one so resolution stays deterministic."
        )
