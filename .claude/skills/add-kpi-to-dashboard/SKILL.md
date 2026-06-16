---
name: add-kpi-to-dashboard
description: Add a new KPI metric to the analytics dashboard. Covers: creating a backend preset, regenerating frontend types, wiring the RTK Query hook, and rendering it on AnalyticsPage.
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
  → AnalyticsPage.tsx              consumes hooks, renders chart molecules
```

Available response types (`presets/common.py`) and their frontend molecule:
- `TimeSeriesResponse` — time-bucketed metric → `TimeSeriesLineChart`
- `ScalarResponse` — single integer for a time range → `KpiStatCard`
- `LabelValueResponse` — label+count pairs → `BarChart` (many items) or `PieChart` (2–5 items)

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

Use these existing presets as models:
- Time-series: `active_users_over_time.py`
- Scalar: `unique_users_total.py`
- Label/value: `sessions_by_scope.py`

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

## Step 7 — Render on AnalyticsPage

Edit `apps/frontend/src/rework/components/pages/admin/AnalyticsPage/AnalyticsPage.tsx`.

1. Import the hook from `controlPlaneApiEnhancements`.
2. Call it at the top of the component:
   ```ts
   const {
     data: <name>Data,
     isLoading: <name>IsLoading,
     isError: <name>IsError,
   } = use<ShortName>Query(
     { since: timeRange.since, until: timeRange.until },
     { refetchOnMountOrArgChange: true },
   );
   ```
   Add `isFetching` for time-series charts (they show a loading overlay).
3. Place the chart in an existing `<KpiSection>` or add a new one, inside a `<KpiRow>`.

### Chart molecule reference

| Response type                  | Molecule              | Key props                                                               |
|--------------------------------|-----------------------|-------------------------------------------------------------------------|
| `TimeSeriesResponse`           | `TimeSeriesLineChart` | `rows`, `interval`, `valueLabel`, `isFetching`, `isLoading`, `isError` |
| `ScalarResponse`               | `KpiStatCard`         | `label`, `value`, `isLoading`, `isError`                               |
| `LabelValueResponse` (2–5)     | `PieChart`            | `rows`, `emptyMessage`, `isLoading`, `isError`                         |
| `LabelValueResponse` (many)    | `BarChart`            | `rows`, `valueLabel`, `emptyMessage`, `isLoading`, `isError`           |

Use `compactFirst` on `<KpiRow>` when the first child is a `KpiStatCard`, `compactLast` when the last is.

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
- **AnalyticsPage** updated with the new chart
- **Tests**: pass / none needed (preset queries are integration-tested against a live OpenSearch)
