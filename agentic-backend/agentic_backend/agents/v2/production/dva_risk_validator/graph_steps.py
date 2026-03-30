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

"""Business steps for DVA Risk Validator graph workflow."""

from __future__ import annotations

import re
from typing import Literal, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agentic_backend.core.agents.v2 import (
    GraphNodeContext,
    HumanInputRequest,
    ToolContentKind,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    StepResult,
    typed_node,
)
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

from .graph_state import CitationSource, DVARiskValidatorState, RiskEvidence, RiskRecord
from .prompt_loader import load_dva_risk_validator_prompt
from .reporting import (
    blocker_status_for_risk,
    render_risk_index_json,
    render_validation_report,
    treatment_status_for_risk,
)
from .session_scope import merge_session_scope

_GRAPH_EXTRACT_PROMPT = load_dva_risk_validator_prompt(
    "dva_risk_validator_graph_extract_system_prompt.md"
)
_GRAPH_RECOMMEND_PROMPT = load_dva_risk_validator_prompt(
    "dva_risk_validator_graph_recommend_system_prompt.md"
)

_RISK_TABLE_QUERIES = (
    "risk table DVA risk register mitigations owner target date",
    "risks and mitigations risk assessment matrix",
    "table des risques registre des risques mesures de mitigation",
    "analyse des risques matrice des risques propriétaire date cible",
)


class ExtractedRisks(BaseModel):
    """Structured extraction for ordered source risk rows."""

    risks: list[str] = Field(default_factory=list)


@typed_node(DVARiskValidatorState)
async def route_or_start_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Route any user request into the DVA validation workflow.

    Why this exists:
    - keeps the graph entry explicit for model-operation routing and future branching

    How to use:
    - use as entry node in the workflow, then continue to max-risk collection
    """

    context.emit_status("route_or_start", "Starting DVA risk validation workflow.")
    return StepResult(route_key="start")


@typed_node(DVARiskValidatorState)
async def ask_max_risk_count_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Collect and validate the maximum number of risks to produce.

    Why this exists:
    - the workflow must enforce an explicit user-chosen cap with a strict `<=30` rule

    How to use:
    - place this near the start of the graph before extraction and enrichment
    """

    if state.requested_max_risks is not None and 1 <= state.requested_max_risks <= 30:
        return StepResult(route_key="valid")

    response = await context.request_human_input(
        HumanInputRequest(
            stage="risk_count",
            title="Maximum risk count",
            question=(
                "How many risks should I include in the report? "
                "Please provide a number between 1 and 30."
            ),
            free_text=True,
        )
    )

    requested = _extract_requested_risk_count(response)
    if requested is None:
        return StepResult(route_key="retry")

    if requested > 30:
        return StepResult(
            state_update={
                "final_text": (
                    "Requested maximum risk count is too large. "
                    "Please provide a number below 30."
                )
            },
            route_key="retry",
        )

    return StepResult(
        state_update={"requested_max_risks": requested},
        route_key="valid",
    )


@typed_node(DVARiskValidatorState)
async def locate_risk_table_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Locate whether the DVA contains a risk table using bilingual retrieval probes.

    Why this exists:
    - risk-table presence is mandatory before extracting ordered source risks

    How to use:
    - call early; route to HITL section hint when confidence is weak
    """

    del state
    context.emit_status("locate_risk_table", "Searching DVA risk table evidence.")
    for query in _RISK_TABLE_QUERIES:
        result = await context.invoke_tool(
            TOOL_REF_KNOWLEDGE_SEARCH,
            {
                "query": query,
                "top_k": 6,
            },
        )
        if _result_contains_risk_table_signal(result):
            return StepResult(
                route_key="found", state_update={"risk_table_located": True}
            )
    return StepResult(route_key="missing", state_update={"risk_table_located": False})


@typed_node(DVARiskValidatorState)
async def maybe_ask_risk_section_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Ask user for risk section hint when automatic risk-table location failed.

    Why this exists:
    - workflow must use HITL when it cannot confidently identify the risk table

    How to use:
    - place this immediately after locate step on the missing branch
    """

    if state.risk_table_located:
        return StepResult(route_key="continue")

    response = await context.request_human_input(
        HumanInputRequest(
            stage="risk_section",
            title="Risk section hint",
            question=(
                "I could not confidently locate the DVA risk table. "
                "Which section contains the listed risks?"
            ),
            free_text=True,
        )
    )
    section_hint = _extract_text_answer(response)
    if not section_hint:
        return StepResult(route_key="continue")
    return StepResult(
        state_update={"risk_section_hint": section_hint}, route_key="continue"
    )


@typed_node(DVARiskValidatorState)
async def extract_source_risks_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Extract source risks in source order using retrieval + structured parsing.

    Why this exists:
    - report order must start with DVA-native risks in original source order

    How to use:
    - run after locating the risk table and optional HITL section hint
    """

    query = _build_extraction_query(state.risk_section_hint)
    result = await context.invoke_tool(
        TOOL_REF_KNOWLEDGE_SEARCH,
        {
            "query": query,
            "top_k": 12,
        },
    )
    raw_text = _collect_result_text(result)

    extracted = await _extract_risk_titles(raw_text, context)
    if not extracted:
        extracted = [
            "Risk register entry could not be extracted automatically; infer from DVA context"
        ]

    source_risks = [
        RiskRecord(
            risk_id=f"R-{index:02d}",
            title=title,
            risk_type="Source",
            source_order=index,
            priority=_priority_for_position(index),
            evidence=RiskEvidence(),
        )
        for index, title in enumerate(extracted, start=1)
    ]

    citations = _collect_citation_sources(result)
    return StepResult(
        state_update={
            "source_risks": source_risks,
            "all_risks": source_risks,
            "sources": citations,
        }
    )


@typed_node(DVARiskValidatorState)
async def enrich_to_requested_count_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Append inferred risks when user-requested count exceeds extracted source risks.

    Why this exists:
    - workflow must complete to requested count while keeping source risks first

    How to use:
    - run after extraction and before per-risk coverage/treatment validation
    """

    del context
    target = state.requested_max_risks or len(state.source_risks)
    if target <= len(state.source_risks):
        return StepResult(state_update={"all_risks": list(state.source_risks)})

    all_risks = list(state.source_risks)
    next_index = len(all_risks) + 1
    while len(all_risks) < target:
        all_risks.append(
            RiskRecord(
                risk_id=f"R-{next_index:02d}",
                title=f"Inferred contextual risk {next_index}",
                risk_type="Inferred",
                source_order=next_index,
                priority=_priority_for_position(next_index),
                evidence=RiskEvidence(
                    notes=(
                        "This risk is inferred from domain context because the "
                        "requested count exceeds extracted source rows."
                    )
                ),
            )
        )
        next_index += 1

    return StepResult(state_update={"all_risks": all_risks})


@typed_node(DVARiskValidatorState)
async def retrieve_coverage_evidence_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Retrieve per-risk coverage snippets from DVA scope and map numeric citations.

    Why this exists:
    - every material claim must map to evidence or explicit no-evidence marker

    How to use:
    - run after risk list finalization, before treatment validation
    """

    all_risks = list(state.all_risks)
    sources = list(state.sources)
    source_index = {source.index: source for source in sources}
    max_index = max(source_index.keys(), default=0)

    for idx, risk in enumerate(all_risks):
        search_result = await context.invoke_tool(
            TOOL_REF_KNOWLEDGE_SEARCH,
            {
                "query": f"{risk.title} treatment mitigation owner target date",
                "top_k": 5,
            },
        )
        risk_text = _collect_result_text(search_result)

        new_sources = _collect_citation_sources(search_result)
        for source in new_sources:
            if source.index in source_index:
                continue
            max_index += 1
            source_index[max_index] = source.model_copy(update={"index": max_index})

        citation = max(source_index.keys(), default=1)
        coverage_ref = _derive_coverage_reference(
            risk_title=risk.title,
            risk_text=risk_text,
            search_result=search_result,
        )
        risk.evidence.coverage_ref = coverage_ref
        risk.evidence.coverage_citation = (
            citation if coverage_ref != "NO EVIDENCE FOUND" else None
        )
        all_risks[idx] = risk

    ordered_sources = [source_index[key] for key in sorted(source_index.keys())]
    return StepResult(state_update={"all_risks": all_risks, "sources": ordered_sources})


@typed_node(DVARiskValidatorState)
async def validate_treatment_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Validate treatment completeness and blocker rules from retrieved evidence.

    Why this exists:
    - missing strategy/owner/target-date must mark the risk as BLOCKER

    How to use:
    - run after coverage retrieval and before recommendation generation
    """

    del context
    validated: list[RiskRecord] = []
    for risk in state.all_risks:
        enriched = _populate_treatment_fields_from_coverage(risk)
        blocker, reason = blocker_status_for_risk(enriched)
        enriched.blocker = blocker
        enriched.blocker_reason = reason
        enriched.treatment_status = treatment_status_for_risk(enriched)
        validated.append(enriched)
    return StepResult(state_update={"all_risks": validated})


@typed_node(DVARiskValidatorState)
async def recommend_strategy_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Generate inferred strategy recommendations for each risk.

    Why this exists:
    - recommendations are mandatory for source and inferred risks

    How to use:
    - run after treatment validation so recommendation prompt sees blocker context
    """

    recommended: list[RiskRecord] = []
    for risk in state.all_risks:
        strategy_lines = await _model_recommend_lines(
            context,
            operation="recommend_strategy",
            system_prompt=_GRAPH_RECOMMEND_PROMPT,
            user_prompt=(
                f"Risk: {risk.title}\n"
                f"Type: {risk.risk_type}\n"
                f"Current status: {risk.treatment_status}\n"
                f"Blocker: {risk.blocker_reason or 'none'}\n"
                "Return 1-2 concise inferred strategy lines."
            ),
            fallback=[
                "Align mitigation strategy with explicit accountable ownership.",
                "Link each treatment commitment to verifiable DVA evidence.",
            ],
        )
        risk.inferred_recommended_strategy = strategy_lines
        recommended.append(risk)
    return StepResult(state_update={"all_risks": recommended})


@typed_node(DVARiskValidatorState)
async def recommend_actions_mitigations_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Generate inferred action recommendations for each risk.

    Why this exists:
    - final risk cards require explicit recommended actions

    How to use:
    - run after strategy recommendation generation
    """

    final_risks: list[RiskRecord] = []
    for risk in state.all_risks:
        actions = await _model_recommend_lines(
            context,
            operation="recommend_actions",
            system_prompt=_GRAPH_RECOMMEND_PROMPT,
            user_prompt=(
                f"Risk: {risk.title}\n"
                f"Blocker: {risk.blocker_reason or 'none'}\n"
                "Return exactly 3 inferred mitigation actions as short lines."
            ),
            fallback=[
                "Define one concrete mitigation action with measurable outcome.",
                "Assign one accountable owner for execution and reporting.",
                "Set one target date and one follow-up checkpoint.",
            ],
        )
        risk.inferred_recommended_actions = actions[:3]
        final_risks.append(risk)
    return StepResult(state_update={"all_risks": final_risks})


@typed_node(DVARiskValidatorState)
async def build_report_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Build markdown report and risk-index JSON payload.

    Why this exists:
    - report/index generation must remain explicit and testable before publication

    How to use:
    - run after all validation and recommendation steps
    """

    del context
    report_markdown = render_validation_report(state.all_risks, state.sources)
    source_document_uids = [
        source.document_uid for source in state.sources if source.document_uid
    ]
    risk_index_json = render_risk_index_json(
        state.all_risks,
        state.sources,
        source_document_uids=cast(list[str], source_document_uids),
        result_document_uid=None,
        risk_index_document_uid=None,
    )
    return StepResult(
        state_update={
            "report_markdown": report_markdown,
            "risk_index_json": risk_index_json,
        }
    )


@typed_node(DVARiskValidatorState)
async def publish_outputs_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Publish `result.md` and `risk_index.json` artifacts.

    Why this exists:
    - graph output must provide downloadable artifacts for report and index

    How to use:
    - run once report and index payloads are finalized
    """

    report_artifact = await context.publish_text(
        file_name="result.md",
        text=state.report_markdown,
        title="DVA Risk Validation Report",
        content_type="text/markdown; charset=utf-8",
    )
    index_artifact = await context.publish_text(
        file_name="risk_index.json",
        text=state.risk_index_json,
        title="DVA Risk Validation Index",
        content_type="application/json",
    )

    updated_index = render_risk_index_json(
        state.all_risks,
        state.sources,
        source_document_uids=[
            source.document_uid for source in state.sources if source.document_uid
        ],
        result_document_uid=report_artifact.document_uid,
        risk_index_document_uid=index_artifact.document_uid,
    )

    return StepResult(
        state_update={
            "result_artifact": report_artifact,
            "risk_index_artifact": index_artifact,
            "risk_index_json": updated_index,
        }
    )


@typed_node(DVARiskValidatorState)
async def persist_session_scope_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Merge generated artifact document UIDs into runtime session search scope.

    Why this exists:
    - QA follow-up turns must be able to search both original DVA and generated outputs

    How to use:
    - run after publication, then pass merged context through the normal session channel
    """

    generated_uids = [
        uid
        for uid in (
            state.result_artifact.document_uid if state.result_artifact else None,
            state.risk_index_artifact.document_uid
            if state.risk_index_artifact
            else None,
        )
        if uid
    ]
    merged = merge_session_scope(
        context.binding.runtime_context,
        generated_document_uids=cast(list[str], generated_uids),
        fallback_search_policy="hybrid",
    )
    return StepResult(state_update={"persisted_runtime_context": merged})


@typed_node(DVARiskValidatorState)
async def finalize_step(
    state: DVARiskValidatorState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Finalize user-facing text payload.

    Why this exists:
    - runtime output should show report body in chat while links are attached as UI parts

    How to use:
    - make this the terminal node of the graph
    """

    del context
    return StepResult(
        state_update={
            "final_text": state.report_markdown,
            "done_reason": "completed",
        }
    )


def _extract_requested_risk_count(payload: object) -> int | None:
    """Parse free-text HITL payload into an integer risk-count request."""

    text = _extract_text_answer(payload)
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _extract_text_answer(payload: object) -> str:
    """Extract one human text answer from flexible HITL resume payload shapes."""

    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "answer", "value", "choice_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_extraction_query(section_hint: str | None) -> str:
    """Build bilingual retrieval query for source risk extraction."""

    base = (
        "Extract the ordered risk rows from DVA risk table / table des risques / "
        "registre des risques, including risk title and mitigation context"
    )
    if not section_hint:
        return base
    return f"{base}. Prioritize section: {section_hint}"


async def _extract_risk_titles(raw_text: str, context: GraphNodeContext) -> list[str]:
    """Extract ordered risk titles from markdown-like retrieval text."""

    if context.model is not None:
        extracted = cast(
            ExtractedRisks,
            await context.invoke_structured_model(
                ExtractedRisks,
                messages=[
                    SystemMessage(content=_GRAPH_EXTRACT_PROMPT),
                    HumanMessage(content=raw_text[:5000]),
                ],
                operation="extract_source_risks",
            ),
        )
        cleaned_model_rows = _clean_extracted_risk_titles(extracted.risks)
        if cleaned_model_rows:
            return cleaned_model_rows

    heuristic = _heuristic_risk_rows(raw_text)
    return _clean_extracted_risk_titles(heuristic)


def _heuristic_risk_rows(raw_text: str) -> list[str]:
    """Detect likely bilingual risk rows from plain text when no model is available."""

    rows: list[str] = []
    for line in raw_text.splitlines():
        normalized = line.strip(" -\t")
        lower = normalized.lower()
        if not normalized:
            continue
        if "|" in normalized:
            extracted_table_title = _risk_title_from_markdown_row(normalized)
            if extracted_table_title:
                rows.append(extracted_table_title)
                continue
        if any(
            token in lower
            for token in (
                "risk",
                "risque",
                "mitigation",
                "owner",
                "propriétaire",
                "matrice",
            )
        ):
            rows.append(normalized[:180])
    deduped: list[str] = []
    for row in rows:
        if row not in deduped:
            deduped.append(row)
    return deduped[:30]


def _clean_extracted_risk_titles(raw_titles: list[str]) -> list[str]:
    """Filter and normalize extracted rows so only meaningful risk titles remain."""

    cleaned: list[str] = []
    for title in raw_titles:
        normalized = re.sub(r"\s+", " ", title).strip()
        if not normalized:
            continue
        if "|" in normalized:
            extracted = _risk_title_from_markdown_row(normalized)
            if extracted:
                normalized = extracted
        normalized = normalized.strip(" -*`")
        if _looks_like_non_risk_line(normalized):
            continue
        if normalized not in cleaned:
            cleaned.append(normalized[:180])
    return cleaned[:30]


def _risk_title_from_markdown_row(line: str) -> str | None:
    """Extract the probable 'Risk Title' cell from a markdown table row."""

    parts = [part.strip() for part in line.split("|")]
    parts = [part for part in parts if part]
    if len(parts) < 3:
        return None

    lower_parts = [_strip_markup(part).lower().strip() for part in parts]
    header_tokens = (
        "id",
        "risk",
        "risk title",
        "titre du risque",
        "strategy",
        "stratégie",
        "impact",
        "action",
        "owner",
        "propriétaire",
        "target date",
        "date cible",
    )
    header_hits = 0
    for cell in lower_parts:
        if any(token == cell or token in cell for token in header_tokens):
            header_hits += 1
    if header_hits >= max(3, (len(parts) + 1) // 2):
        return None
    if all(re.fullmatch(r"[-: ]+", part or "") for part in parts):
        return None

    # In common DVA markdown tables:
    # category | id | risk title | strategy | impact | action
    if len(parts) >= 3 and re.fullmatch(r"\d{1,3}", parts[1]):
        return parts[2]

    # Fallback: choose longest non-header segment.
    candidates = [
        part
        for part in parts
        if not re.fullmatch(r"\d{1,3}", part)
        and not _looks_like_non_risk_line(part)
        and len(part) > 8
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _looks_like_non_risk_line(text: str) -> bool:
    """Return True for headings/metadata rows that are not concrete risk titles."""

    lower = text.lower().strip()
    if not lower:
        return True
    if lower.startswith("#") or lower.startswith("[") or lower.startswith(">"):
        return True
    if lower.startswith("<img") or "contents" in lower:
        return True
    if re.fullmatch(r"[-:| ]+", lower):
        return True
    if re.search(r"<[^>]+>", lower):
        return True
    if lower.count("[") >= 2 and lower.count("]") >= 2:
        return True
    if lower.startswith(("type:", "priority:", "coverage in", "source:", "status:")):
        return True
    if "|" in text:
        parts = [_strip_markup(part).lower().strip() for part in text.split("|")]
        parts = [part for part in parts if part]
        if not parts:
            return True
        if all(re.fullmatch(r"[-: ]+", part) for part in parts):
            return True
        header_tokens = (
            "id",
            "risk",
            "risk title",
            "titre du risque",
            "strategy",
            "stratégie",
            "impact",
            "action",
            "owner",
            "propriétaire",
            "target date",
            "date cible",
        )
        header_hits = 0
        for part in parts:
            if any(token == part or token in part for token in header_tokens):
                header_hits += 1
        if header_hits >= max(3, (len(parts) + 1) // 2):
            return True
    return False


def _result_contains_risk_table_signal(result: object) -> bool:
    """Return True when retrieval output strongly suggests risk-table coverage."""

    text = _collect_result_text(result)
    lower = text.lower()
    if any(
        marker in lower
        for marker in (
            "risk table",
            "risk register",
            "table des risques",
            "registre des risques",
            "matrice des risques",
        )
    ):
        return True

    # Broader bilingual fallback:
    # if retrieved text references risks plus treatment fields (owner/date/action),
    # we treat this as sufficient confidence and avoid unnecessary HITL prompts.
    has_risk_term = any(
        token in lower
        for token in (
            "risk",
            "risque",
            "analyse des risques",
            "risk assessment",
        )
    )
    has_treatment_term = any(
        token in lower
        for token in (
            "mitigation",
            "owner",
            "propriétaire",
            "proprietaire",
            "target date",
            "date cible",
            "action",
            "mesure",
            "traitement",
        )
    )
    if has_risk_term and has_treatment_term:
        return True

    if re.search(r"\b(r[-\s]?\d{1,3}|risk\s+\d+|risque\s+\d+)\b", lower):
        return True
    return False


def _collect_result_text(result: object) -> str:
    """Normalize mixed tool-result blocks into one text blob."""

    if result is None:
        return ""

    blocks = getattr(result, "blocks", ())
    lines: list[str] = []
    for block in blocks or ():
        kind = getattr(block, "kind", None)
        if kind == ToolContentKind.TEXT:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
        if kind == ToolContentKind.JSON:
            data = getattr(block, "data", None)
            lines.extend(_extract_text_from_json_payload(data))

    if lines:
        return "\n".join(lines)

    sources = getattr(result, "sources", ())
    for source in sources or ():
        content = getattr(source, "content", None)
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
    return "\n".join(lines)


def _extract_text_from_json_payload(data: object) -> list[str]:
    """Extract textual snippet lines from known knowledge.search JSON payloads."""

    if not isinstance(data, dict):
        return []

    hits = data.get("hits")
    if not isinstance(hits, list):
        return []

    lines: list[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        content = hit.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
    return lines


def _collect_citation_sources(result: object) -> list[CitationSource]:
    """Build citation metadata rows from retrieval sources."""

    sources: list[CitationSource] = []
    raw_sources = getattr(result, "sources", ())
    for idx, source in enumerate(raw_sources or (), start=1):
        title = str(getattr(source, "title", None) or "Retrieved source")
        file_name = str(getattr(source, "file_name", None) or title)
        section = cast(str | None, getattr(source, "section", None))
        page = cast(int | None, getattr(source, "page", None))
        document_uid = cast(str | None, getattr(source, "document_uid", None))
        sources.append(
            CitationSource(
                index=idx,
                title=title,
                file_name=file_name,
                section=section,
                page=page,
                document_uid=document_uid,
            )
        )
    return sources


def _priority_for_position(position: int) -> Literal["P0", "P1", "P2", "P3"]:
    """Assign inferred P0-P3 priority from source-order position."""

    if position % 4 == 1:
        return "P0"
    if position % 4 == 2:
        return "P1"
    if position % 4 == 3:
        return "P2"
    return "P3"


def _populate_treatment_fields_from_coverage(risk: RiskRecord) -> RiskRecord:
    """Populate mandatory treatment fields from compact coverage text heuristics."""

    coverage = risk.evidence.coverage_ref.lower()
    if coverage == "no evidence found":
        risk.evidence.evidence_status = "NO EVIDENCE FOUND"
        risk.evidence.strategy_text = "NO EVIDENCE FOUND"
        risk.evidence.owner_text = "NO EVIDENCE FOUND"
        risk.evidence.target_date_text = "NO EVIDENCE FOUND"
        risk.evidence.actions = []
        risk.evidence.notes = "No DVA paragraph was found for this risk."
        return risk

    citation = risk.evidence.coverage_citation
    risk.evidence.mapping_text = "Mapped to nearest retrieved DVA section"
    risk.evidence.mapping_citation = citation

    has_strategy = any(token in coverage for token in ("strategy", "stratégie"))
    has_owner = any(
        token in coverage for token in ("owner", "propriétaire", "responsable")
    )
    has_target = any(token in coverage for token in ("target", "échéance", "date"))
    has_action = any(token in coverage for token in ("action", "mitigation", "mesure"))

    risk.evidence.strategy_text = (
        "Strategy mentioned in DVA excerpt" if has_strategy else "NO EVIDENCE FOUND"
    )
    risk.evidence.strategy_citation = citation if has_strategy else None

    risk.evidence.owner_text = (
        "Owner mentioned in DVA excerpt" if has_owner else "NO EVIDENCE FOUND"
    )
    risk.evidence.owner_citation = citation if has_owner else None

    risk.evidence.target_date_text = (
        "Target date mentioned in DVA excerpt" if has_target else "NO EVIDENCE FOUND"
    )
    risk.evidence.target_date_citation = citation if has_target else None

    if has_action:
        risk.evidence.actions = ["Action or mitigation item detected in DVA excerpt"]
        risk.evidence.action_citations = [citation] if citation is not None else []

    present_fields = sum((has_strategy, has_owner, has_target, has_action))
    if present_fields >= 3:
        risk.evidence.evidence_status = "Sufficient"
    else:
        risk.evidence.evidence_status = "Partial"
    risk.evidence.notes = "Treatment fields were inferred from retrieved DVA wording."
    return risk


async def _model_recommend_lines(
    context: GraphNodeContext,
    *,
    operation: str,
    system_prompt: str,
    user_prompt: str,
    fallback: list[str],
) -> list[str]:
    """Generate 1..N recommendation lines from model text with deterministic fallback."""

    if context.model is None:
        return fallback

    message = await context.invoke_model(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
        operation=operation,
    )
    raw = str(getattr(message, "content", "")).strip()
    if not raw:
        return fallback
    lines = [line.strip(" -\t") for line in raw.splitlines() if line.strip()]
    cleaned = [line for line in lines if len(line) > 2]
    return cleaned[: max(1, len(fallback))] or fallback


def _compact_line(raw_text: str) -> str:
    """Normalize multiline snippet to one compact line for report tables."""

    return re.sub(r"\s+", " ", raw_text).strip()[:240]


def _derive_coverage_reference(
    *,
    risk_title: str,
    risk_text: str,
    search_result: object,
) -> str:
    """Build a human-readable coverage reference from retrieval output."""

    if not risk_text.strip():
        return "NO EVIDENCE FOUND"

    source_section = _source_section_hint(search_result)
    row_hint = _risk_table_row_reference(risk_text, risk_title)
    if row_hint:
        if source_section:
            return f"{source_section} — {row_hint}"
        return row_hint

    heading = _markdown_heading_reference(risk_text)
    if heading:
        return heading

    sentence = _sentence_for_risk_title(risk_text, risk_title)
    if sentence:
        return sentence

    compact = _compact_line(_strip_markup(risk_text))
    if compact:
        return compact
    return "NO EVIDENCE FOUND"


def _source_section_hint(search_result: object) -> str | None:
    """Return section/title hint from first retrieval source when available."""

    for source in getattr(search_result, "sources", ()) or ():
        section = getattr(source, "section", None)
        if isinstance(section, str) and section.strip():
            return section.strip()
        title = getattr(source, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()
    return None


def _risk_table_row_reference(risk_text: str, risk_title: str) -> str | None:
    """Return concise row reference when risk appears inside markdown table rows."""

    target = risk_title.lower().strip()
    for line in risk_text.splitlines():
        if "|" not in line:
            continue
        lower = line.lower()
        if target and target not in lower:
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) < 3:
            continue
        if re.fullmatch(r"\d{1,3}", parts[1]):
            category = parts[0]
            row_id = parts[1]
            return f"Risk table row ({category}, ID {row_id})"
        parsed_title = _risk_title_from_markdown_row(line)
        if parsed_title:
            return f"Risk table row ({parsed_title})"
    return None


def _markdown_heading_reference(risk_text: str) -> str | None:
    """Extract the first markdown heading as coverage reference when present."""

    for line in risk_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            return stripped[4:].strip()
        if stripped.startswith("## "):
            return stripped[3:].strip()
    return None


def _sentence_for_risk_title(risk_text: str, risk_title: str) -> str | None:
    """Extract one sentence containing the risk title from free text chunks."""

    cleaned = _strip_markup(risk_text)
    if not cleaned:
        return None
    target = risk_title.lower().strip()
    if not target:
        return None
    for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
        normalized = sentence.strip()
        if target in normalized.lower():
            return _compact_line(normalized)
    return None


def _strip_markup(text: str) -> str:
    """Remove markdown/html noise from retrieved text before sentence extraction."""

    without_images = re.sub(r"<img[^>]*>", " ", text, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_images)
    without_md_links = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", without_tags)
    without_ref_links = re.sub(r"\[([^\]]+)\]\[[^\]]+\]", r"\1", without_md_links)
    without_pipes = without_ref_links.replace("|", " ")
    return re.sub(r"\s+", " ", without_pipes).strip()


def preview_required_nodes() -> tuple[str, ...]:
    """
    Return the mandatory node ids expected in graph previews/tests.

    Why this exists:
    - keeps topology assertions stable and centralized for unit tests

    How to use:
    - use in tests to assert that workflow shape remains explicit

    Example:
    ```python
    assert "locate_risk_table" in preview_required_nodes()
    ```
    """

    return (
        "route_or_start",
        "ask_max_risk_count",
        "locate_risk_table",
        "maybe_ask_risk_section",
        "extract_source_risks",
        "enrich_to_requested_count",
        "retrieve_coverage_evidence",
        "validate_treatment",
        "recommend_strategy",
        "recommend_actions_mitigations",
        "build_report",
        "publish_outputs",
        "persist_session_scope",
        "finalize",
    )
