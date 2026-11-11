---
name: add-kpi-to-dashboard
description: Add a new KPI metric to the analytics dashboard. Covers: creating a backend preset, regenerating frontend types, wiring the RTK Query hook, and rendering it in an AnalyticsPage tab.
user-invocable: true
---

Add a new KPI metric end-to-end, from backend preset to dashboard chart. Follow these steps in order.

## Context — how the KPI pipeline works

```
KPIWriter (fred-core)              writes events to OpenSearch
  → preset handler                 queries OpenSearch, returns a typed Pydantic response
  → FastAPI route                  auto-mounted at GET /kpi/presets/<name>
  → OpenAPI schema                 regenerated from source
  → controlPlaneOpenApi.ts         generated from OpenAPI (never hand-edit)
  → controlPlaneApiEnhancements.ts re-exports hooks with short names (hand-edited)
  → AnalyticsPage/tabs/*Tab.tsx    consumes hooks, renders chart molecules
```

Available response types (`presets/common.py`) and their frontend molecule:
- `TimeSeriesResponse` — time-bucketed metric → `TimeSeriesLineChart`
- `ScalarResponse` — single integer for a time range → `KpiStatCard`
- `LabelValueResponse` — label+count pairs → `BarChart` (many items) or `PieChart` (2–5 items)
- `DistributionResponse` — fixed histogram buckets + median → `HistogramChart` (+ `KpiStatCard` for the median); build the buckets/median with `presets/distribution_utils.py`, never inline

If the shape doesn't fit, define a new Pydantic model in `common.py` and a matching molecule under `apps/frontend/src/rework/components/shared/molecules/`.

---

## Step 1 — Gather requirements

Before writing anything, confirm:
1. **Metric name** — the `metric.name` value written by `KPIWriter`. Find usages with `grep -r 'kpi\.count\|kpi\.emit\|kpi\.gauge\|kpi\.timer\|kpi\.log_llm' --include="*.py"`.
2. **Aggregation** — count of events, cardinality of a field, sum of a value, or terms breakdown?
3. **Response shape** — time series, scalar, or label/value list?
4. **Chart type** — which molecule (see table in Step 5)?
5. **Preset name** — short snake_case; becomes the URL segment and the React hook name.

---

## Steps 2 & 3 — Create and register the backend preset

See `apps/control-plane-backend/control_plane_backend/kpi/README.md` for the full preset authoring guide: file skeleton, OpenSearch query patterns, `resolve_interval()` usage, and registration in `__init__.py`.

**If your preset filters or groups on a new dimension field** (a `dim.*` key not yet in the index mapping), you must also:
1. Add the field to `KPI_INDEX_MAPPING` in `libs/fred-core/fred_core/kpi/opensearch_kpi_store.py` (under `dims.properties`); `ensure_ready()` adds it to already-deployed indexes on startup.
2. Past events stay unsearchable on that field until reindexed: say so in the PR's migration note.

Use these existing presets as models:
- Time-series: `sessions_over_time.py` (calendar buckets: `analytics_activity_over_time.py`)
- Period vs previous period: `analytics_overview.py` (helpers in `analytics_common.py`)
- Label/value: `user_token_usage_by_model.py`

If you wish to test your Opensearch query, the dev Opensearch is running in docker, you can query it with user `admin` and password `Azerty123_`.

---

## Step 4 — Regenerate frontend types

```bash
cd apps/frontend && make update-control-plane-api
```

This regenerates `src/slices/controlPlane/controlPlaneOpenApi.ts`. The new hook will be named:
`useHandlerControlPlaneV1KpiPresets<PascalCaseName>GetQuery`

---

## Step 5 — Wire the RTK Query hook

In `apps/frontend/src/slices/controlPlane/controlPlaneApiEnhancements.ts`, add a short-name alias at the bottom of the destructured export block:

```ts
useHandlerControlPlaneV1KpiPresets<PascalCaseName>GetQuery: use<ShortName>Query,
```

---

## Step 6 — Add i18n keys

Add keys to both locale files:
- `apps/frontend/src/locales/en/translation.json`
- `apps/frontend/src/locales/fr/translation.json`

Place them under `rework.analytics`. Minimum per chart:
- `title` — chart heading
- `valueLabel` — tooltip label (bar/line charts)
- `empty` — empty state (bar/pie charts)
- `total` — if adding a `KpiStatCard` companion

---

## Step 7 — Render in an AnalyticsPage tab

Each tab is a component in `apps/frontend/src/rework/components/pages/admin/AnalyticsPage/tabs/` receiving `{ timeRange, teamIds }`.

1. Import the hook from `controlPlaneApiEnhancements`.
2. Call it with the shared helpers from `analyticsQuery.ts`:
   ```ts
   const result = use<ShortName>Query(zonedKpiArgs(timeRange, teamIds), KPI_CACHE);
   ```
   Use `kpiArgs` when the preset takes no `tz`, and `platformOnly(teamIds)` instead of `KPI_CACHE` for a preset that is not team-scopable.
3. Place the chart in an existing `<AnalyticsSection>` or add one; tiles use `InfoTile` / `KpiStatCard`, values go through `analyticsFormat.ts`.
4. If the value belongs in the Excel export, add it in `control_plane_backend/kpi/export_workbook.py` with its texts in `export_texts.py` (a test checks them against the locales).

### Chart molecule reference

| Response type                  | Molecule              | Key props                                                               |
|--------------------------------|-----------------------|-------------------------------------------------------------------------|
| `TimeSeriesResponse`           | `TimeSeriesLineChart` | `rows`, `interval`, `valueLabel`, `isFetching`, `isLoading`, `isError` |
| `ScalarResponse`               | `KpiStatCard`         | `label`, `value`, `isLoading`, `isError`                               |
| `LabelValueResponse` (2–5)     | `PieChart`            | `rows`, `emptyMessage`, `isLoading`, `isError`                         |
| `LabelValueResponse` (many)    | `BarChart`            | `rows`, `valueLabel`, `emptyMessage`, `isLoading`, `isError`           |
| `DistributionResponse`         | `HistogramChart`      | `rows`, `valueLabel`, `emptyMessage`, `isLoading`, `isError` (median → a companion `KpiStatCard` with `unavailable` when null) |

---

## Step 8 — Verify

```bash
cd apps/control-plane-backend && make code-quality && make test
cd apps/frontend && make code-quality
```

If a new molecule was added, also verify it renders correctly in the browser.

---

## Step 9 — Close-out

Report:
- **Preset file** created and registered in `__init__.py`
- **Frontend types** regenerated
- **Hook alias** added to `controlPlaneApiEnhancements.ts`
- **i18n** keys added to both locale files
- **AnalyticsPage** tab updated with the new chart
- **Tests**: an offline preset test capturing the query body and parsing canned aggregations (see `tests/test_kpi_analytics_*.py`), plus the tab's case in `AnalyticsPage.test.tsx`
