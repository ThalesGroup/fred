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
Graph definition for the test assistant agent.

Purpose:
- Provide a no-LLM, no-MCP graph agent that exercises every major SSE event
  type so developers can validate the chat UI without any external services.

Workflow overview (keyword-routed by dispatch_step):

    dispatch
     ├─ echo        ──► echo_step        ──► finalize
     ├─ model_probe ──► model_probe_step ──► finalize
     ├─ hitl_choice ──► hitl_choice_step ──► finalize
     ├─ hitl_text   ──► hitl_text_step   ──► finalize
     ├─ trace       ──► trace_step       ──► finalize
     ├─ error       ──► error_step  (raises) → finalize (via on_error)
     ├─ long        ──► long_step         ──► finalize
     └─ fallback    ──► fallback_step     ──► finalize

No model provider is needed. No MCP servers are required.
The agent can run in any fred-agents pod that has fred_sdk installed.
"""

from __future__ import annotations

from fred_core.store import VectorSearchHit
from fred_sdk import FieldSpec, GraphAgent, GraphWorkflow, UIHints
from fred_sdk.graph.runtime import GraphExecutionOutput
from pydantic import BaseModel

from .graph_state import TestInput, TestState
from .graph_steps import (
    dispatch_step,
    echo_step,
    error_step,
    fallback_step,
    finalize_step,
    hitl_choice_step,
    hitl_text_step,
    long_step,
    model_probe_step,
    trace_step,
)


class TestAssistantGraphAgent(GraphAgent):
    """
    No-LLM-by-default test agent that exercises all major SSE event types.

    Use this agent when you need to:
    - validate chat UI rendering without a model provider
    - test HITL flows (binary choice and free-text)
    - test source panel rendering with mock VectorSearchHit data
    - test error / node_error SSE event rendering
    - test long streaming reply layout (word-by-word via emit_assistant_delta)
    - optionally validate graph operation-aware model routing when a model is configured

    Send a message starting with one of the scenario keywords to trigger
    the corresponding workflow branch. Send anything else to see the help menu.
    """

    agent_id: str = "fred.test.assistant"
    role: str = "Test Assistant (no LLM)"
    description: str = (
        "A no-LLM-by-default, no-MCP graph agent for UI testing. "
        "Exercises status events, HITL choice, HITL free-text, "
        "streaming text via assistant_delta, mock sources, node errors, "
        "long streaming replies, and an optional model-routing probe. "
        "Keyword-prefix routing: echo | model routing | model planning | "
        "hitl choice | hitl text | trace | error | long."
    )
    tags: tuple[str, ...] = ("test", "graph", "hitl", "streaming", "no-llm", "dev")

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Role instructions shown back in every scenario reply to confirm "
                "the value was applied end-to-end."
            ),
            required=True,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.planning",
            type="prompt",
            title="Planning step instructions",
            description=(
                "Optional instructions injected into the dispatch-step status "
                "message, proving per-step prompt injection works."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True),
        ),
        FieldSpec(
            key="prompts.routing",
            type="prompt",
            title="Routing/model probe instructions",
            description=(
                "Optional instructions injected into the optional model-probe "
                "scenario when validating operation-aware model routing."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True),
        ),
        FieldSpec(
            key="settings.verbose",
            type="boolean",
            title="Verbose mode",
            description=(
                "When enabled, every scenario reply appends a debug footer "
                "showing the active scenario name."
            ),
            default=False,
            ui=UIHints(group="Settings"),
        ),
        FieldSpec(
            key="settings.delay_ms",
            type="integer",
            title="Step delay (ms)",
            description=(
                "Extra milliseconds added to each asyncio.sleep() call. "
                "Use this to simulate slow-network or slow-model UX."
            ),
            default=0,
            min=0,
            max=2000,
            ui=UIHints(group="Settings"),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description=(
                "Frontend hint used to verify that managed agent instances can "
                "toggle file-attachment affordances in chat."
            ),
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document library picker",
            description=(
                "Frontend hint used to verify that managed agent instances can "
                "toggle library-selection affordances in chat."
            ),
            default=False,
            ui=UIHints(group="Chat options"),
        ),
    )

    input_schema = TestInput
    state_schema = TestState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="dispatch",
        nodes={
            "dispatch": dispatch_step,
            "echo": echo_step,
            "model_probe": model_probe_step,
            "hitl_choice": hitl_choice_step,
            "hitl_text": hitl_text_step,
            "trace": trace_step,
            "error": error_step,
            "long": long_step,
            "fallback": fallback_step,
            "finalize": finalize_step,
        },
        edges={
            "echo": "finalize",
            "model_probe": "finalize",
            "hitl_choice": "finalize",
            "hitl_text": "finalize",
            "trace": "finalize",
            "long": "finalize",
            "fallback": "finalize",
        },
        error_routes={
            "error": "finalize",
            "dispatch": "finalize",
        },
        routes={
            "dispatch": {
                "echo": "echo",
                "model_probe": "model_probe",
                "hitl_choice": "hitl_choice",
                "hitl_text": "hitl_text",
                "trace": "trace",
                "error": "error",
                "long": "long",
                "fallback": "fallback",
            },
        },
    )

    def build_output(self, state: BaseModel) -> BaseModel:
        """
        Override to attach mock VectorSearchHit sources when the trace scenario ran.

        The default GraphAgent.build_output only sets content; this override also
        populates sources from state.sources_data so SourcesPanel is exercised.
        """
        assert isinstance(state, TestState)
        content = state.final_text or ""

        sources: tuple[VectorSearchHit, ...] = ()
        for raw in state.sources_data:
            hit = VectorSearchHit.model_validate(raw)
            sources = (*sources, hit)

        return GraphExecutionOutput(content=content, sources=sources)


TEST_ASSISTANT_AGENT = TestAssistantGraphAgent()
