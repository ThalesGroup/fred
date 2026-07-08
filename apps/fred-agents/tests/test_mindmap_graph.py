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

from types import SimpleNamespace
from typing import cast

import pytest
from fred_agents.mindmap.graph_agent import MINDMAP_AGENT
from fred_agents.mindmap.graph_state import DocumentSegmentSummary, MindmapState
from fred_agents.mindmap.graph_steps import (
    _DOCUMENT_PICKER_MESSAGE,
    MindMapPayload,
    build_document_digest_step,
    normalize_mindmap_payload,
    read_selected_documents_step,
    render_mindmap_markdown,
    resolve_selected_documents_step,
)
from fred_sdk import GraphNodeContext, load_agent_prompt_markdown


class _FakeContext:
    """
    Minimal graph-node context used by the mindmap step unit tests.

    Why this exists:
    - the business steps only need a small slice of the runtime protocol
    - keeping the fake tiny makes the tests easy to read and adapt

    How to use it:
    - configure `selected_document_uids`, `tuning_values`, and optional tool
      payloads per test case
    - cast the instance to `GraphNodeContext` at the call site
    """

    def __init__(
        self,
        *,
        selected_document_uids: list[str] | None = None,
        tuning_values: dict[str, object] | None = None,
        runtime_tool_pages: list[object] | None = None,
    ) -> None:
        self.binding = SimpleNamespace(
            runtime_context=SimpleNamespace(
                selected_document_uids=selected_document_uids,
            )
        )
        self.tuning_values = dict(tuning_values or {})
        self.model = None
        self._runtime_tool_pages = list(runtime_tool_pages or [])
        self.runtime_tool_calls: list[tuple[str, dict[str, object]]] = []
        self.statuses: list[tuple[str, str | None]] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))

    async def invoke_runtime_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> object:
        self.runtime_tool_calls.append((tool_name, dict(arguments)))
        if not self._runtime_tool_pages:
            raise AssertionError("No fake runtime tool payload configured.")
        return self._runtime_tool_pages.pop(0)

    async def invoke_tool(self, tool_ref: str, payload: dict[str, object]):
        raise AssertionError(
            f"Unexpected tool invocation in this test: {tool_ref} {payload}"
        )

    async def invoke_model(self, messages, *, operation: str = "default"):
        raise AssertionError(f"Unexpected model invocation in this test: {operation}")

    async def invoke_structured_model(
        self, output_model, messages, *, operation: str = "default"
    ):
        raise AssertionError(
            f"Unexpected structured model invocation in this test: {output_model} {operation}"
        )


@pytest.mark.asyncio
async def test_resolve_selected_documents_requests_picker_when_nothing_selected() -> (
    None
):
    """
    Verify strict mode asks the user to use the document picker.

    Why this test exists:
    - selected-document mode is the default contract for the final mindmap
      agent
    - the graph should stop early with explicit picker guidance instead of
      drifting into search

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    state = MindmapState(latest_user_text="build a transcript mindmap")
    context = cast(GraphNodeContext, _FakeContext(selected_document_uids=None))

    result = await resolve_selected_documents_step(state, context)

    assert result.state_update["final_text"] == _DOCUMENT_PICKER_MESSAGE
    assert result.state_update["needs_document_selection"] is True
    assert result.state_update["done_reason"] == "needs_document_selection"


@pytest.mark.asyncio
async def test_resolve_selected_documents_can_enable_explicit_search_fallback() -> None:
    """
    Verify the graph can opt into the legacy search path explicitly.

    Why this test exists:
    - fallback search must stay behind an explicit setting
    - the routing step is where that guardrail lives

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    state = MindmapState(latest_user_text="build a transcript mindmap")
    context = cast(
        GraphNodeContext,
        _FakeContext(
            selected_document_uids=[],
            tuning_values={
                "settings.allow_search_fallback": True,
                "settings.require_selected_documents": False,
            },
        ),
    )

    result = await resolve_selected_documents_step(state, context)

    assert result.state_update["use_search_fallback"] is True
    assert result.state_update["needs_document_selection"] is False


@pytest.mark.asyncio
async def test_read_selected_documents_uses_paginated_preview_reads() -> None:
    """
    Verify selected-document mode reads multiple filesystem pages sequentially.

    Why this test exists:
    - the main refactor replaces chunk search with paginated preview coverage
    - the graph must keep only compact summaries and synthetic grounded sources

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    state = MindmapState(
        latest_user_text="build a transcript mindmap",
        selected_document_uids=["doc-1"],
    )
    fake_context = _FakeContext(
        selected_document_uids=["doc-1"],
        runtime_tool_pages=[
            {
                "path": "/corpus/documents/doc-1/preview.md",
                "content": "1 | intro\n2 | agenda",
                "start_line": 1,
                "end_line": 2,
                "total_lines": 4,
                "has_more": True,
                "next_offset": 2,
                "truncated": False,
            },
            {
                "path": "/corpus/documents/doc-1/preview.md",
                "content": "3 | decision\n4 | action",
                "start_line": 3,
                "end_line": 4,
                "total_lines": 4,
                "has_more": False,
                "next_offset": None,
                "truncated": False,
            },
        ],
    )
    context = cast(GraphNodeContext, fake_context)

    result = await read_selected_documents_step(state, context)

    raw_summaries = cast(
        list[object],
        result.state_update["document_segment_summaries"],
    )
    summaries = [DocumentSegmentSummary.model_validate(raw) for raw in raw_summaries]
    source_refs = cast(list[object], result.state_update["source_refs"])
    assert len(summaries) == 2
    assert summaries[0].document_uid == "doc-1"
    assert summaries[0].line_range == "L1-L2"
    assert summaries[1].line_range == "L3-L4"
    assert len(source_refs) == 2
    assert result.state_update["done_reason"] is None
    assert fake_context.runtime_tool_calls == [
        (
            "read_file_page",
            {
                "path": "/corpus/documents/doc-1/preview.md",
                "offset": 0,
                "limit": 120,
                "max_chars": 18000,
            },
        ),
        (
            "read_file_page",
            {
                "path": "/corpus/documents/doc-1/preview.md",
                "offset": 2,
                "limit": 120,
                "max_chars": 18000,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_build_document_digest_falls_back_to_compact_summary_text_without_model() -> (
    None
):
    """
    Verify digest building still works in offline no-model test mode.

    Why this test exists:
    - the helper-based steps should remain testable without a live model
    - fallback text keeps the graph runnable in smoke and unit tests

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    summary = DocumentSegmentSummary(
        document_uid="doc-1",
        page_index=0,
        line_range="L1-L2",
        title="Opening",
        summary="Introduces the topic and agenda.",
        key_points=["topic", "agenda"],
    )
    state = MindmapState(
        latest_user_text="build a transcript mindmap",
        document_segment_summaries=[summary.model_dump()],
        output_language="en",
    )
    context = cast(GraphNodeContext, _FakeContext(selected_document_uids=["doc-1"]))

    result = await build_document_digest_step(state, context)

    digest = cast(str, result.state_update["document_digest"])
    assert "Document: doc-1" in digest
    assert "Summary: Introduces the topic and agenda." in digest


def test_mindmap_prompts_and_defaults_favor_coverage_and_depth() -> None:
    """
    Verify the shipped prompts and defaults favor concrete transcript coverage.

    Why this test exists:
    - the regression in this task was caused by overly executive prompt wording
      plus a too-tight default branch cap
    - checking the shipped prompt files and agent defaults guards the intended
      behavior without needing a live model

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    extract_prompt = load_agent_prompt_markdown(
        package="fred_agents.mindmap",
        file_name="extract_mindmap.md",
    )
    refine_prompt = load_agent_prompt_markdown(
        package="fred_agents.mindmap",
        file_name="refine_mindmap.md",
    )

    assert "Prefer an executive mindmap" not in extract_prompt
    assert "coverage-oriented transcript mindmap" in extract_prompt
    assert "Do not collapse distinct topics into generic labels" in extract_prompt
    assert "coverage-oriented transcript mindmap" in refine_prompt

    max_children_field = next(
        field
        for field in MINDMAP_AGENT.fields
        if field.key == "settings.max_children_per_node"
    )
    assert max_children_field.default == 8


def test_normalized_payload_preserves_initial_depth_two() -> None:
    """
    Verify payload normalization keeps an explicit initial depth of two.

    Why this test exists:
    - the frontend renderer now respects `presentation.initialDepth`
    - the backend should therefore preserve an explicit depth when the model
      asks for it

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    payload = MindMapPayload.model_validate(
        {
            "title": "Transcript mindmap",
            "root": {
                "id": "root",
                "name": "Fred-native Audio-to-Mindmap Agent",
                "children": [],
            },
            "presentation": {
                "initialDepth": 2,
                "layout": "orthogonal",
                "focusMode": True,
            },
        }
    )

    normalized = normalize_mindmap_payload(
        payload,
        max_depth=4,
        max_children=8,
        include_evidence=True,
        max_source_index=0,
    )

    presentation = cast(dict[str, object], normalized["presentation"])
    assert presentation["initialDepth"] == 2


def test_rendered_markdown_keeps_concrete_branches_in_mindmap_json() -> None:
    """
    Verify rendered markdown exposes concrete transcript branches in the payload.

    Why this test exists:
    - this task specifically targets generic, over-compressed branch labels
    - checking the rendered fenced payload guards the final frontend contract

    How to use it:
    - run via `make test` from the `fred-agents` project
    """

    payload = {
        "version": "1.0",
        "title": "Fred-native Audio-to-Mindmap Agent",
        "summary": "Concrete transcript branches are preserved.",
        "root": {
            "id": "root",
            "name": "Fred-native Audio-to-Mindmap Agent",
            "children": [
                {"id": "objective", "name": "Objective", "children": []},
                {"id": "frontend-mvp", "name": "Frontend MVP", "children": []},
                {
                    "id": "backend-graph-agent",
                    "name": "Backend Graph Agent",
                    "children": [],
                },
                {
                    "id": "knowledge-flow-integration",
                    "name": "Knowledge Flow Integration",
                    "children": [],
                },
                {"id": "ux-requirements", "name": "UX Requirements", "children": []},
                {"id": "retrieval-risks", "name": "Retrieval Risks", "children": []},
                {"id": "testing-strategy", "name": "Testing Strategy", "children": []},
                {"id": "roadmap", "name": "Roadmap", "children": []},
            ],
        },
        "presentation": {
            "initialDepth": 2,
            "layout": "orthogonal",
            "focusMode": True,
        },
    }

    markdown = render_mindmap_markdown(payload)

    assert "```mindmap-json" in markdown
    for branch in (
        "Objective",
        "Frontend MVP",
        "Backend Graph Agent",
        "Knowledge Flow Integration",
        "UX Requirements",
        "Retrieval Risks",
        "Testing Strategy",
        "Roadmap",
    ):
        assert branch in markdown
