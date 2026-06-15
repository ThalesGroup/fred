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

from __future__ import annotations

from fred_core.store import VectorSearchHit
from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    TOOL_REF_KNOWLEDGE_SEARCH,
    FieldSpec,
    GraphAgent,
    GraphExecutionOutput,
    GraphWorkflow,
    MCPServerRef,
    ToolRefRequirement,
    UIHints,
)
from pydantic import BaseModel

from .graph_state import MindmapInput, MindmapState
from .graph_steps import (
    analyze_request_step,
    build_document_digest_step,
    extract_mindmap_step,
    refine_mindmap_step,
    read_selected_documents_step,
    resolve_selected_documents_step,
    render_response_step,
)

MINDMAP_AGENT_ID = "fred.dt.mindmap.graph"


class MindmapGraphAgent(GraphAgent):
    agent_id: str = MINDMAP_AGENT_ID
    role: str = "Mindmap — Knowledge Flow transcript visualizer"
    description: str = (
        "Generates an exhaustive mindmap from transcript/script documents "
        "explicitly selected in Fred's Documents picker. Reads selected "
        "Knowledge Flow documents through bounded paginated filesystem access "
        "and summarizes them before generating the mindmap."
    )
    tags: tuple[str, ...] = (
        "document-picker",
        "paginated-read",
        "transcript",
        "script",
        "mindmap",
        "knowledge-flow",
    )

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_FS),
    )

    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search selected Knowledge Flow transcript libraries and return grounded snippets."
            ),
        ),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="settings.top_k",
            type="integer",
            title="Top K",
            description="Maximum number of transcript chunks retrieved per fallback search query.",
            default=16,
            min=4,
            max=30,
            ui=UIHints(group="Fallback"),
        ),
        FieldSpec(
            key="settings.require_selected_documents",
            type="boolean",
            title="Require selected documents",
            description=(
                "Require the user to select transcript/script documents with "
                "the Documents picker before generating a mindmap."
            ),
            default=True,
            ui=UIHints(group="Document reading"),
        ),
        FieldSpec(
            key="settings.page_line_limit",
            type="integer",
            title="Page line limit",
            description="Maximum number of document lines read per paginated call.",
            default=120,
            min=20,
            max=500,
            ui=UIHints(group="Document reading"),
        ),
        FieldSpec(
            key="settings.page_max_chars",
            type="integer",
            title="Page max characters",
            description="Maximum number of characters read per paginated call.",
            default=18000,
            min=4000,
            max=50000,
            ui=UIHints(group="Document reading"),
        ),
        FieldSpec(
            key="settings.max_pages_per_document",
            type="integer",
            title="Max pages per document",
            description="Safety limit for the number of pages read from each selected document.",
            default=20,
            min=1,
            max=100,
            ui=UIHints(group="Document reading"),
        ),
        FieldSpec(
            key="settings.max_selected_documents",
            type="integer",
            title="Max selected documents",
            description="Maximum number of selected documents processed in one request.",
            default=5,
            min=1,
            max=20,
            ui=UIHints(group="Document reading"),
        ),
        FieldSpec(
            key="settings.allow_search_fallback",
            type="boolean",
            title="Allow search fallback",
            description=(
                "Allow the agent to fall back to Knowledge Flow search when no "
                "document is selected. Disabled by default because exhaustive "
                "mindmaps require full document coverage."
            ),
            default=False,
            ui=UIHints(group="Fallback"),
        ),
        FieldSpec(
            key="settings.max_depth",
            type="integer",
            title="Max depth",
            description="Maximum depth of the generated mindmap tree.",
            default=4,
            min=2,
            max=6,
            ui=UIHints(group="Mindmap"),
        ),
        FieldSpec(
            key="settings.max_children_per_node",
            type="integer",
            title="Max children per node",
            description="Maximum number of children under each mindmap node.",
            default=8,
            min=2,
            max=10,
            ui=UIHints(group="Mindmap"),
        ),
        FieldSpec(
            key="settings.output_language",
            type="select",
            title="Output language",
            description="Language used for labels and summaries.",
            default="auto",
            enum=["auto", "fr", "en"],
            ui=UIHints(group="Mindmap"),
        ),
        FieldSpec(
            key="settings.include_evidence",
            type="boolean",
            title="Include evidence",
            description="Attach source references and supporting notes to mindmap nodes when available.",
            default=True,
            ui=UIHints(group="Grounding"),
        ),
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description="Optional operator override for the Mindmap extraction behavior.",
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    input_schema = MindmapInput
    state_schema = MindmapState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="analyze_request",
        nodes={
            "analyze_request": analyze_request_step,
            "resolve_selected_documents": resolve_selected_documents_step,
            "read_selected_documents": read_selected_documents_step,
            "build_document_digest": build_document_digest_step,
            "extract_mindmap": extract_mindmap_step,
            "refine_mindmap": refine_mindmap_step,
            "render_response": render_response_step,
        },
        edges={
            "analyze_request": "resolve_selected_documents",
            "resolve_selected_documents": "read_selected_documents",
            "read_selected_documents": "build_document_digest",
            "build_document_digest": "extract_mindmap",
            "extract_mindmap": "refine_mindmap",
            "refine_mindmap": "render_response",
        },
        error_routes={
            "analyze_request": "render_response",
            "resolve_selected_documents": "render_response",
            "read_selected_documents": "render_response",
            "build_document_digest": "render_response",
            "extract_mindmap": "render_response",
            "refine_mindmap": "render_response",
        },
    )

    def build_output(self, state: BaseModel) -> BaseModel:
        assert isinstance(state, MindmapState)
        sources: tuple[VectorSearchHit, ...] = ()
        for raw in state.source_refs:
            sources = (*sources, VectorSearchHit.model_validate(raw))
        return GraphExecutionOutput(content=state.final_text or "", sources=sources)


MINDMAP_AGENT = MindmapGraphAgent()
