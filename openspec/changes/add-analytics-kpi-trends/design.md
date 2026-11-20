## Decisions

- **Affordance:** an optional action on `KpiStatCard`, a medium `show_chart` IconButton beside the info hint; the value is not clickable. Tiles without a series get no icon. Funnel rows (visitors, active users) get the same button at the end of the row.
- **Data:** the dialog reads `analytics_activity_over_time` with the tab's exact arguments (scope, user filter, tz, bucket), skipped until it opens, so the RTK cache is shared with the tab charts.
- **Additive counts** (conversations, messages, cost, tokens, CO2e): cumulative line computed in the frontend; its last point equals the tile value. Tokens are plotted as one input + output total, footprint in kg CO2e only (kWh stays in the tile caption).
- **Distinct counts** (active users, visitors): one line per bucket, with a note giving the period value, since per-bucket values do not add up to it.
- **Rendering:** central `Dialog` (single "Fermer" button) with `MultiSeriesLineChart` in primary, labels from `bucketSeries`.
