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
Input and state models for the test assistant graph agent.

This agent needs no LLM — every branch is keyword-driven so developers
can exercise every SSE event type (status, assistant_delta, HITL choice,
HITL free-text, sources, error) from a running pod without configuring
a model provider.

Trigger keywords (case-insensitive prefix match):
  echo          → simple echo reply with status events
  hitl choice   → binary HITL confirmation gate (3 options)
  hitl text     → free-text HITL input gate
  trace         → status events + streamed analytical text + mock sources
  error         → node_error path to test UI error rendering
  long          → ~30 short sentences streamed word-by-word
  files         → unified /fs round-trip: write to the agent's space, read back, list
  (anything else) → fallback with scenario list
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TestInput(BaseModel):
    """User message that selects a test scenario."""

    message: str = Field(..., min_length=1)


class TestState(BaseModel):
    """Minimal workflow state — only what the dispatcher and scenario steps need."""

    latest_user_text: str

    # Written by dispatcher, read by scenario steps
    scenario: str = ""

    # Accumulated free-text HITL reply (written by hitl_text step)
    human_text_reply: str = ""

    # Mock sources written by trace_step; consumed by build_output override
    sources_data: list[dict[str, object]] = Field(default_factory=list)

    # LinkPart ui_parts written by files_step; consumed by build_output override
    link_parts: list[dict[str, object]] = Field(default_factory=list)

    # Terminal output
    final_text: str | None = None
    done_reason: str | None = None

    # Set by runtime on node errors
    node_error: str = ""
