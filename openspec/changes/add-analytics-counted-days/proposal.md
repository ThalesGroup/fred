## Why

Weekends and public holidays pull the per-day analytics down and make periods
hard to compare. Tracking issue: #3310.

## What Changes

- Presets and the export take `exclude_weekends` and `exclude_holidays`
  (default `false`); excluded local days leave every figure.
- The analytics pages send a per-viewer choice, both excluded by default.

## Capabilities

### Modified Capabilities

- `platform-analytics`: counted days.

## Impact

Control-plane `kpi/counted_days.py`, the day-filterable presets and the
export; regenerated `controlPlaneOpenApi.ts`; a settings dialog on both
analytics pages.
