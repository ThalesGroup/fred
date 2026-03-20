from __future__ import annotations

from typing import Iterable

from .models import CitationRecord, RiskAssessment


def _citations_inline(citations: Iterable[int]) -> str:
    unique = []
    seen = set()
    for c in citations:
        if c in seen:
            continue
        seen.add(c)
        unique.append(c)
    if not unique:
        return ""
    return " " + " ".join(f"[{c}]" for c in unique)


def render_report(
    *,
    risks: list[RiskAssessment],
    citations: list[CitationRecord],
    dva_invalid_reason: str | None = None,
) -> str:
    lines: list[str] = []

    lines.append("DVA Risks (Full List, Source Order)")
    lines.append("")
    lines.append(
        "Priority legend (inferred): P0 is not the highest priority; P3 is the least."
    )
    lines.append("")
    for risk in risks:
        label = "Inferred" if risk.source == "inferred" else "Source"
        lines.append(f"- {risk.risk_id} — {risk.title} ({label})")
    lines.append("")

    lines.append("Coverage List with reference to the paragraph that covers the risk")
    lines.append("")
    for risk in risks:
        if risk.coverage.citations:
            section = risk.coverage.section or ""
            section_text = f"{section} " if section else ""
            lines.append(
                f"- {risk.risk_id} — {risk.title}: {section_text.strip()}{_citations_inline(risk.coverage.citations)}"
            )
        else:
            lines.append(f"- {risk.risk_id} — {risk.title}: NO EVIDENCE FOUND")
    lines.append("")

    lines.append("Treatment Validation Summary")
    lines.append("")
    lines.append(
        "| Risk ID | Risk title | Source or inferred | Inferred priority | Treatment status | Blocker status | Evidence status |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for risk in risks:
        source_label = "Source" if risk.source == "source" else "Inferred"
        blocker_label = "Yes" if risk.blocker else "No"
        lines.append(
            "| {risk_id} | {title} | {source} | {priority} | {treatment} | {blocker} | {evidence} |".format(
                risk_id=risk.risk_id,
                title=risk.title,
                source=source_label,
                priority=risk.inferred_priority,
                treatment=risk.treatment_status,
                blocker=blocker_label,
                evidence=risk.evidence.status,
            )
        )
    lines.append("")

    lines.append("Treatment Validation Details")
    lines.append("")
    for risk in risks:
        lines.append(f"### {risk.risk_id} — {risk.title}")
        lines.append(
            f"- **Type:** {'Source' if risk.source == 'source' else 'Inferred'}"
        )
        lines.append(f"- **Priority:** {risk.inferred_priority} *(inferred)*")
        if risk.coverage.citations:
            section = risk.coverage.section or ""
            section_text = f"{section} " if section else ""
            lines.append(
                f"- **Coverage in DVA:** {section_text.strip()}{_citations_inline(risk.coverage.citations)}"
            )
        else:
            lines.append("- **Coverage in DVA:** NO EVIDENCE FOUND")
        lines.append("")
        lines.append("**DVA treatment**")
        strategy = risk.treatment.strategy or "NO EVIDENCE FOUND"
        strategy_line = (
            f"{strategy}{_citations_inline(risk.coverage.citations)}"
            if strategy != "NO EVIDENCE FOUND" and risk.coverage.citations
            else strategy
        )
        lines.append(f"- **Strategy (DVA):** {strategy_line}")
        if risk.treatment.actions:
            lines.append("- **Actions/Mitigations (DVA):**")
            for action in risk.treatment.actions:
                lines.append(
                    f"  - {action}{_citations_inline(risk.coverage.citations)}"
                )
        else:
            lines.append("- **Actions/Mitigations (DVA):**")
            lines.append("  - NO EVIDENCE FOUND")
        owner = risk.treatment.owner or "NO EVIDENCE FOUND"
        owner_line = (
            f"{owner}{_citations_inline(risk.coverage.citations)}"
            if owner != "NO EVIDENCE FOUND" and risk.coverage.citations
            else owner
        )
        lines.append(f"- **Owner:** {owner_line}")
        target = risk.treatment.target_date or "NO EVIDENCE FOUND"
        target_line = (
            f"{target}{_citations_inline(risk.coverage.citations)}"
            if target != "NO EVIDENCE FOUND" and risk.coverage.citations
            else target
        )
        lines.append(f"- **Target date:** {target_line}")
        mapping = risk.treatment.mapping or "NO EVIDENCE FOUND"
        mapping_line = (
            f"{mapping}{_citations_inline(risk.coverage.citations)}"
            if mapping != "NO EVIDENCE FOUND" and risk.coverage.citations
            else mapping
        )
        lines.append(f"- **DVA mapping:** {mapping_line}")
        lines.append("")
        lines.append("**Evidence**")
        lines.append(f"- **Evidence status:** {risk.evidence.status}")
        notes = risk.evidence.notes or "No additional notes."
        lines.append(f"- **Notes:** {notes}")
        lines.append("")
        lines.append("**Recommended strategy (inferred)**")
        if risk.recommendation.strategy:
            lines.append(f"- {risk.recommendation.strategy} (inferred)")
        else:
            lines.append("- (inferred) No recommendation generated.")
        lines.append("")
        lines.append("**Recommended actions (inferred)**")
        if risk.recommendation.actions:
            for idx, action in enumerate(risk.recommendation.actions, start=1):
                lines.append(f"{idx}. {action} (inferred)")
        else:
            lines.append("1. (inferred) No recommended actions generated.")
        lines.append("")
        lines.append("**Blocker rationale**")
        blocker_label = "Yes" if risk.blocker else "No"
        reason = risk.blocker_reason or "No blocking issues detected."
        lines.append(f"- **BLOCKER:** {blocker_label} — {reason}")
        lines.append("")

    lines.append("Blockers & PDA Action Plan")
    lines.append("")
    if dva_invalid_reason:
        lines.append(f"- BLOCKER: {dva_invalid_reason}")
    added = False
    for risk in risks:
        if risk.blocker or risk.evidence.status == "NO EVIDENCE FOUND":
            added = True
            lines.append(
                f"- {risk.risk_id}: Add missing treatment details (strategy, owner, target date) and cite the DVA section that covers them."
            )
    if not added and not dva_invalid_reason:
        lines.append("- No blockers detected based on available evidence.")

    if citations:
        lines.append("")
        lines.append("Sources")
        lines.append("")
        for record in citations:
            label_bits = []
            if record.title:
                label_bits.append(record.title)
            if record.section:
                label_bits.append(f"§ {record.section}")
            if record.page is not None:
                label_bits.append(f"p.{record.page}")
            if record.file_name:
                label_bits.append(f"({record.file_name})")
            label = " — ".join(label_bits) if label_bits else (record.uid or "Source")
            lines.append(f"- [{record.index}] {label}")

    return "\n".join(lines).strip() + "\n"
