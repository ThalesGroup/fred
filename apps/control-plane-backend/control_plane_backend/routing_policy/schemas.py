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
    """One team's resolved model settings.

    `GET` always returns this shape — an empty policy (`version=0`, nothing
    set) when the team has never written one, resolving to runtime defaults,
    never a 404. Disabled and reasoning-off models are stored as exceptions,
    so a model the platform newly allows arrives enabled with reasoning on.
    """

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None = None
    disabled_model_ids: list[str] = Field(
        default_factory=list,
        description="Model capability ids the team disabled for its members.",
    )
    reasoning_default_off_model_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Model capability ids whose composer reasoning row starts OFF. "
            "Every other reasoning-enabled model starts ON."
        ),
    )


class UpdateTeamRoutingPolicyRequest(BaseModel):
    """`PATCH` body — a full typed replacement, no per-field patch semantics.

    Ids the team can no longer use are pruned on write. Newly disabled models
    clear the team's agent recommendations naming them, in the same write.
    """

    chat_default_profile_id: str | None = None
    disabled_model_ids: list[str] = Field(default_factory=list)
    reasoning_default_off_model_ids: list[str] = Field(default_factory=list)
    expected_version: int | None = Field(
        default=None,
        description=(
            "The `version` the client last read (0 before any write). When "
            "set and the stored version differs, the write is refused with "
            "409 so a concurrent edit is not overwritten."
        ),
    )


class AvailableModelProfile(BaseModel):
    """One chat profile this team may reference from its routing policy.

    It is `can_use`-enabled and advertised by every model-capable pod; the
    server derives this set from declared capability, never the profile id.
    """

    profile_id: str
    capability_id: str
    name: str = Field(description="i18n key, same as CapabilityCatalogEntry.name")
    display_name: str | None = Field(
        default=None,
        description="Ops-authored model display name, when the pod catalog has one.",
    )
    reasoning_available: bool = Field(
        default=False,
        description=(
            "Whether a platform admin enabled reasoning for this model: only "
            "then can the team set a reasoning default for it."
        ),
    )


class AvailableModelProfileList(BaseModel):
    profiles: list[AvailableModelProfile] = Field(default_factory=list)
    effective_default_profile_id: str | None = Field(
        default=None,
        description=(
            "The profile shown as the team's Default: the stored team default, "
            "else the pod default of the team's pods when they agree. Its "
            "model cannot be disabled."
        ),
    )


class DisableImpactAgent(BaseModel):
    agent_instance_id: str
    display_name: str


class DisableImpact(BaseModel):
    """Agents whose recommendation names a model about to be disabled; they
    will follow the team default once it is."""

    agents: list[DisableImpactAgent] = Field(default_factory=list)


class SelectableChatModel(BaseModel):
    """One model a member may pick for a conversation with an agent."""

    profile_id: str = Field(description="Choice key sent as `chat_profile_id`.")
    capability_id: str
    name: str
    display_name: str | None = None
    reasoning_enabled: bool = Field(
        default=False, description="Reasoning enabled platform-wide for this model."
    )
    reasoning_default_on: bool = Field(
        default=False,
        description="The team's starting reasoning state for this model.",
    )


class EffectiveChatModel(BaseModel):
    """The concrete model a chat turn with one agent instance will actually use
    (#2387), resolved for one team.

    Why this exists as its own read: the composer used to label itself with the
    single model whose *reasoning* an admin had enabled platform-wide, which is
    unrelated to routing — so it contradicted any platform binding or override
    in force and read as "model routing is broken". This is the answer to the
    question the composer actually needs to ask.

    Deliberately NOT part of `ExecutionPreparation`: that runs on every send and
    is contractually free of pod-catalog fetches, while resolving the two
    pod-owned precedence levels requires the pod's `/agents/models-catalog`.
    This read is per chat-page open instead, the same cost profile as
    `available-models` next to it.

    Scoped to what the composer renders. It deliberately does NOT report which
    precedence level won or which profile id it came from: that describes the
    POLICY, which only an elevated team role may read (#2167), and no surface
    displays it. Adding it would mean either leaking the policy to a plain
    member or gating a field nobody reads. `[V2][MODEL_ROUTING]` in the pod log
    remains the place to see the deciding level.

    Every model field is `None` together, meaning nothing resolved at all — a
    pod declaring no chat default with no team policy, or (during a rolling
    upgrade) a pod not yet advertising its defaults. The composer shows no model
    rather than guessing one.
    """

    name: str | None = Field(
        default=None,
        description=(
            "The concrete model name. `capability_id` below identifies the "
            "`(provider, name)` pair uniquely for a caller that needs to join "
            "against team enablement or the models admin view."
        ),
    )
    display_name: str | None = Field(
        default=None,
        description=(
            "The ops-authored `model_display_name` for this model, when the pod "
            "catalog names one. `None` leaves the frontend on its name/id "
            "prettifying fallback — the same fallback the composer already had."
        ),
    )
    capability_id: str | None = Field(
        default=None,
        description=(
            'The `(provider, name)`-keyed `kind="model"` capability id, so the '
            "caller can join this against team enablement and the models admin "
            "view. `None` for an unresolved model."
        ),
    )
    enabled_for_team: bool = Field(
        default=True,
        description=(
            "False when the resolved model is not `can_use`-enabled for this "
            "team, in which case the turn fails before the LLM call "
            "(`ModelNotUsableError`). Reported rather than hidden so the "
            "composer can say WHY a turn will fail instead of letting the user "
            "discover an opaque error — the same diagnosability rule REASON-01 "
            "§8 applies to the reasoning control. Always True for a platform "
            "binding, which bypasses team enablement by design: the operator is "
            "the authority on what is reachable."
        ),
    )
    reasoning_enabled: bool = Field(
        default=False,
        description=(
            "Whether reasoning actually runs on THIS model — i.e. whether a "
            "platform admin switched its reasoning on (REASON-01 §5). The "
            "composer must not offer the reasoning toggle when this is False: "
            "`RoutedChatModelFactory` STRIPS the reasoning settings for a model "
            "absent from `reasoning_enabled_model_ids` (§5.6.2), so the toggle "
            "would be inert and the turn would silently not reason.\n\n"
            "Needed because the reasoning control is emitted from the PLATFORM "
            "list — 'some model has reasoning on' — while routing may land on a "
            "different model entirely. With reasoning enabled on Mistral Small "
            "and a team override routing to Mistral Medium, the composer used to "
            "render 'Mistral Medium · Élevé' and offer the toggle while the pod "
            "ran no reasoning at all."
        ),
    )

    selectable_models: list[SelectableChatModel] = Field(
        default_factory=list,
        description=(
            "Models a member may pick for this agent: chat models served by "
            "the instance's pod, `can_use` for the team and not team-disabled. "
            "Empty when the choice is locked or the pod is unreachable."
        ),
    )
    choice_locked: bool = Field(
        default=False,
        description=(
            "True when a platform binding or a pod per-agent override fixes "
            "the model, so no choice is offered."
        ),
    )


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


class ModelDisabledForTeamError(Exception):
    """A write names a profile whose model the team disabled: the team default,
    or an agent's recommendation. Mapped to 422."""

    def __init__(self, *, team_id: TeamId, profile_ids: list[str]) -> None:
        self.team_id = team_id
        self.profile_ids = profile_ids
        super().__init__(
            f"Profile id(s) {profile_ids!r} name a model team {team_id!r} disabled."
        )


class DefaultModelNotDisableableError(Exception):
    """The team's default model, explicit or effective, cannot be disabled."""

    def __init__(self, *, capability_ids: list[str]) -> None:
        self.capability_ids = capability_ids
        super().__init__(
            f"Model(s) {capability_ids!r} are the team default and cannot be disabled."
        )


class ModelCatalogUnavailableError(Exception):
    """A pod serving the team could not be read while a write disables models,
    so the default it protects and the recommendations it clears are unknown.
    Mapped to 503: retry once the pod is back."""

    def __init__(self, *, runtime_ids: list[str]) -> None:
        self.runtime_ids = runtime_ids
        super().__init__(
            f"Model catalog of runtime(s) {runtime_ids!r} is unreachable; models "
            "cannot be disabled until it is back. Try again shortly."
        )


class RoutingPolicyVersionConflictError(Exception):
    """The policy changed since the client read it. Mapped to 409."""

    def __init__(self, *, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"The team's model settings changed (version {actual}, expected "
            f"{expected}). Reload and try again."
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
