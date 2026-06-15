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

import json
import re
from collections.abc import Sequence
from typing import Literal

from fred_core.store import VectorSearchHit
from fred_sdk import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    GraphNodeContext,
    StepResult,
    load_agent_prompt_markdown,
    model_text_step,
    structured_model_step,
    typed_node,
)
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .graph_state import DocumentPage, DocumentSegmentSummary, MindmapState

_DOCUMENT_PICKER_MESSAGE = """## Please select transcript document(s)

This Mindmap agent needs the full transcript/script to generate an exhaustive mindmap.

Use the **Documents** picker in the composer to select one or more transcript/script documents, then ask again.
"""


def _as_int(value: object, default: int) -> int:
    """
    Convert one tuning value to an integer with a safe fallback.

    Why this exists:
    - graph tuning values arrive as loosely typed scalars
    - the agent should degrade predictably when a field is blank or malformed

    How to use it:
    - pass the raw tuning value and the default business value
    - receive a best-effort integer without raising parsing errors
    """

    return int(value) if isinstance(value, (int, float)) else default


def _as_bool(value: object, default: bool = False) -> bool:
    """
    Convert one tuning value to a boolean with a safe fallback.

    Why this exists:
    - optional boolean tuning values may be absent in direct or older runs
    - small coercion helpers keep the business steps readable

    How to use it:
    - pass the raw tuning value and the fallback boolean
    - receive the original boolean only when the value is already typed
    """

    return value if isinstance(value, bool) else default


def _as_text(value: object) -> str:
    """
    Normalize one optional tuning or payload value to stripped text.

    Why this exists:
    - operator prompts and small runtime values should not leak `None` checks
      into every step
    - the agent prefers empty strings over ad hoc sentinel handling

    How to use it:
    - pass any optional scalar-like value
    - receive stripped text or the empty string
    """

    return value.strip() if isinstance(value, str) else ""


def _coerce_text(value: object) -> str:
    """
    Convert a payload field to plain text without raising validation errors.

    Why this exists:
    - runtime tool payloads may be dicts, Pydantic models, or partial objects
    - document-page parsing should stay defensive at the adapter boundary

    How to use it:
    - pass one raw field value from a runtime tool response
    - receive a string or the empty string when the field is not text
    """

    return value if isinstance(value, str) else ""


def _coerce_int(value: object) -> int | None:
    """
    Convert a payload field to an integer when possible.

    Why this exists:
    - filesystem pagination metadata should stay typed once it enters graph
      state
    - callers should not need repeated `isinstance` checks for every field

    How to use it:
    - pass one raw runtime-tool field
    - receive an integer or `None` when the value is missing or invalid
    """

    return int(value) if isinstance(value, int | float) else None


def _runtime_context_selected_uids(context: GraphNodeContext) -> list[str]:
    """
    Read the selected document uids from the bound runtime context.

    Why this exists:
    - the selected-document flow is the primary entry point for this agent
    - the runtime context shape should be touched in one place only

    How to use it:
    - call inside routing or document-resolution steps
    - the result is always a plain list, never `None`
    """

    runtime_context = getattr(context.binding, "runtime_context", None)
    raw_uids = getattr(runtime_context, "selected_document_uids", None)
    if not isinstance(raw_uids, list):
        return []
    return [uid.strip() for uid in raw_uids if isinstance(uid, str) and uid.strip()]


def _output_language(context: GraphNodeContext, detected: str | None) -> str:
    """
    Resolve the effective output language for summaries and mindmap labels.

    Why this exists:
    - operators may force a language, but request detection should still win
      when no explicit override was configured
    - keeping the policy centralized avoids prompt drift across steps

    How to use it:
    - pass the detected request language when available
    - receive one of `fr` or `en`
    """

    forced = _as_text(context.tuning_values.get("settings.output_language")) or "auto"
    if forced in {"fr", "en"}:
        return forced
    if detected in {"fr", "en"}:
        return detected
    return "en"


def _system_override(context: GraphNodeContext) -> str:
    """
    Return the optional operator prompt override for this agent.

    Why this exists:
    - the managed-agent form exposes one small override channel for operators
    - every model step should apply it consistently when present

    How to use it:
    - call before building a system prompt
    - append the returned text only when it is non-empty
    """

    return _as_text(context.tuning_values.get("prompts.system"))


def _top_k(context: GraphNodeContext) -> int:
    """
    Resolve the fallback search retrieval depth.

    Why this exists:
    - the legacy search path remains available behind an explicit opt-in flag
    - keeping the bound here isolates fallback-only retrieval tuning

    How to use it:
    - call only in search-fallback code paths
    - the value is clamped to the historic search bounds
    """

    return max(4, min(30, _as_int(context.tuning_values.get("settings.top_k"), 16)))


def _require_selected_documents(context: GraphNodeContext) -> bool:
    """
    Return whether the agent should require document-picker selection.

    Why this exists:
    - the selected-document mode is the default product behavior
    - the routing step should express the policy directly from managed tuning

    How to use it:
    - call during document-resolution before any fallback path is considered
    """

    return _as_bool(
        context.tuning_values.get("settings.require_selected_documents"),
        True,
    )


def _allow_search_fallback(context: GraphNodeContext) -> bool:
    """
    Return whether knowledge search may run as a secondary path.

    Why this exists:
    - exhaustive transcript mindmaps should not silently drop back to partial
      vector coverage
    - the fallback needs one explicit gate the operator can audit

    How to use it:
    - call only when no selected documents are available
    """

    return _as_bool(context.tuning_values.get("settings.allow_search_fallback"), False)


def _page_line_limit(context: GraphNodeContext) -> int:
    """
    Resolve the bounded filesystem line limit for one page read.

    Why this exists:
    - page size should be operator-tunable but still clamped to backend-safe
      bounds
    - every paginated read should use the same resolved limit

    How to use it:
    - call before invoking `read_file_page`
    - the result is always between 20 and 500 lines
    """

    return max(
        20,
        min(500, _as_int(context.tuning_values.get("settings.page_line_limit"), 120)),
    )


def _page_max_chars(context: GraphNodeContext) -> int:
    """
    Resolve the bounded character budget for one page read.

    Why this exists:
    - large transcript pages must stay bounded before entering the model path
    - the filesystem contract already exposes a safe upper bound we can mirror

    How to use it:
    - call before invoking `read_file_page`
    - the result is always between 4,000 and 50,000 characters
    """

    return max(
        4000,
        min(
            50000, _as_int(context.tuning_values.get("settings.page_max_chars"), 18000)
        ),
    )


def _max_pages_per_document(context: GraphNodeContext) -> int:
    """
    Resolve the per-document pagination safety limit.

    Why this exists:
    - the agent needs a hard stop even when a transcript is unexpectedly large
    - callers should not repeat the same clamping logic around each read loop

    How to use it:
    - call once before iterating one selected document
    - the result is always between 1 and 100 pages
    """

    return max(
        1,
        min(
            100,
            _as_int(context.tuning_values.get("settings.max_pages_per_document"), 20),
        ),
    )


def _max_selected_documents(context: GraphNodeContext) -> int:
    """
    Resolve the selected-document processing cap for one request.

    Why this exists:
    - a single composer turn may include many selected documents
    - the agent should fail soft by trimming scope rather than overloading the
      prompt budget

    How to use it:
    - call in the document-resolution step before storing selected uids
    - the result is always between 1 and 20 documents
    """

    return max(
        1,
        min(
            20, _as_int(context.tuning_values.get("settings.max_selected_documents"), 5)
        ),
    )


def _max_depth(context: GraphNodeContext) -> int:
    """
    Resolve the final mindmap depth cap.

    Why this exists:
    - downstream extraction and normalization both need the same policy value
    - keeping it centralized prevents prompt/config divergence

    How to use it:
    - call during extraction, refinement, and normalization
    """

    return max(2, min(6, _as_int(context.tuning_values.get("settings.max_depth"), 4)))


def _max_children_per_node(context: GraphNodeContext) -> int:
    """
    Resolve the final child-count cap for each mindmap node.

    Why this exists:
    - the visual payload should remain navigable in the frontend tree renderer
    - prompts and payload normalization should share one consistent limit

    How to use it:
    - call during extraction, refinement, and normalization
    """

    return max(
        2,
        min(
            10,
            _as_int(context.tuning_values.get("settings.max_children_per_node"), 6),
        ),
    )


def _include_evidence(context: GraphNodeContext) -> bool:
    """
    Return whether evidence links should be preserved in the final payload.

    Why this exists:
    - some teams want concise maps while others want grounded drill-down
    - one helper keeps the evidence policy shared across extraction stages

    How to use it:
    - call before normalization or prompt construction
    """

    return _as_bool(context.tuning_values.get("settings.include_evidence"), True)


def _is_final(state: MindmapState) -> bool:
    """
    Report whether a prior step already produced the final user response.

    Why this exists:
    - the graph runtime uses direct edges rather than conditional flow here
    - downstream nodes need a clean no-op check after picker guidance or errors

    How to use it:
    - guard early in every downstream step
    - return an empty `StepResult` when this function returns `True`
    """

    return bool((state.final_text or "").strip())


def _trim_text(text: str | None, limit: int) -> str:
    """
    Trim one text block to a bounded display or prompt budget.

    Why this exists:
    - segment summaries and evidence quotes should remain compact
    - repeated truncation logic would otherwise obscure the workflow steps

    How to use it:
    - pass optional text and a positive limit
    - receive a bounded string with an ellipsis only when trimming happened
    """

    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _slugify(label: str) -> str:
    """
    Convert one label into a stable node id slug.

    Why this exists:
    - the frontend mindmap renderer needs unique node ids
    - model-produced ids are often missing or too loose to trust directly

    How to use it:
    - pass one model-generated label or fallback token
    - receive a lowercase slug safe for JSON ids
    """

    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "node"


def _dedupe_key(hit: VectorSearchHit) -> str:
    """
    Build one stable deduplication key for fallback search hits.

    Why this exists:
    - fallback retrieval can surface the same logical snippet through multiple
      broad queries
    - mindmap prompts benefit from a compact, non-redundant evidence set

    How to use it:
    - call while folding search hits into a map keyed by source identity
    """

    if hit.uid:
        return f"uid:{hit.uid}|page:{hit.page}|section:{hit.section}"
    title = (hit.title or "").strip()
    file_name = (hit.file_name or "").strip()
    page = "" if hit.page is None else str(hit.page)
    section = (hit.section or "").strip()
    content_prefix = (hit.content or "")[:80]
    return f"meta:{title}|{file_name}|{page}|{section}|{content_prefix}"


def dedupe_hits(hits: Sequence[VectorSearchHit]) -> list[VectorSearchHit]:
    """
    Deduplicate fallback search hits while keeping the best-scoring variant.

    Why this exists:
    - coverage-oriented fallback queries intentionally overlap
    - the graph state should carry only the strongest variant for each snippet

    How to use it:
    - pass any hit sequence collected from multiple search calls
    - receive a compact list with one best hit per dedupe key
    """

    best_by_key: dict[str, VectorSearchHit] = {}
    for hit in hits:
        key = _dedupe_key(hit)
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = hit
            continue
        if hit.score is not None and (
            current.score is None or hit.score > current.score
        ):
            best_by_key[key] = hit
    return list(best_by_key.values())


def _compact_hits(hits: Sequence[VectorSearchHit], max_chars: int = 12000) -> str:
    """
    Render compact grounded evidence blocks for prompts and fallbacks.

    Why this exists:
    - search hits and document-summary pseudo-hits share one prompt shape
    - the extractor should not see an unbounded pile of source text

    How to use it:
    - pass the source hits already stored in state
    - receive a bounded multi-block string for prompt injection
    """

    blocks: list[str] = []
    total = 0
    for index, hit in enumerate(hits, start=1):
        locator_parts: list[str] = []
        if hit.file_name:
            locator_parts.append(hit.file_name)
        if hit.page is not None:
            locator_parts.append(f"p. {hit.page}")
        elif hit.section:
            locator_parts.append(f"§{hit.section}")
        locator = ", ".join(locator_parts) if locator_parts else "source"
        title = (hit.title or "").strip() or (hit.file_name or f"source {index}")
        content = _trim_text(hit.content, 900)
        block = (
            f"Source {index}\nTitle: {title}\nLocator: {locator}\nSnippet:\n{content}\n"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks).strip()


def _line_range(page: DocumentPage) -> str:
    """
    Convert page pagination metadata into a compact human-readable range.

    Why this exists:
    - segment summaries should preserve chronology and location
    - prompts and UI notes both benefit from one consistent range label

    How to use it:
    - pass one `DocumentPage`
    - receive a `Lx-Ly` style label or a coarse page fallback
    """

    if page.start_line is None and page.end_line is None:
        return f"page {page.page_index + 1}"
    if page.start_line is None:
        return f"L?-L{page.end_line}"
    if page.end_line is None:
        return f"L{page.start_line}-L?"
    return f"L{page.start_line}-L{page.end_line}"


def _normalize_page_payload(payload: object) -> dict[str, object]:
    """
    Normalize one runtime-tool page payload to a plain mapping.

    Why this exists:
    - `invoke_runtime_tool` may return dicts, Pydantic models, or similar
      objects depending on runtime plumbing
    - page parsing should work from one consistent mapping shape

    How to use it:
    - pass the raw result from `context.invoke_runtime_tool(...)`
    - receive a best-effort `dict[str, object]`
    """

    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="python")
    if hasattr(payload, "model_dump"):
        model_dump = getattr(payload, "model_dump")
        if callable(model_dump):
            dumped = model_dump(mode="python")
            if isinstance(dumped, dict):
                return dumped
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _pseudo_hit_from_summary(summary: DocumentSegmentSummary) -> VectorSearchHit:
    """
    Build one lightweight grounded source from a document segment summary.

    Why this exists:
    - the final graph output expects `VectorSearchHit`-shaped sources
    - selected-document mode still needs stable evidence indexes for the
      mindmap payload without keeping raw page text in state

    How to use it:
    - pass one persisted `DocumentSegmentSummary`
    - receive a small synthetic source entry suitable for prompts and output
    """

    return VectorSearchHit(
        uid=summary.document_uid,
        title=f"Document {summary.document_uid}",
        content=_trim_text(summary.summary, 900),
        file_name="preview.md",
        type="document-segment",
        page=summary.page_index + 1,
        section=summary.line_range,
        score=1.0,
    )


def _segment_summaries_to_text(
    summaries: Sequence[DocumentSegmentSummary],
    *,
    max_chars: int = 14000,
) -> str:
    """
    Render persisted segment summaries into a bounded digest-building prompt.

    Why this exists:
    - the agent should merge many bounded page summaries without concatenating
      raw transcript pages
    - one shared renderer keeps prompt structure consistent across turns

    How to use it:
    - pass the summaries already stored in graph state
    - receive a bounded text block ready for a digest model step
    """

    blocks: list[str] = []
    total = 0
    for summary in summaries:
        block = (
            f"Document: {summary.document_uid}\n"
            f"Segment: {summary.line_range}\n"
            f"Title: {summary.title}\n"
            f"Summary: {summary.summary}\n"
            f"Key points: {', '.join(summary.key_points) or '-'}\n"
            f"Actions: {', '.join(summary.actions) or '-'}\n"
            f"Risks: {', '.join(summary.risks) or '-'}\n"
            f"Notable terms: {', '.join(summary.notable_terms) or '-'}\n"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks).strip()


def _render_missing_transcript_response() -> str:
    """
    Render the fallback-search miss response for insufficient corpus coverage.

    Why this exists:
    - the strict selected-document path and the optional search path fail in
      different ways
    - the search miss should still return a direct, user-readable next step

    How to use it:
    - call from the render step when fallback search returned no useful hits
    """

    return (
        "## I could not find enough transcript content\n\n"
        "I did not find sufficient transcript or script material to build an "
        "exhaustive mindmap. Please select the transcript/script documents "
        "with the **Documents** picker and ask again."
    )


def _render_document_read_failure_response() -> str:
    """
    Render the response used when selected documents could not be read safely.

    Why this exists:
    - a selected-document run can fail after picker selection because the
      preview is missing, unauthorized, or empty
    - the user should get one clear remediation message rather than a raw error

    How to use it:
    - call from the render step when document reads produced no usable summary
    """

    return (
        "## I could not read enough document content\n\n"
        "The selected transcript/script documents did not yield enough readable "
        "preview content for an exhaustive mindmap. Please verify the selected "
        "documents and try again."
    )


def _fallback_outline(hits: Sequence[VectorSearchHit]) -> str:
    """
    Render a compact fallback outline when JSON mindmap generation fails.

    Why this exists:
    - the workflow should still return useful grounded content when the
      extraction payload is malformed
    - a short outline is safer than returning nothing after successful reads

    How to use it:
    - pass the best available grounded sources from state
    - receive a human-readable markdown fallback
    """

    lines = [
        "## Mindmap generation needs refinement",
        "",
        "I gathered enough transcript material, but I could not produce a reliable mindmap JSON payload this time.",
        "",
        "### Transcript highlights",
    ]
    for index, hit in enumerate(hits[:6], start=1):
        title = (hit.title or "").strip() or (hit.file_name or f"Source {index}")
        snippet = _trim_text(hit.content, 180)
        lines.append(f"- {title}: {snippet}")
    return "\n".join(lines)


class RequestAnalysis(BaseModel):
    detected_language: Literal["fr", "en", "unknown"] = Field(
        description="Detected language of the request."
    )
    normalized_request: str = Field(
        description="Short rewritten request used for downstream processing."
    )
    transcript_title_hint: str = Field(
        default="",
        description="Possible transcript title, project, or domain hint if present.",
    )


class MindMapEvidence(BaseModel):
    sourceIndex: int | None = None
    quote: str = ""


class MindMapNode(BaseModel):
    id: str = ""
    name: str = Field(..., min_length=1)
    summary: str = ""
    detail: str = ""
    evidence: list[MindMapEvidence] = Field(default_factory=list)
    children: list["MindMapNode"] = Field(default_factory=list)


class MindMapPresentation(BaseModel):
    initialDepth: int = 2
    layout: Literal["orthogonal", "radial"] = "orthogonal"
    focusMode: bool = True


class MindMapPayload(BaseModel):
    version: str = "1.0"
    title: str = Field(..., min_length=1)
    summary: str = ""
    root: MindMapNode
    presentation: MindMapPresentation = Field(default_factory=MindMapPresentation)


MindMapNode.model_rebuild()


def _normalize_evidence(
    evidence: Sequence[MindMapEvidence],
    *,
    max_source_index: int,
    include_evidence: bool,
) -> list[dict[str, object]]:
    """
    Filter model-generated evidence items to valid source indexes.

    Why this exists:
    - the frontend expects source indexes to point at actual `sources` entries
    - selected-document mode may carry fewer grounded sources than the model
      tries to cite

    How to use it:
    - pass the raw model evidence plus the number of available sources
    - receive a compact list of safe evidence payloads
    """

    if not include_evidence or max_source_index <= 0:
        return []
    normalized: list[dict[str, object]] = []
    for item in evidence:
        source_index = item.sourceIndex
        if not isinstance(source_index, int) or not (
            1 <= source_index <= max_source_index
        ):
            continue
        normalized.append(
            {
                "sourceIndex": source_index,
                "quote": _trim_text(item.quote, 220),
            }
        )
    return normalized[:3]


def _normalize_node(
    node: MindMapNode,
    *,
    fallback_id: str,
    seen_ids: set[str],
    depth: int,
    max_depth: int,
    max_children: int,
    max_source_index: int,
    include_evidence: bool,
) -> dict[str, object]:
    """
    Normalize one recursively nested mindmap node for frontend rendering.

    Why this exists:
    - model output is loosely structured and may contain duplicate ids or
      oversized child sets
    - the renderer benefits from one deterministic, bounded payload shape

    How to use it:
    - call from `normalize_mindmap_payload(...)`
    - pass the recursive traversal limits and seen-id set
    """

    raw_name = _trim_text(node.name, 80) or "Untitled topic"
    raw_id = _slugify(node.id or raw_name or fallback_id)
    final_id = raw_id
    suffix = 2
    while final_id in seen_ids:
        final_id = f"{raw_id}-{suffix}"
        suffix += 1
    seen_ids.add(final_id)

    children: list[dict[str, object]] = []
    if depth < max_depth:
        for index, child in enumerate(node.children[:max_children], start=1):
            children.append(
                _normalize_node(
                    child,
                    fallback_id=f"{final_id}-{index}",
                    seen_ids=seen_ids,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_children=max_children,
                    max_source_index=max_source_index,
                    include_evidence=include_evidence,
                )
            )

    return {
        "id": final_id,
        "name": raw_name,
        "summary": _trim_text(node.summary, 220),
        "detail": _trim_text(node.detail, 700),
        "evidence": _normalize_evidence(
            node.evidence,
            max_source_index=max_source_index,
            include_evidence=include_evidence,
        ),
        "children": children,
    }


def normalize_mindmap_payload(
    payload: MindMapPayload,
    *,
    max_depth: int,
    max_children: int,
    include_evidence: bool,
    max_source_index: int,
) -> dict[str, object]:
    """
    Normalize the model-produced payload to the frontend contract.

    Why this exists:
    - the frontend mindmap block expects bounded ids, child counts, and
      evidence indexes
    - keeping the shaping here lets prompts stay focused on business meaning

    How to use it:
    - pass the raw `MindMapPayload` plus rendering bounds
    - receive a stable JSON-serializable dict for the fenced response
    """

    seen_ids: set[str] = set()
    root = _normalize_node(
        payload.root,
        fallback_id="root",
        seen_ids=seen_ids,
        depth=1,
        max_depth=max_depth,
        max_children=max_children,
        max_source_index=max_source_index,
        include_evidence=include_evidence,
    )
    root["id"] = "root"
    seen_ids.add("root")
    initial_depth = max(1, min(max_depth, payload.presentation.initialDepth))
    return {
        "version": "1.0",
        "title": _trim_text(payload.title, 120) or "Mindmap",
        "summary": _trim_text(payload.summary, 320),
        "root": root,
        "presentation": {
            "initialDepth": initial_depth,
            "layout": payload.presentation.layout,
            "focusMode": bool(payload.presentation.focusMode),
        },
    }


def render_mindmap_markdown(
    payload: dict[str, object],
    *,
    coverage_warnings: Sequence[str] = (),
) -> str:
    """
    Render the final fenced `mindmap-json` response shown in chat.

    Why this exists:
    - the frontend already knows how to render mindmap payloads from fenced
      markdown
    - keeping the response assembly in one helper makes close-out notes and
      warning blocks consistent

    How to use it:
    - pass the normalized payload and any coverage warnings
    - receive the final markdown text stored in `state.final_text`
    """

    summary = str(payload.get("summary") or "").strip()
    root = payload.get("root") if isinstance(payload.get("root"), dict) else {}
    branch_names: list[str] = []
    if isinstance(root, dict):
        children = root.get("children")
        if isinstance(children, list):
            for child in children[:5]:
                if isinstance(child, dict) and isinstance(child.get("name"), str):
                    branch_names.append(child["name"].strip())

    notes = ""
    if branch_names:
        notes = "\n### Reading notes\n- Main themes: " + ", ".join(branch_names) + "."

    warning_block = ""
    if coverage_warnings:
        warning_lines = "\n".join(f"- {warning}" for warning in coverage_warnings)
        warning_block = f"\n### Coverage notes\n{warning_lines}\n"

    body = json.dumps(payload, ensure_ascii=True, indent=2)
    intro = (
        "## Mindmap generated from the selected transcript\n\n"
        "I read the selected transcript/script documents through paginated Knowledge "
        "Flow previews and generated a hierarchical mindmap. Use the interactive "
        "block below to zoom, pan, expand/collapse, and drill into topics.\n"
    )
    summary_text = f"\nSummary: {summary}\n" if summary else "\n"
    return (
        f"{intro}{summary_text}\n```mindmap-json\n{body}\n```\n{warning_block}{notes}\n"
    ).rstrip()


async def read_document_pages(
    context: GraphNodeContext,
    document_uid: str,
    *,
    page_line_limit: int,
    page_max_chars: int,
    max_pages: int,
) -> list[DocumentPage]:
    """
    Read one selected document through bounded filesystem pagination.

    Why this exists:
    - exhaustive transcript coverage needs sequential reads instead of vector
      relevance sampling
    - the helper centralizes pagination normalization and stop conditions

    How to use it:
    - pass the graph context plus one selected document uid and read bounds
    - continue summarization from the returned ordered page list
    """

    path = f"/corpus/documents/{document_uid}/preview.md"
    pages: list[DocumentPage] = []
    offset = 0

    for page_index in range(max_pages):
        raw_page = await context.invoke_runtime_tool(
            "read_file_page",
            {
                "path": path,
                "offset": offset,
                "limit": page_line_limit,
                "max_chars": page_max_chars,
            },
        )
        payload = _normalize_page_payload(raw_page)
        page = DocumentPage(
            document_uid=document_uid,
            path=_coerce_text(payload.get("path")) or path,
            page_index=page_index,
            start_line=_coerce_int(payload.get("start_line")),
            end_line=_coerce_int(payload.get("end_line")),
            total_lines=_coerce_int(payload.get("total_lines")),
            has_more=_as_bool(payload.get("has_more"), False),
            next_offset=_coerce_int(payload.get("next_offset")),
            truncated=_as_bool(payload.get("truncated"), False),
            content=_coerce_text(payload.get("content")).strip(),
        )
        pages.append(page)

        if not page.has_more:
            break
        if page.next_offset is None:
            break
        offset = page.next_offset

    return pages


async def _summarize_document_page(
    context: GraphNodeContext,
    page: DocumentPage,
) -> DocumentSegmentSummary:
    """
    Summarize one bounded transcript page for later digest merging.

    Why this exists:
    - the workflow must preserve chronology without concatenating full document
      previews into one large prompt
    - storing compact structured summaries keeps graph state JSON-friendly and
      bounded

    How to use it:
    - pass one `DocumentPage` returned by `read_document_pages(...)`
    - receive a compact `DocumentSegmentSummary`
    """

    line_range = _line_range(page)
    if context.model is None:
        return DocumentSegmentSummary(
            document_uid=page.document_uid,
            page_index=page.page_index,
            line_range=line_range,
            title=f"Segment {page.page_index + 1}",
            summary=_trim_text(page.content, 500),
        )

    system_prompt = (
        "Summarize this transcript/script segment for mindmap generation.\n\n"
        "Rules:\n"
        "- Use only the segment content.\n"
        "- Preserve chronology.\n"
        "- Extract key concepts, actions, decisions, risks, and transitions.\n"
        "- Keep labels short.\n"
        "- Do not invent missing context."
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Document UID: {page.document_uid}\n"
                f"Segment: {line_range}\n\n"
                f"Content:\n{page.content or '(empty)'}"
            )
        ),
    ]
    try:
        summary = await context.invoke_structured_model(
            DocumentSegmentSummary,
            messages,
            operation="mindmap_summarize_document_page",
        )
        return DocumentSegmentSummary.model_validate(summary)
    except Exception:
        return DocumentSegmentSummary(
            document_uid=page.document_uid,
            page_index=page.page_index,
            line_range=line_range,
            title=f"Segment {page.page_index + 1}",
            summary=_trim_text(page.content, 500),
        )


def _build_fallback_queries(request_text: str) -> list[str]:
    """
    Build a small deterministic fallback search query set.

    Why this exists:
    - the explicit search fallback should stay lightweight and avoid adding a
      second planning LLM call to the graph
    - broad deterministic queries are good enough for the fallback path

    How to use it:
    - pass the normalized user request
    - receive deduplicated coverage-oriented search queries
    """

    seed = " ".join(request_text.split()).strip()
    candidates = [
        seed,
        f"{seed} transcript script overview main themes",
        f"{seed} introduction conclusion key topics decisions action items",
    ]
    seen: set[str] = set()
    queries: list[str] = []
    for query in candidates:
        normalized = " ".join(query.split())
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            continue
        seen.add(lowered)
        queries.append(normalized)
    return queries or [seed]


async def _retrieve_fallback_hits(
    state: MindmapState,
    context: GraphNodeContext,
) -> tuple[list[VectorSearchHit], list[str]]:
    """
    Retrieve fallback search hits when no selected documents were provided.

    Why this exists:
    - search fallback is still supported, but only behind an explicit setting
    - isolating it here keeps the main document-reading step easy to follow

    How to use it:
    - call only when `state.use_search_fallback` is true
    - receive the deduplicated hits plus the queries that were executed
    """

    queries = _build_fallback_queries(state.latest_user_text)
    all_hits: list[VectorSearchHit] = []
    for query in queries:
        if not query.strip():
            continue
        result = await context.invoke_tool(
            TOOL_REF_KNOWLEDGE_SEARCH,
            {"query": query, "top_k": _top_k(context)},
        )
        all_hits.extend(list(result.sources))
        for block in result.blocks:
            block_kind = getattr(block.kind, "value", block.kind)
            if block_kind != "json" or not isinstance(block.data, dict):
                continue
            raw_hits = block.data.get("hits")
            if not isinstance(raw_hits, list):
                continue
            for raw_hit in raw_hits:
                if not isinstance(raw_hit, dict):
                    continue
                try:
                    all_hits.append(VectorSearchHit.model_validate(raw_hit))
                except (TypeError, ValueError):
                    continue
    deduped = dedupe_hits(all_hits)
    deduped.sort(key=lambda hit: (hit.score is None, -(hit.score or 0.0)))
    return deduped, queries


@typed_node(MindmapState)
async def analyze_request_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Normalize the user request and detect the output language.

    Why this exists:
    - later steps should reason over a compact normalized request rather than
      free-form user phrasing
    - language detection keeps summary and label prompts consistent

    How to use it:
    - this is the graph entry step
    - it stores the normalized request back into `latest_user_text`
    """

    context.emit_status("analyze_request", "Analyzing the transcript mapping request.")
    system_prompt = (
        "You analyze a request for a transcript-to-mindmap workflow.\n"
        "Return structured output only."
    )
    override = _system_override(context)
    if override:
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{override}"
    analysis = await structured_model_step(
        context,
        operation="mindmap_analyze_request",
        output_model=RequestAnalysis,
        system_prompt=system_prompt,
        user_prompt=state.latest_user_text,
        fallback_output={
            "detected_language": "unknown",
            "normalized_request": state.latest_user_text.strip(),
            "transcript_title_hint": "",
        },
    )
    detected = (
        analysis.detected_language if analysis.detected_language != "unknown" else None
    )
    normalized_request = (
        analysis.normalized_request.strip() or state.latest_user_text.strip()
    )
    return StepResult(
        state_update={
            "detected_language": detected,
            "output_language": _output_language(context, detected),
            "latest_user_text": normalized_request,
        }
    )


@typed_node(MindmapState)
async def resolve_selected_documents_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Resolve the selected-document routing mode for the current request.

    Why this exists:
    - the agent must prefer explicit document selection over search
    - the workflow needs one place to decide between selected-document mode,
      picker guidance, and the optional fallback path

    How to use it:
    - this step runs immediately after request analysis
    - downstream steps simply inspect the flags stored here
    """

    if _is_final(state):
        return StepResult()

    context.emit_status(
        "resolve_selected_documents",
        "Resolving selected documents from the runtime context.",
    )
    selected_uids = _runtime_context_selected_uids(context)
    max_selected = _max_selected_documents(context)
    coverage_warnings: list[str] = []
    if len(selected_uids) > max_selected:
        coverage_warnings.append(
            f"Processed only the first {max_selected} selected documents out of {len(selected_uids)}."
        )
        selected_uids = selected_uids[:max_selected]

    if selected_uids:
        return StepResult(
            state_update={
                "selected_document_uids": selected_uids,
                "coverage_warnings": coverage_warnings,
                "needs_document_selection": False,
                "use_search_fallback": False,
            }
        )

    if _allow_search_fallback(context) and not _require_selected_documents(context):
        return StepResult(
            state_update={
                "use_search_fallback": True,
                "needs_document_selection": False,
                "selected_document_uids": [],
            }
        )

    return StepResult(
        state_update={
            "final_text": _DOCUMENT_PICKER_MESSAGE,
            "needs_document_selection": True,
            "done_reason": "needs_document_selection",
            "selected_document_uids": [],
            "use_search_fallback": False,
        }
    )


@typed_node(MindmapState)
async def read_selected_documents_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Read selected transcript documents or execute the explicit fallback search.

    Why this exists:
    - selected-document mode needs bounded sequential reads and incremental page
      summarization
    - the graph keeps the legacy search path only as a guarded secondary mode

    How to use it:
    - this step follows document-resolution
    - it persists compact segment summaries or fallback search hits into state
    """

    if _is_final(state):
        return StepResult()

    if state.use_search_fallback:
        context.emit_status(
            "read_selected_documents",
            "No selected documents were provided; running explicit search fallback.",
        )
        hits, queries = await _retrieve_fallback_hits(state, context)
        return StepResult(
            state_update={
                "retrieval_queries": queries,
                "transcript_hits": [hit.model_dump() for hit in hits],
                "source_refs": [hit.model_dump() for hit in hits],
                "done_reason": None if hits else "no_transcript_hits",
            }
        )

    context.emit_status(
        "read_selected_documents",
        f"Reading {len(state.selected_document_uids)} selected document(s) through paginated previews.",
    )
    segment_summaries: list[DocumentSegmentSummary] = []
    source_refs: list[dict[str, object]] = []
    coverage_warnings = list(state.coverage_warnings)
    page_line_limit = _page_line_limit(context)
    page_max_chars = _page_max_chars(context)
    max_pages = _max_pages_per_document(context)

    for document_uid in state.selected_document_uids:
        try:
            pages = await read_document_pages(
                context,
                document_uid,
                page_line_limit=page_line_limit,
                page_max_chars=page_max_chars,
                max_pages=max_pages,
            )
        except Exception as exc:
            coverage_warnings.append(
                f"Could not read document `{document_uid}`: {type(exc).__name__}."
            )
            continue

        if not pages:
            coverage_warnings.append(
                f"Document `{document_uid}` returned no readable preview pages."
            )
            continue

        last_page = pages[-1]
        if (
            last_page.has_more
            and last_page.next_offset is not None
            and len(pages) >= max_pages
        ):
            coverage_warnings.append(
                f"Stopped reading document `{document_uid}` after {max_pages} pages for safety."
            )
        elif last_page.has_more and last_page.next_offset is None:
            coverage_warnings.append(
                f"Stopped reading document `{document_uid}` because pagination metadata had no next offset."
            )

        for page in pages:
            if not page.content:
                continue
            if page.truncated:
                coverage_warnings.append(
                    f"Document `{document_uid}` segment {_line_range(page)} was truncated by filesystem bounds."
                )
            summary = await _summarize_document_page(context, page)
            segment_summaries.append(summary)
            source_refs.append(_pseudo_hit_from_summary(summary).model_dump())

    done_reason = None if segment_summaries else "no_document_content"
    return StepResult(
        state_update={
            "document_segment_summaries": [
                summary.model_dump() for summary in segment_summaries
            ],
            "source_refs": source_refs,
            "coverage_warnings": coverage_warnings,
            "done_reason": done_reason,
        }
    )


@typed_node(MindmapState)
async def build_document_digest_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Merge selected-document summaries or fallback hits into one global digest.

    Why this exists:
    - the mindmap extractor should work from one coherent transcript digest
      rather than raw pages or scattered snippets
    - this keeps the workflow bounded while still preserving chronology

    How to use it:
    - this step runs after document reads or fallback retrieval
    - it stores the merged digest in `state.document_digest`
    """

    if _is_final(state):
        return StepResult()

    context.emit_status("build_document_digest", "Building a global transcript digest.")

    if state.use_search_fallback:
        hits = [VectorSearchHit.model_validate(raw) for raw in state.transcript_hits]
        if not hits:
            return StepResult(
                state_update={
                    "document_digest": "",
                    "done_reason": state.done_reason or "no_transcript_hits",
                }
            )
        evidence_text = _compact_hits(hits)
        system_prompt = (
            "You condense transcript evidence into a faithful digest for mindmap extraction.\n"
            "Preserve chronology, topic transitions, decisions, and action items.\n"
            "Preserve concrete section-level topics from the transcript. Keep implementation details, decisions, risks, action items, test scenarios, acceptance criteria, and roadmap items separate when present.\n"
            "Avoid merging distinct sections into generic categories.\n"
            "Do not invent material. Write concise bullet points in the requested language."
        )
        override = _system_override(context)
        if override:
            system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{override}"
        digest = await model_text_step(
            context,
            operation="mindmap_build_fallback_digest",
            system_prompt=system_prompt,
            user_prompt=(
                f"Output language: {state.output_language}\n\n"
                f"User request:\n{state.latest_user_text}\n\n"
                f"Transcript evidence:\n{evidence_text}"
            ),
            fallback_text=evidence_text,
        )
        return StepResult(state_update={"document_digest": digest.strip()})

    summaries = [
        DocumentSegmentSummary.model_validate(raw)
        for raw in state.document_segment_summaries
    ]
    if not summaries:
        return StepResult(
            state_update={
                "document_digest": "",
                "done_reason": state.done_reason or "no_document_content",
            }
        )

    digest_input = _segment_summaries_to_text(summaries)
    system_prompt = (
        "You merge transcript/script segment summaries into one global digest for mindmap generation.\n"
        "Rules:\n"
        "- Preserve chronology across segments and across documents.\n"
        "- Preserve concrete section-level topics from the transcript.\n"
        "- Keep implementation details, decisions, risks, action items, test scenarios, acceptance criteria, and roadmap items separate when present.\n"
        "- Avoid merging distinct sections into generic categories.\n"
        "- Highlight themes, transitions, decisions, actions, risks, and conclusions.\n"
        "- Keep labels concise and grounded.\n"
        "- Do not invent context missing from the summaries."
    )
    override = _system_override(context)
    if override:
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{override}"
    digest = await model_text_step(
        context,
        operation="mindmap_build_document_digest",
        system_prompt=system_prompt,
        user_prompt=(
            f"Output language: {state.output_language}\n\n"
            f"User request:\n{state.latest_user_text}\n\n"
            f"Segment summaries:\n{digest_input}"
        ),
        fallback_text=digest_input,
    )
    return StepResult(state_update={"document_digest": digest.strip()})


@typed_node(MindmapState)
async def extract_mindmap_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Generate the first structured mindmap draft from the global digest.

    Why this exists:
    - the extractor turns the merged transcript digest into the stable JSON
      contract expected by the frontend renderer
    - separating extraction from refinement gives the model one smaller prompt
      at each stage

    How to use it:
    - this step runs after digest generation
    - it stores the raw draft payload in `state.mindmap_payload`
    """

    if _is_final(state):
        return StepResult()

    if not (state.document_digest or "").strip():
        return StepResult(
            state_update={
                "done_reason": state.done_reason or "mindmap_generation_failed"
            }
        )

    context.emit_status("extract_mindmap", "Extracting a first mindmap structure.")
    hits = [VectorSearchHit.model_validate(raw) for raw in state.source_refs]
    system_prompt = load_agent_prompt_markdown(
        package="fred_agents.mindmap",
        file_name="extract_mindmap.md",
    )
    override = _system_override(context)
    if override:
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{override}"
    payload = await structured_model_step(
        context,
        operation="mindmap_extract_mindmap",
        output_model=MindMapPayload,
        system_prompt=system_prompt,
        user_prompt=(
            f"User request:\n{state.latest_user_text}\n\n"
            f"Output language: {state.output_language}\n"
            f"Maximum depth: {_max_depth(context)}\n"
            f"Maximum children per node: {_max_children_per_node(context)}\n"
            f"Include evidence: {_include_evidence(context)}\n\n"
            f"Transcript digest:\n{state.document_digest or '(empty)'}\n\n"
            f"Grounded supporting summaries:\n{_compact_hits(hits)}"
        ),
        fallback_output={
            "version": "1.0",
            "title": "Transcript mindmap",
            "summary": "Fallback transcript overview.",
            "root": {
                "id": "root",
                "name": "Transcript",
                "summary": "Transcript overview",
                "detail": "The transcript was processed but the first mindmap extraction fell back to a minimal structure.",
                "evidence": [],
                "children": [],
            },
            "presentation": {
                "initialDepth": min(2, _max_depth(context)),
                "layout": "orthogonal",
                "focusMode": True,
            },
        },
    )
    return StepResult(state_update={"mindmap_payload": payload.model_dump()})


@typed_node(MindmapState)
async def refine_mindmap_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Refine and normalize the first draft before rendering.

    Why this exists:
    - a second pass improves hierarchy quality while the normalizer enforces the
      frontend-safe contract
    - this is the last model step before markdown rendering

    How to use it:
    - this step runs after extraction
    - it writes the normalized payload back into `state.mindmap_payload`
    """

    if _is_final(state):
        return StepResult()

    raw_payload = state.mindmap_payload or {}
    if not raw_payload:
        return StepResult(
            state_update={
                "done_reason": state.done_reason or "mindmap_generation_failed"
            }
        )

    context.emit_status("refine_mindmap", "Refining the mindmap structure.")
    hits = [VectorSearchHit.model_validate(raw) for raw in state.source_refs]
    system_prompt = load_agent_prompt_markdown(
        package="fred_agents.mindmap",
        file_name="refine_mindmap.md",
    )
    override = _system_override(context)
    if override:
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{override}"
    refined = await structured_model_step(
        context,
        operation="mindmap_refine_mindmap",
        output_model=MindMapPayload,
        system_prompt=system_prompt,
        user_prompt=(
            f"User request:\n{state.latest_user_text}\n\n"
            f"Output language: {state.output_language}\n"
            f"Maximum depth: {_max_depth(context)}\n"
            f"Maximum children per node: {_max_children_per_node(context)}\n"
            f"Include evidence: {_include_evidence(context)}\n\n"
            f"Current mindmap draft:\n{json.dumps(raw_payload, ensure_ascii=True, indent=2)}\n\n"
            f"Transcript digest:\n{state.document_digest or '(empty)'}\n\n"
            f"Grounded supporting summaries:\n{_compact_hits(hits, max_chars=9000)}"
        ),
        fallback_output=raw_payload,
    )
    normalized = normalize_mindmap_payload(
        refined,
        max_depth=_max_depth(context),
        max_children=_max_children_per_node(context),
        include_evidence=_include_evidence(context),
        max_source_index=len(hits),
    )
    return StepResult(state_update={"mindmap_payload": normalized})


@typed_node(MindmapState)
async def render_response_step(
    state: MindmapState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Render the final markdown response for chat.

    Why this exists:
    - the frontend renderer consumes a fenced `mindmap-json` payload rather than
      a raw Python object
    - this step also translates terminal failure states into user-readable
      messages

    How to use it:
    - this is the final graph node
    - it always writes the user-facing text into `state.final_text`
    """

    context.emit_status("render_response", "Rendering the response.")

    if _is_final(state) and state.done_reason == "needs_document_selection":
        return StepResult(state_update={"final_text": state.final_text})

    if state.done_reason == "no_transcript_hits":
        return StepResult(
            state_update={"final_text": _render_missing_transcript_response()}
        )

    if state.done_reason == "no_document_content":
        return StepResult(
            state_update={"final_text": _render_document_read_failure_response()}
        )

    payload = state.mindmap_payload
    if not isinstance(payload, dict):
        hits = [VectorSearchHit.model_validate(raw) for raw in state.source_refs]
        return StepResult(state_update={"final_text": _fallback_outline(hits)})

    _ = load_agent_prompt_markdown(
        package="fred_agents.mindmap",
        file_name="render_response.md",
    )
    final_text = render_mindmap_markdown(
        payload,
        coverage_warnings=state.coverage_warnings,
    )
    if state.node_error:
        final_text = (
            f"{final_text}\n\n### Note\n"
            "The workflow completed with an internal recovery path, so please review "
            "the generated structure before using it as a presentation outline."
        )
    return StepResult(
        state_update={"final_text": final_text, "done_reason": "completed"}
    )
