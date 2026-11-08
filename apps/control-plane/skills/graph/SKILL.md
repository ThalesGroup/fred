---
name: graph
description: Create or repair diagrams, charts and visual comparisons from source facts or verified data, choosing a representation and output supported by the available tools.
license: Apache-2.0
metadata:
  fred-argument-hint: "[goal, source or data] [constraints]"
  author: Fred contributors
  provenance: Original Fred procedure.
---

# Visualization

Identify the question the visual should answer and the supplied facts or actual
tool results that support it. Ask for essential missing relationships, dates or
values; identify a hypothetical plan explicitly. Preserve the intended meaning
when repairing a visual. Prefer a short list or table when it answers more clearly.

## Choose a representation

| What the reader needs | Useful representation |
| --- | --- |
| Steps, decisions or dependencies | Flowchart |
| Ordered interactions, states or structural relationships | Sequence, state, class or entity relationship diagram |
| Hierarchy, milestones or a schedule | Mindmap, timeline or Gantt chart |
| Git ancestry or supplied user-experience scores | Git graph or user journey |
| Category comparisons or ranks | Sorted horizontal bars or a compact table |
| Change over time | Chronological line chart with missing periods visible |
| Numeric distribution | Histogram with stated bins or verified quantiles |
| Two numeric variables | Scatter plot; association alone does not establish cause |
| Parts of one verified total | Table or stacked bars; a pie chart for a few positive parts |
| Exact values or a few observations | Labeled table |

## Use an available output

- For Mermaid output, first read the [Mermaid syntax and delivery reference](references/mermaid.md).
  It covers the diagram families above and the chat's supported syntax. Return
  a complete fenced Mermaid block in chat using that guidance.
- With a plotting, presentation or HTML rendering tool, use its documented
  formats and actual result. A tool limited to HTML/CSS can produce labeled
  static bars with values. Use scripts, libraries or diagram syntax only when
  that tool explicitly supports them. Inspect the artifact when read-back exists.
- Without an appropriate renderer, provide a useful Markdown table or text
  outline and explain the limitation. Request missing data rather than inventing
  measurements; claim generated files only when an available tool produced them.

The Mermaid reference is needed only for Mermaid output. Other formats use
their tool's contract; installing dependencies is outside this procedure.

## Keep the result faithful and readable

Bars use a zero baseline, including for negative values. State cropped axes on
line/scatter plots; use consistent scales for comparable panels, visible gaps
and one explicit denominator for shares. Avoid dual axes and 3D decoration.
Show estimates or uncertainty only when supported by data or computation.

Use a descriptive title, labels and a short explanation in the user's language.
Label units, period, source and material exclusions. Use sufficient contrast and
distinguish series with labels or shapes as well as color. Supply key values or
an accessible table so the result can be understood without seeing it. Check
values, totals, ordering and relationships against the source before presenting.
