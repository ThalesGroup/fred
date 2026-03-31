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

"""Report and machine-index builders for DVA Risk Validator outputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

from .graph_state import CitationSource, RiskRecord


def blocker_status_for_risk(risk: RiskRecord) -> tuple[bool, str]:
    """
    Decide blocker status from mandatory treatment fields.

    Why this exists:
    - blocker logic is a stable business rule reused by graph steps and tests

    How to use:
    - call after evidence extraction populated strategy/owner/target date fields

    Example:
    ```python
    blocker, reason = blocker_status_for_risk(risk)
    ```
    """

    missing: list[str] = []
    if risk.evidence.strategy_text == "NO EVIDENCE FOUND":
        missing.append("strategy")
    if risk.evidence.owner_text == "NO EVIDENCE FOUND":
        missing.append("action owner")
    if risk.evidence.target_date_text == "NO EVIDENCE FOUND":
        missing.append("action target date")
    if not missing:
        return False, ""
    return True, f"Missing mandatory treatment field(s): {', '.join(missing)}."


def treatment_status_for_risk(
    risk: RiskRecord,
) -> Literal["Adequate", "Partial", "Missing"]:
    """
    Classify treatment status from extracted evidence completeness.

    Why this exists:
    - report summary table needs one explicit status per risk

    How to use:
    - call after blocker evaluation

    Example:
    ```python
    status = treatment_status_for_risk(risk)
    ```
    """

    if risk.evidence.evidence_status == "NO EVIDENCE FOUND":
        return "Missing"
    if risk.blocker:
        return "Partial"
    return "Adequate"


def render_validation_report(
    risks: list[RiskRecord], sources: list[CitationSource]
) -> str:
    """
    Render the mandatory markdown report with fixed section ordering.

    Why this exists:
    - enforces a stable report contract for users and downstream parsers

    How to use:
    - call after all risk enrichment/validation/recommendation steps complete

    Example:
    ```python
    markdown = render_validation_report(risks, sources)
    ```
    """

    lines: list[str] = []
    lines.append("# DVA Risk Validation Report")
    lines.append(
        "Priority legend: priorities are **inferred** and ordered `P0` to `P3` "
        "where `P3` is the least priority."
    )
    lines.append("")

    lines.append("## DVA Risks (Full List, Source Order)")
    for risk in risks:
        lines.append(
            f"- {risk.risk_id}: {risk.title} ({risk.risk_type}, priority {risk.priority} inferred)"
        )
    lines.append("")

    lines.append(
        "## Coverage List with reference to the paragraph that covers the risk"
    )
    for risk in risks:
        coverage_ref = risk.evidence.coverage_ref
        citation = (
            f" [{risk.evidence.coverage_citation}]"
            if risk.evidence.coverage_citation is not None
            else ""
        )
        lines.append(f"- {risk.risk_id}: {coverage_ref}{citation}".rstrip())
    lines.append("")

    lines.append("## Treatment Validation Summary")
    lines.append(
        "| risk id | risk title | source or inferred | inferred priority | treatment status | blocker status | evidence status |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for risk in risks:
        lines.append(
            "| "
            f"{risk.risk_id} | {risk.title} | {risk.risk_type} | {risk.priority} | "
            f"{risk.treatment_status} | {'Yes' if risk.blocker else 'No'} | "
            f"{risk.evidence.evidence_status} |"
        )
    lines.append("")

    lines.append("## Treatment Validation Details")
    for risk in risks:
        lines.extend(_render_risk_card(risk))
        lines.append("")

    lines.append("## Blockers & PDA Action Plan")
    blockers = [risk for risk in risks if risk.blocker]
    if not blockers:
        lines.append("- No blockers were detected in current evidence scope.")
    else:
        for risk in blockers:
            lines.append(f"- {risk.risk_id}: {risk.blocker_reason}")
            lines.append(
                f"- PDA action: update DVA section for {risk.risk_id} with strategy, owner, and target date evidence."
            )
    lines.append("")

    lines.append("## Sources")
    if not sources:
        lines.append("- [1] No source metadata available from retrieval hits.")
    else:
        for source in sources:
            details: list[str] = [source.title, source.file_name]
            if source.page is not None:
                details.append(f"page {source.page}")
            if source.section:
                details.append(f"section {source.section}")
            if source.document_uid:
                details.append(f"document_uid={source.document_uid}")
            lines.append(f"- [{source.index}] " + " | ".join(details))

    return "\n".join(lines).strip() + "\n"


def render_risk_index_json(
    risks: list[RiskRecord],
    sources: list[CitationSource],
    *,
    source_document_uids: list[str],
    result_document_uid: str | None,
    risk_index_document_uid: str | None,
) -> str:
    """
    Build the machine-readable risk index artifact.

    Why this exists:
    - QA and downstream systems need a structured counterpart to the markdown report

    How to use:
    - call right before artifact publication once report content is final

    Example:
    ```python
    payload = render_risk_index_json(risks, sources, source_document_uids=["doc-1"], ...)
    ```
    """

    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "source_document_uids": sorted(set(source_document_uids)),
        "risks": [
            {
                "risk_id": risk.risk_id,
                "title": risk.title,
                "source_or_inferred": risk.risk_type,
                "source_order": risk.source_order,
                "inferred_priority": risk.priority,
                "coverage_reference": risk.evidence.coverage_ref,
                "coverage_citation": risk.evidence.coverage_citation,
                "treatment_status": risk.treatment_status,
                "blocker": risk.blocker,
                "blocker_reason": risk.blocker_reason,
                "evidence_status": risk.evidence.evidence_status,
                "inferred_recommended_strategy": risk.inferred_recommended_strategy,
                "inferred_recommended_actions": risk.inferred_recommended_actions,
            }
            for risk in risks
        ],
        "citation_mapping": [
            {
                "index": source.index,
                "title": source.title,
                "file_name": source.file_name,
                "section": source.section,
                "page": source.page,
                "document_uid": source.document_uid,
            }
            for source in sources
        ],
        "artifact_metadata": {
            "result_document_uid": result_document_uid,
            "risk_index_document_uid": risk_index_document_uid,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_risk_card(risk: RiskRecord) -> list[str]:
    """Render one risk detail card using the strict multiline format."""

    lines: list[str] = []
    lines.append(f"### {risk.risk_id} — {risk.title}")
    lines.append(f"- **Type:** {risk.risk_type}")
    lines.append(f"- **Priority:** {risk.priority} *(inferred)*")

    coverage = risk.evidence.coverage_ref
    if risk.evidence.coverage_citation is not None:
        coverage = f"{coverage} [{risk.evidence.coverage_citation}]"
    lines.append(f"- **Coverage in DVA:** {coverage}")
    lines.append("")

    lines.append("**DVA treatment**")
    strategy = risk.evidence.strategy_text
    if risk.evidence.strategy_citation is not None:
        strategy = f"{strategy} [{risk.evidence.strategy_citation}]"
    lines.append(f"- **Strategy (DVA):** {strategy}")

    lines.append("- **Actions/Mitigations (DVA):**")
    if risk.evidence.actions:
        for idx, action in enumerate(risk.evidence.actions):
            citation = (
                f" [{risk.evidence.action_citations[idx]}]"
                if idx < len(risk.evidence.action_citations)
                else ""
            )
            lines.append(f"  - {action}{citation}")
    else:
        lines.append("  - NO EVIDENCE FOUND")

    owner = risk.evidence.owner_text
    if risk.evidence.owner_citation is not None:
        owner = f"{owner} [{risk.evidence.owner_citation}]"
    target_date = risk.evidence.target_date_text
    if risk.evidence.target_date_citation is not None:
        target_date = f"{target_date} [{risk.evidence.target_date_citation}]"
    mapping = risk.evidence.mapping_text
    if risk.evidence.mapping_citation is not None:
        mapping = f"{mapping} [{risk.evidence.mapping_citation}]"

    lines.append(f"- **Owner:** {owner}")
    lines.append(f"- **Target date:** {target_date}")
    lines.append(f"- **DVA mapping:** {mapping}")
    lines.append("")

    lines.append("**Evidence**")
    lines.append(f"- **Evidence status:** {risk.evidence.evidence_status}")
    lines.append(f"- **Notes:** {risk.evidence.notes}")
    lines.append("")

    lines.append("**Recommended strategy (inferred)**")
    strategy_lines = risk.inferred_recommended_strategy or [
        "Harmonize DVA wording with explicit accountable treatment owner."
    ]
    for strategy_line in strategy_lines:
        lines.append(f"- {strategy_line}")
    lines.append("")

    lines.append("**Recommended actions (inferred)**")
    action_lines = risk.inferred_recommended_actions or [
        "Define one measurable mitigation action.",
        "Assign one accountable owner.",
        "Add one target date and review checkpoint.",
    ]
    for idx, action in enumerate(action_lines, start=1):
        lines.append(f"{idx}. {action}")
    lines.append("")

    lines.append("**Blocker rationale**")
    lines.append(
        f"- **BLOCKER:** {'Yes' if risk.blocker else 'No'} — {risk.blocker_reason or 'No blocker condition detected.'}"
    )
    return lines
