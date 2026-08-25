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

"""
Model-routing contracts used by Fred v2 runtimes.

This file is intentionally "product-first": read it as a data contract for
"which model do we use for this call?".

Minimal mental model:

1. A `ModelProfile` is a named model configuration.
2. A `ModelRoutingPolicy` has a default profile per capability, plus an
   optional per-agent override.

Concrete scenario:

- Team-wide chat default: `default_profile_by_capability["chat"]` ->
  `chat.ollama.mistral`
- One agent needs a stronger model: `agent_profile_overrides["mindmap"]` ->
  `chat.azure_apim.gpt4o`
"""

from __future__ import annotations

from enum import Enum

from fred_core.common import ModelConfiguration
from fred_sdk.contracts.context import FrozenModel, ModelCapability
from pydantic import Field, model_validator

# `FrozenModel` and `ModelCapability` are canonically defined in
# `fred_sdk.contracts.context` (relocated there so control-plane, which
# depends on fred_sdk but not fred_runtime, can speak `ModelCapability` too).
# Imported and re-exported here unchanged so every existing
# `from .contracts import ModelCapability` / `from fred_runtime.model_routing
# import ModelCapability` caller keeps working without modification.


class ModelNotUsableError(RuntimeError):
    """Raised when a resolved profile's model is not `can_use`-authorized for
    the requesting team (OBSERV-02 v3, AGENT-CAPABILITY-RFC.md §8.7) — the
    fail-closed gate `RoutedChatModelFactory.build_for_chat` enforces against
    `BoundRuntimeContext.usable_model_ids`. Deliberately never substitutes a
    different model — an agent turn silently routed to a model the team never
    agreed to use would violate the whole point of admin-gated enablement.

    Propagates like any other resolver/provider exception from
    `build_for_chat` (see that method's docstring) — the runtime's generic
    turn-level exception handling surfaces it as an `execution_error` event,
    never a raw crash.
    """

    def __init__(self, *, capability_id: str, provider: str, name: str) -> None:
        self.capability_id = capability_id
        self.provider = provider
        self.name = name
        super().__init__(
            f"Model {provider}/{name} ({capability_id!r}) is not enabled for this team."
        )


class TeamRoutingProfileDriftError(RuntimeError):
    """Raised when a team policy profile is absent or has the wrong capability.

    Deliberately never falls back to another profile: control-plane and this
    pod's catalog have drifted, and silently picking a different model would
    hide the invalid stored policy.
    """

    def __init__(
        self,
        *,
        profile_id: str,
        expected_capability: ModelCapability | None = None,
        actual_capability: ModelCapability | None = None,
    ) -> None:
        self.profile_id = profile_id
        self.expected_capability = expected_capability
        self.actual_capability = actual_capability
        if expected_capability is not None and actual_capability is not None:
            super().__init__(
                f"Team routing policy references profile {profile_id!r} with "
                f"capability {actual_capability.value!r}; expected "
                f"{expected_capability.value!r}."
            )
            return
        super().__init__(
            f"Team routing policy references profile {profile_id!r}, which is not "
            "in this runtime deployment's model catalog."
        )


# Provider-passthrough keys inside `ModelConfiguration.settings` that turn
# reasoning ON at the client (`MODEL-REASONING-ENABLEMENT-RFC.md` REASON-01).
# One list, two consumers that must never disagree: `ModelProfile`'s boot
# validator (§4.3 — declaring one of these without `supports_thinking` is an
# authoring mistake) and `without_reasoning_settings` below, which removes
# them when the platform toggle is off (§5.6.2). Adding a provider's key here
# extends both at once; there is deliberately no second place to update.
REASONING_SETTING_KEYS: frozenset[str] = frozenset({"reasoning_effort"})


def without_reasoning_settings(model: ModelConfiguration) -> ModelConfiguration:
    """Return `model` with every `REASONING_SETTING_KEYS` entry removed from
    `settings` (`MODEL-REASONING-ENABLEMENT-RFC.md` §5.6.2).

    Why removal and not "decline to add": `reasoning_effort` is already in the
    YAML-authored settings by the time anything sees it, so a toggle that only
    skips *adding* it would be decorative — the model would reason with the
    toggle off. That exact failure is on record in-tree for `allow_parallel_calls`
    (`AGENT-THINKING-API-RFC.md` §C.8, "Never reaches the model").

    Returns the SAME object when there is nothing to strip. This runs on the
    model-build path, and the overwhelmingly common case is a profile with no
    reasoning setting at all — no copy, no allocation for it.
    """

    settings = model.settings
    if not settings or REASONING_SETTING_KEYS.isdisjoint(settings):
        return model
    return model.model_copy(
        update={
            "settings": {
                key: value
                for key, value in settings.items()
                if key not in REASONING_SETTING_KEYS
            }
        }
    )


class ModelProfile(FrozenModel):
    """
    Named model configuration.

    `profile_id` is the stable identifier referenced by rules and UI payloads.

    Think of a profile as "one deployable model setup", for example:
    - `chat.ollama.mistral`
    - `default.chat.openai.prod`
    - `chat.azure_apim.gpt4o`
    """

    profile_id: str = Field(..., min_length=1)
    capability: ModelCapability
    model: ModelConfiguration
    description: str | None = None
    model_display_name: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Human-readable model name for the UI. Absent means the frontend "
            "derives one by splitting `model.name` — a heuristic that cannot "
            "tell a version separator from a variant one ('claude-sonnet-4-6' "
            "renders 'Claude Sonnet 4 6'). Display only. Declared per profile, "
            "but describes the model: siblings sharing one (provider, name) "
            "should agree, and the catalog projection takes the first declared."
        ),
    )
    supports_thinking: bool = Field(
        default=False,
        description=(
            "Declared APTITUDE — does this profile's model support Thinking "
            "(`MODEL-REASONING-ENABLEMENT-RFC.md` §4, level 1)? Not activation: "
            "`supports_thinking: true` with no reasoning setting is legal and "
            "means 'capable, shipped off'. Declared per profile, not per model, "
            "because that is where the behaviour actually differs — the same "
            "(provider, name) can be declared twice, reasoning in one profile "
            "and not the other. Whether reasoning actually RUNS is level 2's "
            "platform toggle (§5), delivered per model on "
            "`RuntimeContext.reasoning_enabled_model_ids`."
        ),
    )

    @model_validator(mode="after")
    def validate_model(self) -> "ModelProfile":
        if not self.model.provider or not self.model.provider.strip():
            raise ValueError(
                f"ModelProfile {self.profile_id!r} must define model.provider."
            )
        if not self.model.name or not self.model.name.strip():
            raise ValueError(
                f"ModelProfile {self.profile_id!r} must define model.name."
            )
        # §4.3 — fail loud at pod boot rather than tolerate the inconsistency.
        # A profile that ships a reasoning setting while denying the aptitude
        # is always an authoring mistake, and silently tolerating it is exactly
        # how the current untyped-passthrough situation arose: nothing in Fred
        # would know the profile reasons, so the admin toggle (§5.3) would
        # never appear for it and its reasoning could never be turned off.
        declared = sorted(REASONING_SETTING_KEYS & set(self.model.settings or {}))
        if declared and not self.supports_thinking:
            raise ValueError(
                f"ModelProfile {self.profile_id!r} declares reasoning setting(s) "
                f"{declared} but supports_thinking is false. Set "
                "'supports_thinking: true' on the profile (it declares the model's "
                "aptitude), or remove the setting."
            )
        return self


class ModelRoutingPolicy(FrozenModel):
    """
    Complete routing policy.

    Contains:
    - `default_profile_by_capability`: fallback profile per capability
    - `profiles`: known profile definitions
    - `agent_profile_overrides`: optional `agent_id -> profile_id` override,
      the ops-level escape hatch equivalent of a team's own routing policy
      (`RuntimeContext.agent_profile_overrides`). An override only applies
      when it exists for the requested `agent_id` and the referenced
      profile's capability matches the request; otherwise resolution falls
      through to the capability default.
    """

    default_profile_by_capability: dict[ModelCapability, str]
    profiles: tuple[ModelProfile, ...]
    agent_profile_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "ModelRoutingPolicy":
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("ModelRoutingPolicy.profiles must have unique profile_id.")
        known = set(profile_ids)
        for capability, profile_id in self.default_profile_by_capability.items():
            if profile_id not in known:
                raise ValueError(
                    f"default profile for capability={capability.value!r} points to unknown profile_id={profile_id!r}."
                )
            profile = next(
                profile for profile in self.profiles if profile.profile_id == profile_id
            )
            if profile.capability != capability:
                raise ValueError(
                    f"default profile {profile_id!r} has capability={profile.capability.value!r}, "
                    f"expected capability={capability.value!r}."
                )
        for agent_id, profile_id in self.agent_profile_overrides.items():
            if not agent_id.strip():
                raise ValueError(
                    "ModelRoutingPolicy.agent_profile_overrides keys must be "
                    "non-empty agent ids."
                )
            if profile_id not in known:
                raise ValueError(
                    f"agent_profile_overrides[{agent_id!r}] targets unknown "
                    f"profile_id={profile_id!r}."
                )
        return self


class ModelSelectionRequest(FrozenModel):
    """
    Runtime input passed to the resolver for one model call.

    This is emitted by runtimes per invocation with contextual dimensions:
    `capability`, `agent_id`. `team_id` is deliberately not a matching
    dimension here — the static `agent_profile_overrides` policy is
    deployment-wide, not per-team; per-team routing is the separate
    `resolve_team_override` pass (`RuntimeContext.agent_profile_overrides`).
    """

    capability: ModelCapability
    agent_id: str | None = None


class ModelSelectionSource(str, Enum):
    """Where the final selection came from."""

    DEFAULT = "default"
    AGENT_OVERRIDE = "agent_override"
    TEAM_POLICY = "team_policy"
    PLATFORM_BINDING = "platform_binding"


class ModelSelection(FrozenModel):
    """Resolver decision with audit metadata."""

    source: ModelSelectionSource
    capability: ModelCapability
    profile_id: str
    model: ModelConfiguration
