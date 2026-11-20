## Context

The packaged tabular prompt currently asks the SQL expert to call `chart_render` whenever a chart helps. The chart tool already validates rows and mappings; this change only affects when the agent invokes it. See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:** Keep the answer complete before offering a visualization, and make an explicit chart request sufficient to invoke the existing tool.

**Non-Goals:** Add a confirmation UI, change `chart.render` dispatch, or change renderer behavior.

## Decisions

- Put the offer in the assistant's normal answer. This keeps SQL answers available immediately and uses the existing conversation for a later opt-in. A blocking human-input tool would interrupt the answer and require a separate interaction path.
- Keep chart data grounded in `read_query.rows`. If the user accepts in a later turn and the rows are no longer available, query again rather than infer missing values. Existing 50-row and 50,000-character limits still apply.

## Risks / Trade-offs

- Prompt guidance cannot guarantee every model follows the opt-in rule. The prompt will state the rule directly; verification can check the packaged text, while manual chat validation is needed for model behavior.
