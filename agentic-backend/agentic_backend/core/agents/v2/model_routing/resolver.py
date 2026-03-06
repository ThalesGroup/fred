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

from dataclasses import dataclass

from .contracts import (
    MatchValue,
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One matching rule plus its deterministic tie-break metadata."""

    rule: ModelRouteRule
    order_index: int
    specificity: int


def _value_matches(expected: MatchValue | None, actual: str | None) -> bool:
    """Return True when one criterion value matches one request value."""

    if expected is None:
        return True
    if actual is None:
        return False
    if isinstance(expected, str):
        return actual == expected
    return actual in expected


def _rule_matches(match: ModelRouteMatch, request: ModelSelectionRequest) -> bool:
    """Return True when all non-null rule criteria match the request."""

    return (
        _value_matches(match.purpose, request.purpose)
        and _value_matches(match.agent_id, request.agent_id)
        and _value_matches(match.team_id, request.team_id)
        and _value_matches(match.user_id, request.user_id)
        and _value_matches(match.operation, request.operation)
    )


class ModelRoutingResolver:
    """
    Resolve one runtime model-selection query against a static policy.

    Practical reading:
    - Request comes from runtime context (`team_id`, `agent_id`, `operation`, ...)
    - Resolver chooses one `target_profile_id`
    - Provider/factory will later build the actual model client from it

    Rule precedence:
    1. Highest specificity (number of criteria in rule.match)
    2. First rule order in policy

    When is this called (current integration):
    - ReAct v2:
      - called through `RoutedChatModelFactory.select(...)`
      - typically once per phase in an execution (`routing`, `planning`)
        because runtime caches resolved models by operation for the current run
    - Graph v2:
      - currently called during runtime activation/model build
      - selected model is then reused by graph node executions
        (unless future runtime wiring introduces per-operation graph routing)
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
        - each model selection request (runtime-dependent frequency)

        Expected inputs / invariants:
        - `request.capability` is set
        - policy contains profile ids referenced by matching/default rules

        Return / side effects:
        - returns one `ModelSelection` (winner rule or capability default)
        - no side effects, no external I/O

        Precedence (real implementation):
        1. rule capability must equal request capability
        2. all defined match fields must match request
        3. highest specificity wins (`defined_criteria_count`)
        4. for equal specificity, first rule declared in catalog wins

        Fallback / errors:
        - no matching rule -> `_default_selection(...)`
        - no default profile for capability -> `ValueError`
        - unknown `target_profile_id`/default profile id -> `KeyError`

        Observability signals to look at:
        - resolver itself does not log
        - inspect provider/factory logs that include source/rule/profile metadata
        """

        candidates: list[_Candidate] = []
        for order_index, rule in enumerate(self._policy.rules):
            if rule.capability != request.capability:
                continue
            if _rule_matches(rule.match, request):
                candidates.append(
                    _Candidate(
                        rule=rule,
                        order_index=order_index,
                        specificity=rule.match.defined_criteria_count(),
                    )
                )

        if not candidates:
            return self._default_selection(capability=request.capability)

        winner = min(
            candidates,
            key=lambda candidate: (
                -candidate.specificity,
                candidate.order_index,
            ),
        )
        profile = self._profile(winner.rule.target_profile_id)
        return ModelSelection(
            source=ModelSelectionSource.RULE,
            capability=request.capability,
            profile_id=profile.profile_id,
            model=profile.model.model_copy(deep=True),
            rule_id=winner.rule.rule_id,
            matched_criteria=winner.specificity,
        )

    def _default_selection(self, *, capability: ModelCapability) -> ModelSelection:
        """Return capability default when no explicit rule matches."""

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
            rule_id=None,
            matched_criteria=0,
        )

    def _profile(self, profile_id: str) -> ModelProfile:
        """Read one profile by id from the pre-indexed catalog."""

        return self._profiles_by_id[profile_id]
