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
Graph steps for the document-comparison agent.

The pipeline is deterministic — the LLM only *judges* paired passages, it never
drives retrieval. The targeted ``similarity_search`` MCP tool does the structural
work: pull the salient passages of document A for the user's focus, then for each
one find its closest passage in document B, then classify the pair.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fred_core.store import VectorSearchHit
from fred_sdk import (
    GraphNodeContext,
    StepResult,
    structured_model_step,
    typed_node,
)
from pydantic import BaseModel

from .graph_state import ComparisonState

_PICKER_MESSAGE: dict[str, str] = {
    "en": """## Please select two documents to compare

This agent compares **two** documents and reports what agrees, what contradicts,
and what is missing between them.

Use the **Documents** picker in the composer to select two documents (for example a
contract and its amendment, a document and a reference standard, or two versions of
the same file), then ask again — optionally naming the angle you care about.
""",
    "fr": """## Sélectionnez deux documents à comparer

Cet agent compare **deux** documents et indique ce qui concorde, ce qui se contredit
et ce qui manque entre eux.

Utilisez le sélecteur **Documents** du composer pour choisir deux documents (par
exemple un contrat et son avenant, un document et un référentiel, ou deux versions
d'un même fichier), puis reposez la question — en précisant éventuellement l'angle
qui vous intéresse.
""",
}

_NO_ANCHORS_MESSAGE: dict[str, str] = {
    "en": """## Nothing to compare

No passages could be retrieved from the first document for your request. Try a more
specific instruction, or check that the selected documents are indexed.
""",
    "fr": """## Rien à comparer

Aucun passage n'a pu être extrait du premier document pour votre demande. Essayez une
instruction plus précise, ou vérifiez que les documents sélectionnés sont bien indexés.
""",
}

#: User-visible labels of the deterministic report, per language.
_REPORT_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Document comparison",
        "intro": "Compared **{a}** against **{b}** for your request.",
        "extra": "> Note: {n} extra selected document(s) ignored — this agent compares the first two.",
        "contradictions": "Contradictions",
        "agreements": "Agreements",
        "gaps": "Gaps",
        "none": "_None._",
        "no_match": "No close passage found in document B.",
    },
    "fr": {
        "title": "Comparaison de documents",
        "intro": "Comparaison de **{a}** et **{b}** selon votre demande.",
        "extra": "> Note : {n} document(s) sélectionné(s) supplémentaire(s) ignoré(s) — cet agent compare les deux premiers.",
        "contradictions": "Contradictions",
        "agreements": "Concordances",
        "gaps": "Lacunes",
        "none": "_Aucune._",
        "no_match": "Aucun passage proche trouvé dans le document B.",
    },
}

#: Transient SSE status labels, per language.
_STATUS_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "resolve": "Resolving the selected documents.",
        "anchors": "Selecting the relevant passages of document A.",
        "compare": "Finding the matching passages in document B.",
        "judge": "Classifying matches (agree / contradict / gap).",
        "render": "Composing the comparison report.",
    },
    "fr": {
        "resolve": "Résolution des documents sélectionnés.",
        "anchors": "Sélection des passages pertinents du document A.",
        "compare": "Recherche des passages correspondants dans le document B.",
        "judge": "Classement des correspondances (concordance / contradiction / lacune).",
        "render": "Composition du rapport de comparaison.",
    },
}

_FRENCH_MARKERS = (
    " le ",
    " la ",
    " les ",
    " des ",
    " une ",
    " un ",
    " est ",
    " et ",
    " que ",
    " qui ",
    " dans ",
    " sur ",
    " avec ",
    " ce ",
    " ces ",
    " du ",
    " quel ",
    " quelle ",
    " entre ",
    " versions ",
    " indique ",
    " concorde ",
)


# ---------------------------------------------------------------------------
# Tuning + runtime-context helpers
# ---------------------------------------------------------------------------


def _as_int(value: object, default: int) -> int:
    """Convert a loosely-typed tuning value to int with a safe fallback."""
    return int(value) if isinstance(value, (int, float)) else default


def _coerce_text(value: object) -> str:
    """Return a stripped string, or '' for any non-string / blank value."""
    return value.strip() if isinstance(value, str) else ""


def _anchor_count(context: GraphNodeContext) -> int:
    """Number of A-passages compared against B (clamped to the field bounds)."""
    return max(
        2, min(20, _as_int(context.tuning_values.get("settings.anchor_count"), 8))
    )


def _runtime_context_selected_uids(context: GraphNodeContext) -> list[str]:
    """Read the document uids selected in the Documents picker (never None)."""
    runtime_context = getattr(context.binding, "runtime_context", None)
    raw_uids = getattr(runtime_context, "selected_document_uids", None)
    if not isinstance(raw_uids, list):
        return []
    return [uid.strip() for uid in raw_uids if isinstance(uid, str) and uid.strip()]


def _is_final(state: ComparisonState) -> bool:
    """A node already produced the user-facing text (guidance / early exit)."""
    return bool(state.final_text)


def _detect_language(text: str) -> str:
    """Best-effort fr/en detection from the user's text (defaults to English)."""
    lowered = f" {text.lower()} "
    if any(marker in lowered for marker in _FRENCH_MARKERS):
        return "fr"
    if any(ch in text for ch in "éèêëàâùûïîôçœ"):
        return "fr"
    return "en"


def _runtime_language(context: GraphNodeContext) -> str | None:
    """The UI-declared language from the runtime context, if fr/en."""
    runtime_context = getattr(context.binding, "runtime_context", None)
    lang = getattr(runtime_context, "language", None)
    if isinstance(lang, str) and lang[:2].lower() in ("fr", "en"):
        return lang[:2].lower()
    return None


def _resolve_language(state: ComparisonState, context: GraphNodeContext) -> str:
    """Resolve output language: tuning override → UI language → detect from question."""
    tuning = _coerce_text(context.tuning_values.get("settings.output_language")).lower()
    if tuning in ("fr", "en"):
        return tuning
    return _runtime_language(context) or _detect_language(state.latest_user_text)


def _state_language(state: ComparisonState) -> str:
    """The language stored on state, falling back to detection from the question."""
    return (
        state.language
        if state.language in ("fr", "en")
        else _detect_language(state.latest_user_text)
    )


def _doc_label(hit: dict[str, object], fallback: str) -> str:
    """Human-readable document name (file name → title → uid fallback)."""
    return (
        _coerce_text(hit.get("file_name")) or _coerce_text(hit.get("title")) or fallback
    )


# ---------------------------------------------------------------------------
# similarity_search MCP tool (exposed by the Knowledge Flow Text server)
# ---------------------------------------------------------------------------


def _normalize_hits(raw: object) -> list[dict[str, object]]:
    """
    Normalize a ``similarity_search`` tool result to a list of plain hit dicts.

    ``invoke_runtime_tool`` may hand back a list, a Pydantic model, or a wrapper
    mapping depending on runtime plumbing; this returns one consistent shape.
    """
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="python")
    items: object = raw
    if isinstance(raw, dict):
        items = []
        for key in ("hits", "results", "sources", "data"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
    if not isinstance(items, list):
        return []
    hits: list[dict[str, object]] = []
    for item in items:
        if isinstance(item, BaseModel):
            item = item.model_dump(mode="python")
        if isinstance(item, dict):
            hits.append(item)
    return hits


async def _similarity_search(
    context: GraphNodeContext,
    *,
    anchor: str,
    document_uid: str,
    pool: int,
) -> list[dict[str, object]]:
    """Return the best passages of one document for the anchor, best-first.

    We pass ``document_uids=[document_uid]`` as a hint, but the runtime's
    context-aware tool widens the scope to the whole Documents-picker selection
    (both documents being compared carry the same library tag). So we request a
    wider ``pool`` and re-filter client-side to the requested document by its
    ``uid`` — correct whether or not the runtime honours per-call scoping.
    """
    if not anchor:
        return []
    raw = await context.invoke_runtime_tool(
        "similarity_search",
        {
            "anchor": anchor,
            "document_uids": [document_uid],
            "top_k": pool,
            "rerank": True,
        },
    )
    return [hit for hit in _normalize_hits(raw) if hit.get("uid") == document_uid]


# ---------------------------------------------------------------------------
# LLM judge (the only place the model is used)
# ---------------------------------------------------------------------------


class PairVerdict(BaseModel):
    relation: Literal["concordance", "contradiction", "lacune"]
    note: str = ""


def _judge_system_prompt(context: GraphNodeContext, language: str) -> str:
    lang_name = "French" if language == "fr" else "English"
    base = (
        "You compare two document passages that a targeted similarity search paired "
        "together. Decide the relation between passage A (from the source document) "
        "and passage B (from the compared document):\n"
        "- concordance: they agree / state the same thing;\n"
        "- contradiction: they disagree on a fact, value, version, or claim;\n"
        "- lacune: B does not actually address what A states.\n"
        f"Write the note strictly in {lang_name}, one short sentence."
    )
    override = _coerce_text(context.tuning_values.get("prompts.system"))
    return f"{base}\n\n{override}" if override else base


def _judge_user_prompt(anchor_text: str, match_text: str) -> str:
    return f"Passage A:\n{anchor_text}\n\nPassage B:\n{match_text}"


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


@typed_node(ComparisonState)
async def resolve_documents_step(
    state: ComparisonState, context: GraphNodeContext
) -> StepResult:
    """Resolve A and B from the picker selection (need at least two documents)."""
    language = _resolve_language(state, context)
    context.emit_status("resolve_documents", _STATUS_STRINGS[language]["resolve"])
    uids = _runtime_context_selected_uids(context)
    if len(uids) < 2:
        return StepResult(
            state_update={
                "needs_document_selection": True,
                "final_text": _PICKER_MESSAGE[language],
                "done_reason": "needs_document_selection",
                "language": language,
            }
        )
    return StepResult(
        state_update={
            "doc_a_uid": uids[0],
            "doc_b_uid": uids[1],
            "extra_document_uids": uids[2:],
            "language": language,
        }
    )


@typed_node(ComparisonState)
async def pull_anchors_step(
    state: ComparisonState, context: GraphNodeContext
) -> StepResult:
    """Pull the salient passages of document A for the user's request (anchors)."""
    if _is_final(state) or not state.doc_a_uid:
        return StepResult()
    language = _state_language(state)
    context.emit_status("pull_anchors", _STATUS_STRINGS[language]["anchors"])
    anchor_count = _anchor_count(context)
    # Over-fetch (scope is widened by the runtime, then filtered to A), keep top N.
    hits = await _similarity_search(
        context,
        anchor=state.latest_user_text,
        document_uid=state.doc_a_uid,
        pool=max(anchor_count * 3, 12),
    )
    if not hits:
        return StepResult(
            state_update={
                "final_text": _NO_ANCHORS_MESSAGE[language],
                "done_reason": "no_anchors",
            }
        )
    return StepResult(
        state_update={
            "anchors": hits[:anchor_count],
            "doc_a_name": _doc_label(hits[0], state.doc_a_uid),
        }
    )


@typed_node(ComparisonState)
async def compare_pairs_step(
    state: ComparisonState, context: GraphNodeContext
) -> StepResult:
    """For each A-passage, find its closest passage in document B (top_k=1)."""
    if _is_final(state) or not state.doc_b_uid:
        return StepResult()
    context.emit_status(
        "compare_pairs", _STATUS_STRINGS[_state_language(state)]["compare"]
    )
    doc_b_uid = state.doc_b_uid

    async def _match(anchor: dict[str, object]) -> dict[str, object]:
        # Over-fetch so B passages survive the self-match to A, then take the best B.
        hits = await _similarity_search(
            context,
            anchor=_coerce_text(anchor.get("content")),
            document_uid=doc_b_uid,
            pool=10,
        )
        best = hits[0] if hits else None
        return {"anchor": anchor, "match": best}

    pairs = await asyncio.gather(*[_match(anchor) for anchor in state.anchors])
    matches = [pair["match"] for pair in pairs if isinstance(pair["match"], dict)]
    doc_b_name = _doc_label(matches[0], doc_b_uid) if matches else doc_b_uid
    return StepResult(
        state_update={
            "pairs": list(pairs),
            "source_refs": matches,
            "doc_b_name": doc_b_name,
        }
    )


@typed_node(ComparisonState)
async def judge_pairs_step(
    state: ComparisonState, context: GraphNodeContext
) -> StepResult:
    """Classify each pair: concordance / contradiction / lacune (the LLM judges)."""
    if _is_final(state):
        return StepResult()
    language = _state_language(state)
    context.emit_status("judge_pairs", _STATUS_STRINGS[language]["judge"])

    async def _judge(pair: dict[str, object]) -> dict[str, object]:
        anchor = pair.get("anchor")
        anchor_text = _coerce_text(
            anchor.get("content") if isinstance(anchor, dict) else None
        )
        match = pair.get("match")
        match_text = _coerce_text(
            match.get("content") if isinstance(match, dict) else None
        )
        if not match_text:
            return {
                "relation": "lacune",
                "note": _REPORT_STRINGS[language]["no_match"],
                "anchor": anchor_text,
                "match": "",
            }
        verdict = await structured_model_step(
            context,
            operation="comparison_judge_pair",
            output_model=PairVerdict,
            system_prompt=_judge_system_prompt(context, language),
            user_prompt=_judge_user_prompt(anchor_text, match_text),
            fallback_output={"relation": "concordance", "note": ""},
        )
        return {
            "relation": verdict.relation,
            "note": verdict.note,
            "anchor": anchor_text,
            "match": match_text,
        }

    verdicts = await asyncio.gather(*[_judge(pair) for pair in state.pairs])
    return StepResult(state_update={"verdicts": list(verdicts)})


@typed_node(ComparisonState)
async def render_report_step(
    state: ComparisonState, context: GraphNodeContext
) -> StepResult:
    """Compose the deterministic markdown comparison report."""
    if _is_final(state):
        return StepResult()
    context.emit_status(
        "render_report", _STATUS_STRINGS[_state_language(state)]["render"]
    )
    return StepResult(
        state_update={"final_text": _render_markdown(state), "done_reason": "completed"}
    )


# ---------------------------------------------------------------------------
# Report rendering (pure, deterministic — easy to test offline)
# ---------------------------------------------------------------------------


def _short(value: object, limit: int = 160) -> str:
    text = " ".join(_coerce_text(value).split())
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _render_markdown(state: ComparisonState) -> str:
    strings = _REPORT_STRINGS[_state_language(state)]
    doc_a = state.doc_a_name or state.doc_a_uid or "A"
    doc_b = state.doc_b_name or state.doc_b_uid or "B"

    grouped: dict[str, list[dict[str, object]]] = {
        "contradiction": [],
        "concordance": [],
        "lacune": [],
    }
    for verdict in state.verdicts:
        relation = verdict.get("relation")
        if isinstance(relation, str) and relation in grouped:
            grouped[relation].append(verdict)

    lines: list[str] = [
        f"# {strings['title']}",
        "",
        strings["intro"].format(a=doc_a, b=doc_b),
        "",
    ]
    if state.extra_document_uids:
        lines.append(strings["extra"].format(n=len(state.extra_document_uids)))
        lines.append("")

    def section(title: str, items: list[dict[str, object]]) -> None:
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if not items:
            lines.append(strings["none"])
            lines.append("")
            return
        for item in items:
            note = _coerce_text(item.get("note"))
            anchor = _short(item.get("anchor"))
            match = _short(item.get("match"))
            if match:
                lines.append(
                    f"- **A:** {anchor} — **B:** {match}{f' — {note}' if note else ''}"
                )
            else:
                lines.append(f"- **A:** {anchor}{f' — {note}' if note else ''}")
        lines.append("")

    section(strings["contradictions"], grouped["contradiction"])
    section(strings["agreements"], grouped["concordance"])
    section(strings["gaps"], grouped["lacune"])
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "PairVerdict",
    "resolve_documents_step",
    "pull_anchors_step",
    "compare_pairs_step",
    "judge_pairs_step",
    "render_report_step",
]


def build_sources(state: ComparisonState) -> tuple[VectorSearchHit, ...]:
    """Validate the collected B-matches into grounded sources (skip malformed)."""
    sources: tuple[VectorSearchHit, ...] = ()
    for raw in state.source_refs:
        try:
            sources = (*sources, VectorSearchHit.model_validate(raw))
        except (ValueError, TypeError):
            continue
    return sources
