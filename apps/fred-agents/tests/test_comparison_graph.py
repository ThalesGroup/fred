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
from fred_sdk import GraphNodeContext

from fred_agents.comparison.graph_agent import COMPARISON_AGENT
from fred_agents.comparison.graph_state import ComparisonState
from fred_agents.comparison.graph_steps import (
    _NO_ANCHORS_MESSAGE,
    _PICKER_MESSAGE,
    build_sources,
    compare_pairs_step,
    judge_pairs_step,
    pull_anchors_step,
    render_report_step,
    resolve_documents_step,
)


class _FakeContext:
    """
    Minimal graph-node context for the comparison step unit tests.

    Configure the picker selection, tuning values, a queue of ``similarity_search``
    tool results (each a list of hit dicts), and an optional structured-model result
    used by the pair judge. Cast to ``GraphNodeContext`` at the call site.
    """

    def __init__(
        self,
        *,
        selected_document_uids: list[str] | None = None,
        tuning_values: dict[str, object] | None = None,
        similarity_results: list[object] | None = None,
        structured_result: object | None = None,
    ) -> None:
        self.binding = SimpleNamespace(
            runtime_context=SimpleNamespace(
                selected_document_uids=selected_document_uids,
            )
        )
        self.tuning_values = dict(tuning_values or {})
        # Non-None model → structured_model_step calls invoke_structured_model.
        self.model: object | None = object() if structured_result is not None else None
        self._similarity_results = list(similarity_results or [])
        self._structured_result = structured_result
        self.runtime_tool_calls: list[tuple[str, dict[str, object]]] = []
        self.statuses: list[tuple[str, str | None]] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        self.runtime_tool_calls.append((tool_name, dict(arguments)))
        if not self._similarity_results:
            raise AssertionError("No fake similarity_search payload configured.")
        return self._similarity_results.pop(0)

    async def invoke_structured_model(
        self, output_model: type, messages: object, *, operation: str = "default"
    ) -> object:
        if self._structured_result is None:
            raise AssertionError(f"Unexpected structured model call: {operation}")
        return self._structured_result


def _ctx(
    *,
    selected_document_uids: list[str] | None = None,
    tuning_values: dict[str, object] | None = None,
    similarity_results: list[object] | None = None,
    structured_result: object | None = None,
) -> GraphNodeContext:
    return cast(
        GraphNodeContext,
        _FakeContext(
            selected_document_uids=selected_document_uids,
            tuning_values=tuning_values,
            similarity_results=similarity_results,
            structured_result=structured_result,
        ),
    )


# --- resolve_documents -----------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_documents_requests_picker_when_fewer_than_two() -> None:
    """With <2 selected documents, the agent stops and asks for a selection."""
    state = ComparisonState(latest_user_text="compare these")
    result = await resolve_documents_step(
        state, _ctx(selected_document_uids=["only-1"])
    )

    assert result.state_update["final_text"] == _PICKER_MESSAGE["en"]
    assert result.state_update["needs_document_selection"] is True
    assert result.state_update["done_reason"] == "needs_document_selection"


@pytest.mark.asyncio
async def test_resolve_documents_picks_first_two_and_notes_extras() -> None:
    """A = first selected, B = second; any extras are recorded, not compared."""
    state = ComparisonState(latest_user_text="compare these")
    result = await resolve_documents_step(
        state, _ctx(selected_document_uids=["a", "b", "c"])
    )

    assert result.state_update["doc_a_uid"] == "a"
    assert result.state_update["doc_b_uid"] == "b"
    assert result.state_update["extra_document_uids"] == ["c"]


# --- pull_anchors ----------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_anchors_queries_similarity_scoped_to_document_a() -> None:
    """Anchors come from similarity_search, kept only for document A (by uid)."""
    state = ComparisonState(
        latest_user_text="liability clauses", doc_a_uid="a", doc_b_uid="b"
    )
    # Runtime widens scope to both docs; the B hit must be dropped client-side.
    ctx = _FakeContext(
        similarity_results=[
            [
                {"content": "A liability text", "uid": "a"},
                {"content": "B liability text", "uid": "b"},
            ]
        ]
    )

    result = await pull_anchors_step(state, cast(GraphNodeContext, ctx))

    anchors = cast(list[dict[str, object]], result.state_update["anchors"])
    assert [a["content"] for a in anchors] == ["A liability text"]
    tool_name, args = ctx.runtime_tool_calls[0]
    assert tool_name == "similarity_search"
    assert args["document_uids"] == ["a"]
    assert args["anchor"] == "liability clauses"
    assert args["top_k"] == 24  # over-fetch pool = max(anchor_count*3, 12)
    assert args["rerank"] is True


@pytest.mark.asyncio
async def test_pull_anchors_stops_with_message_when_document_a_has_no_passages() -> (
    None
):
    """An empty similarity result short-circuits to a friendly message."""
    state = ComparisonState(latest_user_text="x", doc_a_uid="a", doc_b_uid="b")
    result = await pull_anchors_step(state, _ctx(similarity_results=[[]]))

    assert result.state_update["final_text"] == _NO_ANCHORS_MESSAGE["en"]
    assert result.state_update["done_reason"] == "no_anchors"


# --- compare_pairs ---------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_pairs_matches_each_anchor_against_document_b() -> None:
    """Each A-passage is paired with its closest B-passage (kept by uid == B)."""
    state = ComparisonState(
        latest_user_text="x",
        doc_a_uid="a",
        doc_b_uid="b",
        anchors=[{"content": "A text", "uid": "a"}],
    )
    # The self-match to A (score 1.0) must be dropped; the best B hit is kept.
    ctx = _FakeContext(
        similarity_results=[
            [
                {"content": "A text", "uid": "a", "score": 1.0},
                {"content": "B text", "uid": "b", "score": 0.9},
            ]
        ]
    )

    result = await compare_pairs_step(state, cast(GraphNodeContext, ctx))

    pairs = cast(list[dict[str, object]], result.state_update["pairs"])
    match = cast(dict[str, object], pairs[0]["match"])
    assert match["content"] == "B text"
    sources = cast(list[object], result.state_update["source_refs"])
    assert len(sources) == 1
    _, args = ctx.runtime_tool_calls[0]
    assert args["document_uids"] == ["b"]
    assert args["top_k"] == 10  # over-fetch pool


# --- judge_pairs -----------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_pairs_marks_gap_without_calling_model() -> None:
    """A pair with no B-match is a deterministic lacune — no model call."""
    state = ComparisonState(
        latest_user_text="x",
        pairs=[{"anchor": {"content": "A text"}, "match": None}],
    )
    # structured_result=None → invoke_structured_model would raise if called.
    result = await judge_pairs_step(state, _ctx())

    verdicts = cast(list[dict[str, object]], result.state_update["verdicts"])
    assert verdicts[0]["relation"] == "lacune"
    assert verdicts[0]["match"] == ""


@pytest.mark.asyncio
async def test_judge_pairs_uses_model_to_classify_a_real_pair() -> None:
    """When both passages exist, the LLM verdict drives the relation."""
    state = ComparisonState(
        latest_user_text="x",
        pairs=[{"anchor": {"content": "A says v1"}, "match": {"content": "B says v2"}}],
    )
    ctx = _ctx(structured_result={"relation": "contradiction", "note": "v1 vs v2"})

    result = await judge_pairs_step(state, ctx)

    verdicts = cast(list[dict[str, object]], result.state_update["verdicts"])
    assert verdicts[0]["relation"] == "contradiction"
    assert verdicts[0]["note"] == "v1 vs v2"
    assert verdicts[0]["anchor"] == "A says v1"
    assert verdicts[0]["match"] == "B says v2"


# --- render_report ---------------------------------------------------------


@pytest.mark.asyncio
async def test_render_report_groups_verdicts_into_three_sections() -> None:
    """The report carries Contradictions / Agreements / Gaps with counts."""
    state = ComparisonState(
        latest_user_text="x",
        doc_a_uid="a",
        doc_b_uid="b",
        verdicts=[
            {"relation": "contradiction", "anchor": "p1", "match": "q1", "note": "n1"},
            {"relation": "concordance", "anchor": "p2", "match": "q2", "note": "n2"},
            {"relation": "lacune", "anchor": "p3", "match": "", "note": ""},
        ],
    )
    result = await render_report_step(state, _ctx())

    report = cast(str, result.state_update["final_text"])
    assert "## Contradictions (1)" in report
    assert "## Agreements (1)" in report
    assert "## Gaps (1)" in report
    assert "n1" in report


@pytest.mark.asyncio
async def test_render_report_uses_document_names_and_user_language() -> None:
    """The report shows human-readable document names (not UUIDs) and is rendered
    in the user's language (French here)."""
    state = ComparisonState(
        latest_user_text="compare ces deux versions",
        language="fr",  # resolve_documents sets this from the question / UI / tuning
        doc_a_uid="b7a986-uuid",
        doc_b_uid="4a3a66-uuid",
        doc_a_name="MARTO_v1.docx",
        doc_b_name="MARTO_v2.docx",
        verdicts=[
            {
                "relation": "contradiction",
                "anchor": "p1",
                "match": "q1",
                "note": "écart",
            },
        ],
    )
    result = await render_report_step(state, _ctx())

    report = cast(str, result.state_update["final_text"])
    # human-readable names, not raw UUIDs
    assert "MARTO_v1.docx" in report
    assert "MARTO_v2.docx" in report
    assert "b7a986-uuid" not in report
    # French scaffolding
    assert "# Comparaison de documents" in report
    assert "## Concordances (0)" in report
    assert "## Lacunes (0)" in report


def test_detect_language_picks_french_and_english() -> None:
    from fred_agents.comparison.graph_steps import _detect_language

    assert _detect_language("compare ces deux versions du dossier") == "fr"
    assert _detect_language("évaluation de la robustesse") == "fr"
    assert _detect_language("compare these two documents") == "en"


# --- wiring + sources ------------------------------------------------------


def test_comparison_agent_graph_is_wired() -> None:
    """The workflow chains the five nodes and degrades forward on error."""
    wf = COMPARISON_AGENT.workflow
    assert wf is not None
    assert wf.entry == "resolve_documents"
    assert set(wf.nodes) == {
        "resolve_documents",
        "pull_anchors",
        "compare_pairs",
        "judge_pairs",
        "render_report",
    }
    assert wf.edges["judge_pairs"] == "render_report"
    # best-effort: every fallible node routes forward to the report on error
    assert set(wf.error_routes.values()) == {"render_report"}


def test_build_sources_validates_hits_and_skips_malformed() -> None:
    """Collected B-matches become grounded VectorSearchHit sources."""
    state = ComparisonState(
        latest_user_text="x",
        # second entry is a dict (valid state) but not a valid VectorSearchHit
        # (missing required uid/title/score).
        source_refs=[
            {"content": "B text", "uid": "b#1", "title": "B", "score": 0.9},
            {"content": "incomplete"},
        ],
    )
    sources = build_sources(state)
    assert len(sources) == 1
    assert sources[0].content == "B text"
