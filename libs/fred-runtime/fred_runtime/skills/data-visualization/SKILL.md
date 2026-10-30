---
name: data-visualization
description: Choose and present a truthful, accessible chart or table from verified data using the rendering tools available for this request.
user-invocable: false
license: Apache-2.0
metadata:
  author: Fred contributors
  provenance: Original Fred procedure.
---

# Clear data visualization

Start with the question the figure should answer and the actual values it can
support. Use the supplied data or results obtained through available tools. If
the underlying values are unavailable, request them or describe a proposed
chart explicitly as a plan; do not draw invented measurements.

Choose the smallest representation that makes the comparison clear:

| Question | Useful representation |
| --- | --- |
| Compare categories or ranks | Sorted horizontal bars, or a compact table |
| Show change over time | Chronological line chart; keep missing periods visible |
| Show a numeric distribution | Histogram with stated bins, or verified quantiles |
| Examine two numeric variables | Scatter plot; association does not prove causation |
| Show shares of a whole | A table or stacked bars with one explicit denominator |
| Read exact values or only a few observations | A labeled table |

Keep the chart faithful to its data. Bars use a zero baseline, including when
values are negative. State any cropped axis on a line or scatter plot. Use
consistent scales for comparable panels, avoid dual axes and three-dimensional
decoration, and show observed gaps rather than silently interpolating them.
Label units, the period, source and material exclusions. Mark estimates and
uncertainty only when they are supported by the data or computation.

Choose an output supported by this request's declared tools:

- With a plotting or presentation tool, use its documented formats and actual
  result. Inspect or validate the artifact when a supported read-back exists.
- With a renderer limited to HTML and CSS, use a static chart supported by
  its documented contract, such as labeled bars paired with their values.
  Use scripts, external libraries or diagram syntax only when the selected
  tool explicitly supports them.
- Without a suitable renderer, return a Markdown table with a short explanation
  and the proposed chart type if useful. Do not claim to have generated a chart
  or downloadable file. Installing a library is outside this procedure.

Write a descriptive title and a short text explanation in the user's requested
language. Use readable labels and enough contrast; distinguish series with
labels or shapes as well as color. Provide the key values or an accessible
table so the result can be understood without seeing the figure. Check that
every plotted value matches the data and that sorting, totals and labels agree
before presenting it.
