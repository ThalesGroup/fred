## Why

The admin Analytics page is a flat set of technical charts; it does not answer
"is the platform adopted, by whom, at what cost". Tracking issue: #3310.

## What Changes

- New Analytics page: fixed header (team scope, user filter, period with
  comparison, Excel export) and seven tabs (Overview, Adoption, Usage, Teams,
  Agents and tools, Quality and cost, Technical).
- One KPI preset per tab section; old presets the page no longer reads are deleted.
- Presets take repeated `team_ids`; team-scoped reads need the new team
  permission `can_read_analytics` (team admins).
- Costs in euros; server-side `.xlsx` export of the current view.
- Team usage page reuses the views for team admins; members keep "My usage".
- Platform page only: filter by stored platform-access user attributes.

## Capabilities

### New Capabilities

- `platform-analytics`: the admin Analytics page, its reads and its export.

### Modified Capabilities

None.

## Impact

Control-plane `kpi/` (presets, scope, export, `openpyxl`), fred-core OpenFGA
model and `usd_per_eur`, regenerated `controlPlaneOpenApi.ts`, frontend
`AnalyticsPage/` and `TeamUsagePage/`. Capability usage figures need the KPI
dims of `kpi-analytics-dims` (separate PR); without them the table is empty.
