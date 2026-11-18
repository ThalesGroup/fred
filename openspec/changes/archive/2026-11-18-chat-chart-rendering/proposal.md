# Proposal

## Why

The legacy `main` branch shipped `chart.render` and inline charts, but the current `swift` topology has no equivalent for `fred-agents`. SQL results can be read in chat without being plotted. The in-flight geo branch also shows that adding each local rendering tool through runtime-specific cases would make this gap recur.

## What Changes

- Port the behavior of `chart.render` from commits `bd79b154e` and `c5924f762` to the current SDK, runtime, and frontend. The port uses the current contracts and design system rather than applying obsolete paths verbatim.
- Make `chart.render` available once to ReAct, Deep, and Graph agents, like the shared `geo.render_points` tool. It accepts bounded rows already returned by a data tool, validates chart columns and numeric series, and returns a typed, self-contained `ChartPart` plus a short text result. It does not run SQL or fetch data.
- Give local native rendering tools one declaration path for their schema, handler, and output part. Use that path for chart and, when integrating the geo branch, for geo. Preserve the existing capability chat-part registration rule without hand-editing the `UiPart` union.
- Render `ChartPart` in the current chat with Recharts, which already renders Fred's KPI charts. Offer bar, line, area, pie, and table views selected by the tool, plus the underlying rows in an accessible table. Keep arbitrary Markdown tables and JSON as text.
- Guide the SQL expert to pass actual `read_query` rows to the chart tool when a chart helps answer the question.

## Capabilities

### New Capabilities

- `chat-chart-rendering`: Bounded native chart tool results and typed chart display in chat.

### Modified Capabilities

None. The geo branch's `chat-geo-rendering` behavior remains the same when its implementation adopts the shared local tool path.

## Impact

`libs/fred-sdk` native tool declarations and chat-part registration, `libs/fred-runtime` ReAct/Deep and Graph dispatch, the `fred-agents` SQL guidance and reference scenario, generated runtime OpenAPI/frontend types, and the frontend's chat part renderer, translations, and design tokens. Recharts is already installed. No database table, SQL execution path, or new chart dependency is needed. The geo branch has uncommitted work and will be reconciled after its owner has a clean branch state.
