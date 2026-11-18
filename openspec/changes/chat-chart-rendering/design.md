# Design

## Context

See proposal.md. The source commits target `agentic-backend` and the retired MUI chat. On `swift`, `fred-sdk` owns built-in tool metadata, `fred-runtime` resolves tools for ReAct/Deep and Graph, and the frontend renders `UiPart` through a part registry. `LinkPart | GeoPart` is the frozen base union; extra part models enter through `rebuild_ui_part_union` during registry boot. The geo foundation commit provides the generic local built-in contract used by both tools.

## Goals / Non-Goals

**Goals:** Port the observable chart behavior to the current topology, use the existing Recharts visual language, and define one SDK-owned path for pure local rendering tools and their output parts. Keep the chart result bounded, self-contained, and stable across live delivery and history reload.

**Non-Goals:** Run SQL in the chart tool, validate that model-supplied rows match a prior SQL result, add chart storage, add a browser chart editor, or change the tabular query service. The source commit's unused `series_key` and unverifiable `sql` fields are not carried into the new contract.

## Decisions

### D1. Port behavior, not the old commits verbatim

`bd79b154e` introduced the tool and `ChartPart`; `c5924f762` improved the Recharts palette, labels, and raw-row table. The first commit also contains unrelated legacy changes, and both target paths that `swift` retired. Implement the same user behavior in `fred-sdk`, `fred-runtime`, `fred-agents`, and `apps/frontend/src/rework/`. This avoids importing the old chat schema, SQL Graph agent, MUI theme, or generated API files.

### D2. One local built-in declaration

Extend `BuiltinToolSpec` with a generic pure local handler and optional output part model, beside its existing ref, argument schema, description, and backend. Use one `LOCAL` backend for both `geo.render_points` and `chart.render`. The SDK validates arguments and builds `ToolInvocationResult`; the catalog converts validation failures into error results without UI parts. ReAct/Deep and Graph execute the handler through their existing approval, event, KPI, and stop controls; the fallback invoker lets Python-authored tools call it too. Transport-backed built-ins keep `TOOL_INVOKER`. Avoid a second dispatch table in the application adapter and avoid `LOCAL_GEO` / `LOCAL_CHART` cases. Existing explicit declarations are deduplicated against implicitly available local rendering tools.

The runtime registry adds the catalog's output part models to its boot-time part collection before rebuilding the union and exporting OpenAPI. `GeoPart` is the same existing base class, so it is included once; `ChartPart` is contributed without editing the base union literal. Kind collisions with a different part class fail boot as they do for capability parts. This uses the existing registration mechanism rather than a placeholder capability visible in the Tools tab.

### D3. Validate a bounded, self-contained result

The chart arguments accept `bar`, `line`, `area`, `pie`, or `table`, a short title, 1-50 row objects, an X key and one or more Y keys for plotted views. Table view does not need Y keys. All row values are JSON scalars or null. Every plotted row must have the mapped keys; Y values must be finite numbers or nonempty canonical numeric strings, with null allowed as a gap. Pie values must be nonnegative. The serialized payload limit is 50,000 characters. An early row-size check avoids serializing oversized values before full validation. Invalid inputs produce a tool error without a partial part. The part retains the original scalar rows; numeric conversion is only for plotting so the raw table shows source values. No query identifier or SQL string is accepted because the tool cannot verify either.

### D4. Frontend uses Recharts and current tokens

Add a renderer for the `chart` part to the current part registry, backed by Recharts primitives. Use the same surface tokens as KPI charts for axes and tooltips, and their shared multi-series palette for distinct series colors. The legacy MUI renderer is a behavior reference only. A semantic, scrollable raw-row table is available for all chart types. Long labels, empty data, invalid saved parts, narrow layouts, keyboard access to values, and light/dark themes receive focused checks. Do not parse free text to infer charts.

### D5. Integrate with SQL and the geo branch

The packaged tabular prompt calls the model-visible `chart_render` tool with returned `read_query` rows when useful, prefers an appropriate chart type, and discloses query truncation. Its stable SDK tool ref is `chart.render`. A reference scenario exercises the tool without a live SQL service. The generic local handler refactor lands in the geo branch with its Leaflet renderer and existing geo contract; the chart branch builds on that commit. Its draft PR targets the geo branch until geo merges. This removes `LOCAL_GEO` cases before chart is added and leaves one way to define local native rendering tools while the chart and map remain different UI parts.

## Risks / Trade-offs

- A model could alter rows while copying a SQL result into tool arguments. The prompt requires actual returned rows; the tool faithfully renders its input but does not claim provenance verification.
- Large text cells or repeated tool calls could expand event and history payloads. The input is capped by row count and serialized size; normal tool budgets still limit repeated calls. No shared mutable state or process-local correctness dependency is added, so replicas behave the same.
- The geo branch can continue changing. Keep the shared foundation commit in that branch and review the resulting stacked diffs separately before merging.
- A frontend older than the runtime will skip an unknown `chart` part while retaining its text tool result and stored raw part. Deploying the updated frontend restores the chart.

## Migration Plan

No database or configuration migration is required. Generate the runtime OpenAPI client from the updated SDK/runtime before building the frontend. Deploy runtime and frontend normally; rollback to the previous frontend hides chart parts but preserves their stored data for a later compatible frontend. Add the required `impact: none` PR migration note with the normal deployment and rollback check.
