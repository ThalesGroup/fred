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
Capability HITL declarations (#1973, RFC §5.4).

Why this module exists:
- exactly ONE HITL gate exists per agent (`FredHitlMiddleware`); capabilities
  never ship interrupt middleware of their own — they DECLARE which of their
  tools pause for human approval, and the runtime merges those declarations
  into the platform gate alongside operator policy

How to use:
- return `HitlSpec`s from `AgentCapability.hitl_specs()`; the `when` predicate
  (if any) is evaluated at gate time with a `HitlGateRequest` carrying the
  tool call, the real tool object, and the capability's typed context
- fail-closed: a raising `when` predicate counts as "interrupt"; predicates
  must be pure and fast — anything needing I/O is its own middleware
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .context import CapabilityContext


@dataclass(frozen=True)
class HitlGateRequest:
    """
    What a `HitlSpec.when` predicate sees for one pending tool call (RFC §5.4).

    Fields:
    - `tool_call`: the model-emitted tool call (`name`, `args`, `id`), with
      filesystem argument rewrites already applied — predicates read the REAL
      arguments the tool would execute with
    - `tool`: the bound tool object, when the runtime can resolve it
    - `context`: the owning capability's typed `CapabilityContext`, so a gate
      condition can read instance config (e.g. "pause writes outside this
      agent's configured workspace root")
    """

    tool_call: Mapping[str, Any]
    tool: Any | None
    context: CapabilityContext[Any, Any]


class HitlSpec(BaseModel):
    """
    One capability tool's approval declaration (RFC §5.4).

    Semantics at the merged gate:
    - `require=True` always pauses the tool for approval
    - otherwise `when(request)` decides per call; a RAISING predicate counts
      as "interrupt" (fail-closed)
    - `question` overrides the default approval question verbatim (the
      capability owns its i18n); title/choices/wire shape stay frozen
    - `allowed_decisions` is forward-compat: the gate renders proceed/cancel
      today; richer decisions are a later, deliberate contract amendment
    """

    model_config = ConfigDict(frozen=True)

    tool: str = Field(min_length=1, description="Name of the gated tool.")
    require: bool = False
    when: Callable[[HitlGateRequest], bool] | None = None
    question: str | None = None
    allowed_decisions: tuple[str, ...] = ("proceed", "cancel")

    @field_validator("allowed_decisions")
    @classmethod
    def _non_empty_decisions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("allowed_decisions must not be empty.")
        return value
