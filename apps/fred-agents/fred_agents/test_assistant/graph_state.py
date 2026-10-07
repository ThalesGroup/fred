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

Every branch is keyword-driven so developers can exercise every SSE event type
(status, assistant_delta, HITL choice, HITL free-text, sources, error) from a
running pod. Model-backed branches (model, assist) fall back to fixed text when
no model is bound; tests bind `mock_llm.MockChatModel`.

Trigger keywords (case-insensitive prefix match):
  echo          → simple echo reply with status events
  hitl confirm  → two-option confirmation
  hitl choice   → four-option question with descriptions
  hitl text     → free-text HITL input gate
  hitl comment  → choice with optional text comment
  trace         → status events + streamed analytical text + mock sources
  error         → node_error path to test UI error rendering
  long          → ~30 short sentences streamed word-by-word
  geo           → renders a sample GeoJSON FeatureCollection as a GeoPart ui_part
  document      → search via the document_access capability's tool
                  (context.invoke_runtime_tool), then a HITL confirm/discard
                  gate on the top hit — degrades to a helpful message when the
                  capability isn't selected on this agent instance
  assist        → a real agent's shape: structured routing, knowledge search,
                  streamed model draft, then one HITL review gate
  delegate      → invoke another agent (this one) through invoke_agent
  crash         → a node error with no on_error route (turn-level failure)
  (anything else) → fallback with scenario list
"""

from __future__ import annotations

from fred_sdk.contracts.context import ConversationalState
from pydantic import BaseModel, Field

# Also the delegate scenario's target: the agent invokes itself one turn deeper.
TEST_ASSISTANT_AGENT_ID = "fred.github.test_assistant"


class TestInput(BaseModel):
    """User message that selects a test scenario."""

    __test__ = False  # a domain model, not a pytest test class

    message: str = Field(..., min_length=1)


class TestState(ConversationalState, BaseModel):
    """Workflow state; `conversation_history` is the only field kept across turns."""

    __test__ = False  # a domain model, not a pytest test class

    latest_user_text: str

    # Written by dispatcher, read by scenario steps
    scenario: str = ""

    # assist scenario: routing decision, retrieved hits, streamed draft
    assist_intent: str = ""
    assist_hits: list[dict[str, object]] = Field(default_factory=list)
    assist_draft: str = ""

    # Accumulated free-text HITL reply (written by hitl_text step)
    human_text_reply: str = ""

    # Sources written by trace_step (mock) or document_step (real capability
    # hit, only on confirm); consumed by build_output override
    sources_data: list[dict[str, object]] = Field(default_factory=list)

    # GeoPart ui_parts written by geo_step; consumed by build_output override
    geo_parts: list[dict[str, object]] = Field(default_factory=list)

    # Terminal output
    final_text: str | None = None
    done_reason: str | None = None

    # Set by runtime on node errors
    node_error: str = ""
