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
Document comparison graph agent (FILES-03).

Showcase agent for the targeted ``similarity_search`` MCP primitive
(KF-SIMILARITY-SEARCH). It compares two documents selected in the Documents picker
and reports what agrees, what contradicts, and what is missing between them — a
comparison agent, not a Q&A agent. Retrieval is deterministic; the LLM only judges
each paired passage.
"""

from __future__ import annotations

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    GraphAgent,
    GraphExecutionOutput,
    GraphWorkflow,
    MCPServerRef,
    UIHints,
)
from pydantic import BaseModel

from .graph_state import ComparisonInput, ComparisonState
from .graph_steps import (
    build_sources,
    compare_pairs_step,
    judge_pairs_step,
    pull_anchors_step,
    render_report_step,
    resolve_documents_step,
)

COMPARISON_AGENT_ID = "fred.dt.comparison.graph"


class ComparisonGraphAgent(GraphAgent):
    agent_id: str = COMPARISON_AGENT_ID
    role: str = "Document Comparison — similarity-based consistency review"
    description: str = (
        "Compares two documents selected in Fred's Documents picker and reports "
        "what agrees, what contradicts, and what is missing between them. Uses the "
        "targeted similarity search to pair passages of document A with their "
        "closest match in document B, then judges each pair. Useful for contract vs "
        "amendment, document vs standard/policy, or version A vs version B reviews."
    )
    tags: tuple[str, ...] = (
        "document-picker",
        "similarity-search",
        "comparison",
        "consistency",
        "knowledge-flow",
    )

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="settings.anchor_count",
            type="integer",
            title="Compared passages",
            description=(
                "Number of salient passages of document A to compare against "
                "document B."
            ),
            default=8,
            min=2,
            max=20,
            ui=UIHints(group="Comparison"),
        ),
        FieldSpec(
            key="settings.output_language",
            type="select",
            title="Output language",
            description="Report language. 'auto' follows the UI / the user's question.",
            default="auto",
            enum=["auto", "fr", "en"],
            ui=UIHints(group="Comparison"),
        ),
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description="Optional operator override appended to the pair-judging prompt.",
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    input_schema = ComparisonInput
    state_schema = ComparisonState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="resolve_documents",
        nodes={
            "resolve_documents": resolve_documents_step,
            "pull_anchors": pull_anchors_step,
            "compare_pairs": compare_pairs_step,
            "judge_pairs": judge_pairs_step,
            "render_report": render_report_step,
        },
        edges={
            "resolve_documents": "pull_anchors",
            "pull_anchors": "compare_pairs",
            "compare_pairs": "judge_pairs",
            "judge_pairs": "render_report",
        },
        error_routes={
            "resolve_documents": "render_report",
            "pull_anchors": "render_report",
            "compare_pairs": "render_report",
            "judge_pairs": "render_report",
        },
    )

    def build_output(self, state: BaseModel) -> BaseModel:
        assert isinstance(state, ComparisonState)
        return GraphExecutionOutput(
            content=state.final_text or "", sources=build_sources(state)
        )


COMPARISON_AGENT = ComparisonGraphAgent()
