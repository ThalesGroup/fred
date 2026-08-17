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
Deterministic model-selection engine for v2 routing policies.

What this file does:
- takes one `ModelSelectionRequest`
- finds the best matching rule (or default profile)
- returns one `ModelSelection` (profile + model config + decision metadata)

What this file does NOT do:
- no model client construction
- no network calls
- no runtime side effects

This is the pure decision layer used by `RoutedChatModelFactory`.
"""

from __future__ import annotations

from .contracts import (
    ModelCapability,
    ModelProfile,
    ModelRoutingPolicy,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
)


class ModelRoutingResolver:
    """
    Resolve one runtime model-selection query against a static policy.

    Practical reading:
    - Request comes from runtime context (`capability`, `agent_id`)
    - Resolver chooses one `target_profile_id`: the policy's
      `agent_profile_overrides[agent_id]` when set and capability-compatible,
      else the capability default
    - Provider/factory will later build the actual model client from it

    When is this called (current integration):
    - ReAct/Deep v2: once per turn, at runtime activation
    - Graph v2: once per turn, at runtime activation — same call, same timing
    """

    def __init__(self, policy: ModelRoutingPolicy):
        self._policy = policy
        self._profiles_by_id = {
            profile.profile_id: profile for profile in policy.profiles
        }

    @property
    def policy(self) -> ModelRoutingPolicy:
        """Expose the immutable policy used by this resolver."""

        return self._policy

    def resolve(self, request: ModelSelectionRequest) -> ModelSelection:
        """
        Why this function exists:
        - implement one deterministic "request -> model profile" decision

        Who calls it:
        - `RoutedChatModelFactory.select(...)`
        - any future capability-specific routed factories

        When it is called:
        - once per turn (runtime-dependent frequency)

        Return / side effects:
        - returns one `ModelSelection` (agent override or capability default)
        - no side effects, no external I/O

        Fallback / errors:
        - no override for `request.agent_id`, or its profile's capability
          doesn't match -> `_default_selection(...)`
        - no default profile for capability -> `ValueError`
        """

        if request.agent_id is not None:
            profile_id = self._policy.agent_profile_overrides.get(request.agent_id)
            if profile_id is not None:
                profile = self._profile(profile_id)
                if profile.capability == request.capability:
                    return ModelSelection(
                        source=ModelSelectionSource.AGENT_OVERRIDE,
                        capability=request.capability,
                        profile_id=profile.profile_id,
                        model=profile.model.model_copy(deep=True),
                    )

        return self._default_selection(capability=request.capability)

    def _default_selection(self, *, capability: ModelCapability) -> ModelSelection:
        """Return capability default when no agent override applies."""

        default_profile_id = self._policy.default_profile_by_capability.get(capability)
        if default_profile_id is None:
            raise ValueError(
                f"No default profile configured for capability={capability.value!r}."
            )
        profile = self._profile(default_profile_id)
        return ModelSelection(
            source=ModelSelectionSource.DEFAULT,
            capability=capability,
            profile_id=profile.profile_id,
            model=profile.model.model_copy(deep=True),
        )

    def _profile(self, profile_id: str) -> ModelProfile:
        """Read one profile by id from the pre-indexed catalog."""

        return self._profiles_by_id[profile_id]

    def profile_or_none(self, profile_id: str) -> ModelProfile | None:
        """Public counterpart to `_profile` for callers outside this class that
        must not raise `KeyError` on an unknown id — e.g. `RoutedChatModelFactory`
        resolving a team-policy `target_profile_id` (drift rule), which needs to
        distinguish "unknown to this deployment" from a Python-internal error
        and raise its own typed `TeamRoutingProfileDriftError` instead."""

        return self._profiles_by_id.get(profile_id)


def resolve_team_override(
    *,
    agent_profile_overrides: dict[str, str] | None,
    chat_default_profile_id: str | None,
    agent_id: str | None,
) -> str | None:
    """
    Second, narrower resolution pass applied only when the static
    `models_catalog.yaml` `agent_profile_overrides` fell through to the
    capability default — never consulted otherwise, so a static override
    always wins over team policy.

    1. `agent_profile_overrides[agent_id]` if `agent_id` is set and present
    2. else `chat_default_profile_id` if set
    3. else `None` — caller keeps the static catalog default unchanged

    Pure function, no I/O, no side effects — easy to unit test in isolation
    from the resolver/provider wiring.
    """

    if agent_id is not None and agent_profile_overrides:
        profile_id = agent_profile_overrides.get(agent_id)
        if profile_id is not None:
            return profile_id
    return chat_default_profile_id
