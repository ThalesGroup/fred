## Why

Analytics tiles show one value for the period; an admin cannot see how it got there. Tracking issue: #3310.

## What Changes

- Tiles whose value has a per-bucket series in `analytics_activity_over_time` get a "show trend" icon button that opens a dialog with that trend. Slice 1 covers conversations, messages, estimated cost, tokens, footprint, active users and visitors.
- `analytics_activity_over_time` points gain `co2e_grams` and `kwh`.
- Deferred: slice 2, tiles that need a new per-bucket series; slice 3, current-state values (agents, storage, members).

## Capabilities

### Modified Capabilities

- `platform-analytics`: KPI trend dialog.

## Impact

Control plane: two extra keys in the activity preset's `values` map (no schema change, generated client unchanged). Frontend: `KpiStatCard` action slot, `InfoTile`, `AdoptionFunnel`, a `KpiTrendDialog`. Contract dated line, Help Center, `COMPONENT-UX.md`. Also: `Dialog` returns focus without a keyboard ring after a click.
