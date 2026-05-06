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
- Expose every FieldSpec type, UIHints option, declared_tool_refs pattern, and
  default_mcp_servers pattern so the control-plane agent form can be validated
  end-to-end from one agent definition.

Field type coverage:
  prompt          prompts.system / prompts.planning / prompts.routing
  boolean         settings.verbose / chat_options.attach_files / chat_options.libraries_selection
  integer         settings.delay_ms
  string          settings.greeting           (UIHints.placeholder)
  select + enum   settings.language
  number          settings.timeout_s          (float)
  text-multiline  settings.notes              (UIHints.textarea)
  array           settings.tags               (item_type=string)
  secret          credentials.api_key         (UIHints.placeholder)
  url             credentials.webhook_url     (UIHints.placeholder)

Tool/MCP coverage:
  declared_tool_refs   knowledge.search (required=True, locked)
                       artifacts.publish_text (required=False, toggleable)
  default_mcp_servers  knowledge-flow/text (default-on, toggleable)

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
from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    GraphAgent,
    GraphWorkflow,
    MCPServerRef,
    ToolRefRequirement,
    UIHints,
)
from fred_sdk import (
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    TOOL_REF_KNOWLEDGE_SEARCH,
)
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
    No-LLM-by-default test agent that exercises all major SSE event types
    and every FieldSpec type available in the fred-sdk contract.

    Use this agent when you need to:
    - validate chat UI rendering without a model provider
    - validate the control-plane agent form renders all field types correctly
    - test HITL flows (binary choice and free-text)
    - test source panel rendering with mock VectorSearchHit data
    - test error / node_error SSE event rendering
    - test long streaming reply layout (word-by-word via emit_assistant_delta)
    - validate declared_tool_refs rendering (locked vs toggleable rows)
    - validate default_mcp_servers rendering (toggleable MCP section)
    - optionally validate graph operation-aware model routing

    Send a message starting with one of the scenario keywords to trigger
    the corresponding workflow branch. Send anything else to see the help menu.
    """

    agent_id: str = "fred.github.test_assistant"
    role: str = "Test Assistant (no LLM)"
    description: str = (
        "A no-LLM-by-default, no-MCP graph agent for UI and form testing. "
        "Exercises every SSE event type (status, HITL choice, HITL free-text, "
        "streaming text, mock sources, node errors, long streaming) and every "
        "FieldSpec type (prompt, boolean, integer, string, select, number, "
        "text-multiline, array, secret, url). Also declares tool refs and an "
        "MCP server to validate form rendering of those sections. "
        "Keyword-prefix routing: echo | model routing | model planning | "
        "hitl choice | hitl text | trace | error | long."
    )
    tags: tuple[str, ...] = ("test", "graph", "hitl", "streaming", "no-llm", "dev")

    # ── Tool ref coverage ─────────────────────────────────────────────────────
    # Two tool refs to test both rendering modes in the agent form:
    # - required=True  (default) → locked row, cannot be disabled
    # - required=False           → toggleable row, can be disabled per instance
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            required=True,
            description=(
                "Knowledge search declared required=True. "
                "This row appears locked in the agent form and cannot be disabled."
            ),
        ),
        ToolRefRequirement(
            tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
            required=False,
            description=(
                "Artifact publish declared required=False. "
                "This row appears as a toggleable option in the agent form."
            ),
        ),
    )

    # ── MCP server coverage ───────────────────────────────────────────────────
    # One MCP server to validate that the MCP section renders in the agent form
    # with a default-on, toggleable checkbox per instance.
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
    )

    # ── Field spec coverage ───────────────────────────────────────────────────
    fields: tuple[FieldSpec, ...] = (
        # ── Prompts ──────────────────────────────────────────────────────────
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
        # ── Settings — scalar types ───────────────────────────────────────────
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
            key="settings.greeting",
            type="string",
            title="Greeting label",
            description=(
                "Short text prepended to every echo reply. "
                "Exercises the single-line string input field."
            ),
            required=False,
            ui=UIHints(group="Settings", placeholder="e.g. Hello from test-agent!"),
        ),
        FieldSpec(
            key="settings.language",
            type="select",
            title="Reply language",
            description=(
                "Language tag appended to the fallback help reply. "
                "Exercises the select / dropdown field type."
            ),
            default="en",
            enum=["en", "fr", "de", "es"],
            ui=UIHints(group="Settings"),
        ),
        FieldSpec(
            key="settings.timeout_s",
            type="number",
            title="Timeout (s)",
            description=(
                "Floating-point timeout value stored but not enforced. "
                "Exercises the number / float field type."
            ),
            default=5.0,
            min=0.1,
            max=30.0,
            ui=UIHints(group="Settings"),
        ),
        FieldSpec(
            key="settings.notes",
            type="text-multiline",
            title="Notes",
            description=(
                "Free-form admin notes. "
                "Exercises the text-multiline field type with textarea=True."
            ),
            required=False,
            ui=UIHints(group="Settings", textarea=True, multiline=True, max_lines=4),
        ),
        FieldSpec(
            key="settings.tags",
            type="array",
            title="Tags",
            description=(
                "List of string tags attached to this instance. "
                "Exercises the array field type with item_type='string'."
            ),
            required=False,
            item_type="string",
            ui=UIHints(group="Settings"),
        ),
        # ── Credentials ───────────────────────────────────────────────────────
        FieldSpec(
            key="credentials.api_key",
            type="secret",
            title="API key",
            description=(
                "Masked secret input — value is stored encrypted and never "
                "shown in plaintext. Exercises the secret field type."
            ),
            required=False,
            ui=UIHints(group="Credentials", placeholder="sk-…"),
        ),
        FieldSpec(
            key="credentials.webhook_url",
            type="url",
            title="Webhook URL",
            description=(
                "URL-validated input. Value is validated as an absolute URL. "
                "Exercises the url field type."
            ),
            required=False,
            ui=UIHints(group="Credentials", placeholder="https://…"),
        ),
        # ── Chat options ──────────────────────────────────────────────────────
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
