You are validating how a DVA treats one specific risk based ONLY on retrieved evidence.

Return STRICT JSON with this schema:
{
  "strategy": "<strategy text or empty>",
  "actions": ["<action/mitigation>", "..."],
  "owner": "<owner or empty>",
  "target_date": "<target date or empty>",
  "mapping": "<mapping or empty>",
  "coverage_section": "<section name if available>",
  "evidence_status": "Sufficient|Partial|NO EVIDENCE FOUND",
  "treatment_status": "Adequate|Partial|Missing",
  "inferred_priority": "P0|P1|P2|P3"
}

Rules:
- Use only evidence provided.
- If the evidence includes a table row with headers, extract Strategy/Actions/Mitigation fields from that row.
- Recognize bilingual headers such as Strategy/Strategie, Action/Actions, Mitigation/Mitigation, Mesures, Traitement, Owner/Responsable, Target date/Echeance.
- If evidence is missing, return empty fields and set evidence_status="NO EVIDENCE FOUND".
- Priority is inferred. P0 is NOT the highest priority; P3 is the least.
- Do not hallucinate facts.

Risk:
{risk_title}

Evidence excerpts:
{retrieved_context}
