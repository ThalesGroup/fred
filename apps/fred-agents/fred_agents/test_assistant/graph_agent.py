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
  so the control-plane agent form can be validated end-to-end from one agent definition.

Field type coverage:
  prompt          prompts.system / prompts.planning / prompts.routing
  boolean         settings.verbose
  integer         settings.delay_ms
  string          settings.greeting           (UIHints.placeholder)
  select + enum   settings.language
  number          settings.timeout_s          (float)
  text-multiline  settings.notes              (UIHints.textarea)
  array           settings.tags               (item_type=string)
  secret          credentials.api_key         (UIHints.placeholder)
  url             credentials.webhook_url     (UIHints.placeholder)

Tool coverage:
  declared_tool_refs   knowledge.search (required=True, locked)

Capability coverage:
  document summarize  Search then summarize through the capability approval gate.
  document scenario   AgentCapability tool invocation via
                       context.invoke_runtime_tool.
                       "document_access" is selected per-instance via
                       tuning.selected_capability_ids — NOT declared on this
                       class the way default_mcp_servers is. Degrades to a
                       helpful message when the capability isn't selected.

Workflow overview (keyword-routed by dispatch_step):

    dispatch
     ├─ echo        ──► echo_step        ──► finalize
     ├─ model_probe ──► model_probe_step ──► finalize
     ├─ hitl_confirm ──► hitl_confirm_step ──► finalize
     ├─ hitl_choice  ──► hitl_choice_step  ──► finalize
     ├─ hitl_text    ──► hitl_text_step    ──► finalize
     ├─ hitl_comment ──► hitl_comment_step ──► finalize
     ├─ trace       ──► trace_step       ──► finalize
     ├─ error       ──► error_step  (raises) → finalize (via on_error)
     ├─ think       ──► think_step        ──► finalize
     ├─ markdown    ──► markdown_step     ──► finalize
     ├─ mermaid     ──► mermaid_step      ──► finalize
     ├─ long        ──► long_step         ──► finalize
     ├─ geo         ──► geo_step          ──► finalize
     ├─ document    ──► document_step     ──► finalize
     ├─ assist      ──► assist_route ─┬─ search ─► assist_search ─► assist_draft
     │                                └─ direct ─────────────────► assist_draft
     │                  assist_draft ─► assist_review [HITL] ─► assist_confirm [HITL]
     │                  ─► assist_commit ─► finalize  (discard / keep ─► finalize)
     ├─ delegate    ──► delegate_step     ──► finalize
     ├─ crash       ──► crash_step  (raises, no on_error: the turn fails)
     ├─ graph check ──► graph_check_step ──► finalize  (live conformance run)
     └─ fallback    ──► fallback_step     ──► finalize

No model provider is needed: model-backed branches fall back to fixed text.
No MCP servers are required. The state is conversational: each completed turn
is appended to `conversation_history` and carried into the next one.
"""

from __future__ import annotations

from fred_core.store import VectorSearchHit
from fred_sdk import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    FieldSpec,
    GraphAgent,
    GraphWorkflow,
    ToolRefRequirement,
    UIHints,
)
from fred_sdk.contracts.context import ConversationTurn, GeoPart
from fred_sdk.graph.runtime import GraphExecutionOutput
from pydantic import BaseModel

from .graph_state import TEST_ASSISTANT_AGENT_ID, TestInput, TestState
from .graph_steps import (
    assist_draft_step,
    assist_review_step,
    assist_route_step,
    assist_search_step,
    crash_step,
    delegate_step,
    dispatch_step,
    document_step,
    echo_step,
    error_step,
    fallback_step,
    finalize_step,
    geo_step,
    graph_check_step,
    hitl_choice_step,
    hitl_comment_step,
    hitl_confirm_step,
    hitl_text_step,
    long_step,
    markdown_step,
    mermaid_step,
    model_probe_step,
    think_step,
    trace_step,
)

_DEFAULT_SYSTEM_PROMPT = (
    "You are the Test Assistant — a no-LLM validation agent.\n\n"
    "Send a message starting with one of these keywords to trigger a scenario:\n"
    "  echo | model | planning | hitl confirm | hitl choice | hitl text | hitl comment | "
    "trace | error | think | markdown | mermaid | long | geo | document\n\n"
    "Any other message shows this help menu."
)

_DEFAULT_PLANNING_PROMPT = (
    "Analyse the incoming message and select the appropriate test scenario "
    "before dispatch."
)

_DEFAULT_ROUTING_PROMPT = (
    "Select the model operation label from the scenario keyword prefix "
    "(echo, model, planning, …) to exercise operation-aware model routing."
)


class TestAssistantGraphAgent(GraphAgent):
    """
    No-LLM-by-default test agent that exercises all major SSE event types
    and every FieldSpec type available in the fred-sdk contract.

    Use this agent when you need to:
    - validate chat UI rendering without a model provider
    - validate the control-plane agent form renders all field types correctly
    - test HITL questions (confirmation, multiple choice, text, choice plus comment)
    - test source panel rendering with mock VectorSearchHit data
    - test error / node_error SSE event rendering
    - test long streaming reply layout (word-by-word via emit_assistant_delta)
    - validate declared_tool_refs rendering (locked vs toggleable rows)
    - optionally validate graph operation-aware model routing

    Send a message starting with one of the scenario keywords to trigger
    the corresponding workflow branch. Send anything else to see the help menu.
    """

    __test__ = False  # an agent definition, not a pytest test class

    agent_id: str = TEST_ASSISTANT_AGENT_ID
    supports_capabilities: bool = True
    role: str = "Test Assistant (no LLM)"
    description: str = (
        "Graph agent for UI and form testing (no LLM by default). "
        "Exercises every SSE event type (status, HITL choice, HITL text, "
        "streaming, sources, node errors, chain-of-thought) "
        "and every FieldSpec type (prompt, boolean, integer, string, select, "
        "number, text-multiline, array, secret, url). "
        "Routing by keyword prefix: echo | model | planning | "
        "hitl confirm | hitl choice | hitl text | hitl comment | trace | error | think | markdown | long."
    )
    tags: tuple[str, ...] = ("test", "graph", "hitl", "streaming", "no-llm", "dev")

    # ── Tool ref coverage ─────────────────────────────────────────────────────
    # The required search tool is locked in the agent form.
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            required=True,
            description=(
                "Knowledge search declared required=True. "
                "This row appears locked in the agent form and cannot be disabled."
            ),
        ),
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
            default=_DEFAULT_SYSTEM_PROMPT,
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
            default=_DEFAULT_PLANNING_PROMPT,
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
            default=_DEFAULT_ROUTING_PROMPT,
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
            "hitl_confirm": hitl_confirm_step,
            "hitl_choice": hitl_choice_step,
            "hitl_text": hitl_text_step,
            "hitl_comment": hitl_comment_step,
            "trace": trace_step,
            "error": error_step,
            "think": think_step,
            "markdown": markdown_step,
            "mermaid": mermaid_step,
            "long": long_step,
            "geo": geo_step,
            "document": document_step,
            "assist_route": assist_route_step,
            "assist_search": assist_search_step,
            "assist_draft": assist_draft_step,
            "assist_review": assist_review_step,
            "delegate": delegate_step,
            "crash": crash_step,
            "graph_check": graph_check_step,
            "fallback": fallback_step,
            "finalize": finalize_step,
        },
        edges={
            "assist_search": "assist_draft",
            "assist_draft": "assist_review",
            "delegate": "finalize",
            "graph_check": "finalize",
            "echo": "finalize",
            "model_probe": "finalize",
            "hitl_confirm": "finalize",
            "hitl_choice": "finalize",
            "hitl_text": "finalize",
            "hitl_comment": "finalize",
            "trace": "finalize",
            "think": "finalize",
            "markdown": "finalize",
            "mermaid": "finalize",
            "long": "finalize",
            "geo": "finalize",
            "document": "finalize",
            "fallback": "finalize",
        },
        error_routes={
            "error": "finalize",
            "dispatch": "finalize",
            # A failed search degrades to a direct answer, as a real agent would.
            "assist_search": "assist_draft",
        },
        routes={
            "dispatch": {
                "echo": "echo",
                "model_probe": "model_probe",
                "hitl_confirm": "hitl_confirm",
                "hitl_choice": "hitl_choice",
                "hitl_text": "hitl_text",
                "hitl_comment": "hitl_comment",
                "trace": "trace",
                "error": "error",
                "think": "think",
                "markdown": "markdown",
                "mermaid": "mermaid",
                "long": "long",
                "geo": "geo",
                "document": "document",
                "assist": "assist_route",
                "delegate": "delegate",
                "crash": "crash",
                "graph_check": "graph_check",
                "fallback": "fallback",
            },
            "assist_route": {
                "search": "assist_search",
                "direct": "assist_draft",
            },
            "assist_review": {
                "approved": "finalize",
                "discarded": "finalize",
            },
        },
    )

    def build_completed_state(self, state: BaseModel) -> BaseModel:
        """Append this turn to `conversation_history` so the next turn sees it."""
        assert isinstance(state, TestState)
        turn = ConversationTurn(
            user_message=state.latest_user_text,
            agent_response=state.final_text or "",
        )
        return state.model_copy(
            update={"conversation_history": (*state.conversation_history, turn)}
        )

    def build_output(self, state: BaseModel) -> BaseModel:
        """
        Override to attach mock VectorSearchHit sources and token_usage when the
        trace scenario ran (SourcesPanel + token badge), ui_parts when
        the files scenario ran (download chip rendering), and GeoPart ui_parts
        when the geo scenario ran (feature-count summary chip rendering — the
        interactive Leaflet map was removed from the frontend, PR #2067).
        """
        assert isinstance(state, TestState)
        content = state.final_text or ""

        sources: tuple[VectorSearchHit, ...] = ()
        for raw in state.sources_data:
            hit = VectorSearchHit.model_validate(raw)
            sources = (*sources, hit)

        ui_parts: tuple[GeoPart, ...] = ()
        for raw in state.geo_parts:
            ui_parts = (*ui_parts, GeoPart.model_validate(raw))

        token_usage: dict[str, int] | None = None
        if state.scenario == "trace" and sources:
            token_usage = {
                "input_tokens": 312,
                "output_tokens": 87,
                "total_tokens": 399,
            }

        return GraphExecutionOutput(
            content=content, sources=sources, token_usage=token_usage, ui_parts=ui_parts
        )


TEST_ASSISTANT_AGENT = TestAssistantGraphAgent()
