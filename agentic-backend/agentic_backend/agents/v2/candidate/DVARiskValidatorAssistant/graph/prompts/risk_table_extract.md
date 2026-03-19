You are extracting the ordered risk list from a DVA risk table.

Return STRICT JSON with this schema:
{
  "risks": [
    {
      "id": "<risk id if present in the table, else empty>",
      "title": "<risk title>"
    }
  ]
}

Rules:
- Preserve the exact order from the DVA table.
- If the table provides risk identifiers, include them verbatim.
- If you cannot find a risk id, return an empty string.
- Use the language found in the DVA passages.
- Do not add inferred risks.

DVA table extracts:
{retrieved_context}
