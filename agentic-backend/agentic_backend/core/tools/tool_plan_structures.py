# Copyright Thales 2025
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

# agentic_backend/core/tooling/tool_plan.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------
# Planner outputs
# -----------------------------


class CallToolPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["call_tool"] = "call_tool"

    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)

    # Explanation for audit / UI
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class AskClarificationPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ask_clarification"] = "ask_clarification"

    question: str
    expected_fields: List[str] = Field(default_factory=list)


class NoToolPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["no_tool"] = "no_tool"

    answer: str


ToolPlanV1 = Union[
    CallToolPlanV1,
    AskClarificationPlanV1,
    NoToolPlanV1,
]
