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
2. A `ModelRouteRule` says "when criteria match, use `target_profile_id`".
3. A `ModelRoutingPolicy` contains defaults + profiles + ordered rules.

Concrete scenario (team-a, R1/R2 ReAct, G1 Graph):

- Team-wide ReAct routing:
  `team_id=team-a`, `purpose=chat`, `operation=routing`
  -> `chat.ollama.mistral`
- Team-wide ReAct planning:
  `team_id=team-a`, `purpose=chat`, `operation=planning`
  -> `default.chat.openai.prod`
- Graph G1 specific JSON validation:
  `team_id=team-a`, `agent_id=internal.graph.g1`,
  `purpose=chat`, `operation=json_validation_fc`
  -> `chat.azure_apim.gpt4o`
"""

from __future__ import annotations

from enum import Enum
from typing import TypeAlias

from fred_core import ModelConfiguration
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    """Strict immutable base model for routing contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


# One criterion can be a single exact value or a tuple of allowed values.
MatchValue: TypeAlias = str | tuple[str, ...]


def _validate_match_value(*, field_name: str, value: MatchValue | None) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(
                f"ModelRouteMatch.{field_name} must be a non-empty string when provided."
            )
        return
    if not value:
        raise ValueError(
            f"ModelRouteMatch.{field_name} must not be an empty tuple when provided."
        )
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"ModelRouteMatch.{field_name} tuple items must be non-empty strings."
            )


class ModelRouteMatch(FrozenModel):
    """
    Match criteria for one routing rule.

    Semantics:
    - any field left as `None` means wildcard ("any")
    - all provided fields are combined with logical AND
    - tuple values mean "one-of"

    Typical examples:
    - team-wide ReAct routing:
      `team_id="team-a", purpose="chat", operation="routing"`
    - one specific Graph operation:
      `team_id="team-a", agent_id="internal.graph.g1",
      purpose="chat", operation="json_validation_fc"`
    """

    purpose: MatchValue | None = None
    agent_id: MatchValue | None = None
    team_id: MatchValue | None = None
    user_id: MatchValue | None = None
    operation: MatchValue | None = None

    def defined_criteria_count(self) -> int:
        return sum(
            1
            for value in (
                self.purpose,
                self.agent_id,
                self.team_id,
                self.user_id,
                self.operation,
            )
            if value is not None
        )

    @model_validator(mode="after")
    def validate_match_values(self) -> "ModelRouteMatch":
        _validate_match_value(field_name="purpose", value=self.purpose)
        _validate_match_value(field_name="agent_id", value=self.agent_id)
        _validate_match_value(field_name="team_id", value=self.team_id)
        _validate_match_value(field_name="user_id", value=self.user_id)
        _validate_match_value(field_name="operation", value=self.operation)
        return self


class ModelCapability(str, Enum):
    """
    Capability = technical model family.

    Use this to express what type of model client is required:
    chat, language, embedding, or image.
    """

    CHAT = "chat"
    LANGUAGE = "language"
    EMBEDDING = "embedding"
    IMAGE = "image"


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
        return self


class ModelRouteRule(FrozenModel):
    """
    One routing decision rule.

    Reads as:
    "If rule criteria apply and `capability` matches, then use
    `target_profile_id`."

    Supported catalog formats:
    - Preferred flat format:
      `operation` (required) + optional criteria (`purpose`, `agent_id`,
      `team_id`, `user_id`) at rule root.
    - Legacy format:
      `match: { ... }` block.

    Transition behavior:
    - both formats are accepted;
    - when both are present, criteria are merged and conflicting values fail
      fast.

    Notes:
    - `rule_id` is only a stable technical identifier.
    - Catch-all rules are not allowed here. Global fallback belongs to
      `default_profile_by_capability` in `ModelRoutingPolicy`.
    """

    rule_id: str = Field(..., min_length=1)
    capability: ModelCapability
    target_profile_id: str = Field(..., min_length=1)
    purpose: MatchValue | None = None
    agent_id: MatchValue | None = None
    team_id: MatchValue | None = None
    user_id: MatchValue | None = None
    operation: MatchValue | None = None
    match: ModelRouteMatch = Field(default_factory=ModelRouteMatch)

    @model_validator(mode="before")
    @classmethod
    def normalize_rule_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        criteria_fields = ("purpose", "agent_id", "team_id", "user_id", "operation")
        merged_criteria: dict[str, MatchValue] = {}

        for field_name in criteria_fields:
            field_value = payload.get(field_name)
            if field_value is not None:
                merged_criteria[field_name] = field_value

        match_value = payload.get("match")
        if isinstance(match_value, ModelRouteMatch):
            match_payload = match_value.model_dump(exclude_none=True)
        elif isinstance(match_value, dict):
            match_payload = {
                field_name: field_value
                for field_name, field_value in match_value.items()
                if field_value is not None
            }
        elif match_value is None:
            match_payload = {}
        else:
            # Let Pydantic emit the type validation error for malformed `match`.
            return payload

        for field_name in criteria_fields:
            if field_name not in match_payload:
                continue
            existing = merged_criteria.get(field_name)
            incoming = match_payload[field_name]
            if existing is not None and existing != incoming:
                raise ValueError(
                    f"ModelRouteRule has conflicting values for '{field_name}' between root and match."
                )
            merged_criteria[field_name] = incoming

        # Flat-shape guardrail: once criteria are provided at rule root, operation
        # must be explicit to avoid broad rules that are hard to reason about.
        root_criteria_present = any(
            payload.get(name) is not None for name in criteria_fields
        )
        if root_criteria_present and merged_criteria.get("operation") is None:
            raise ValueError(
                "ModelRouteRule flat format requires 'operation' at rule root."
            )

        if merged_criteria:
            payload["match"] = merged_criteria
            for field_name in criteria_fields:
                payload[field_name] = merged_criteria.get(field_name)

        return payload

    @model_validator(mode="after")
    def validate_non_empty_match(self) -> "ModelRouteRule":
        if self.match.defined_criteria_count() == 0:
            raise ValueError(
                f"ModelRouteRule {self.rule_id!r} has no criteria. "
                "Use default_profile_id for catch-all behavior."
            )
        return self


class ModelRoutingPolicy(FrozenModel):
    """
    Complete routing policy.

    Contains:
    - `default_profile_by_capability`: fallback profile per capability
    - `profiles`: known profile definitions
    - `rules`: ordered explicit overrides

    Rule resolution order (see resolver):
    1. most specific match (more defined criteria)
    2. first declared rule in `rules` when specificity is tied
    """

    default_profile_by_capability: dict[ModelCapability, str]
    profiles: tuple[ModelProfile, ...]
    rules: tuple[ModelRouteRule, ...] = ()

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
        for rule in self.rules:
            if rule.target_profile_id not in known:
                raise ValueError(
                    f"Rule {rule.rule_id!r} targets unknown profile_id={rule.target_profile_id!r}."
                )
            profile = next(
                profile
                for profile in self.profiles
                if profile.profile_id == rule.target_profile_id
            )
            if profile.capability != rule.capability:
                raise ValueError(
                    f"Rule {rule.rule_id!r} capability={rule.capability.value!r} targets "
                    f"profile capability={profile.capability.value!r}."
                )
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("ModelRoutingPolicy.rules must have unique rule_id.")
        return self


class ModelSelectionRequest(FrozenModel):
    """
    Runtime input passed to the resolver for one model call.

    This is emitted by runtimes per invocation with contextual dimensions:
    `capability`, `purpose`, `agent_id`, `team_id`, `user_id`, `operation`.
    """

    capability: ModelCapability
    purpose: str = Field(..., min_length=1)
    agent_id: str | None = None
    team_id: str | None = None
    user_id: str | None = None
    operation: str | None = None


class ModelSelectionSource(str, Enum):
    """Where the final selection came from."""

    DEFAULT = "default"
    RULE = "rule"


class ModelSelection(FrozenModel):
    """
    Resolver decision with audit metadata.

    `matched_criteria` is useful in traces/debugging to understand why one rule
    won against others.
    """

    source: ModelSelectionSource
    capability: ModelCapability
    profile_id: str
    model: ModelConfiguration
    rule_id: str | None = None
    matched_criteria: int = Field(default=0, ge=0)
