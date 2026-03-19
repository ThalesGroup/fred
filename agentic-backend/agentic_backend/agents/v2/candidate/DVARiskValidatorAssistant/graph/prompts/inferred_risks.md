You are extending a DVA risk list with additional typical risks for this context.

Return STRICT JSON:
{
  "risks": [
    {
      "title": "<inferred risk title>"
    }
  ]
}

Rules:
- Only return risks that are NOT already present.
- Keep the list concise and relevant to the DVA context.
- Use the same language as the DVA excerpts.

Context snippets:
{retrieved_context}

Existing risks:
{existing_risks}
