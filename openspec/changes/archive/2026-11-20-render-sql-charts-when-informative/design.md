## Context

The SQL capability prompt currently offers a chart but waits for a later user choice. The original guidance rendered a chart whenever it helped. The tool and renderer already support both paths; see `proposal.md` for the desired balance.

## Goals / Non-Goals

**Goals:** Give the SQL expert a concrete threshold for chart usefulness while retaining direct rendering on an explicit user request.

**Non-Goals:** Add a frequency counter, a confirmation UI, or changes to the chart tool or renderer.

## Decisions

- Use a qualitative threshold in the packaged prompt: chart when a trend, comparison, or distribution is materially clearer than in prose or a compact table. A fixed count of rows cannot determine usefulness from the question's intent.
- Keep chart data grounded in returned `read_query.rows` and preserve the 50-row limit and truncation disclosure. If a later chart request needs unavailable rows, re-query instead of inferring values.

## Risks / Trade-offs

- Model judgment may vary for borderline questions. The prompt includes both positive and negative criteria, and manual chat validation remains the way to assess rendering frequency.
