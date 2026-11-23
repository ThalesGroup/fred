## Why

Chat charts currently offer only bar, line, area, and pie plots, so different SQL results often look alike. A broader but data-appropriate set of Recharts views will make comparisons and distributions easier to read. Long-form grouped bars currently share one color, so their groups are hard to distinguish.

## What Changes

- Extend `chart.render` with common flat-row views: horizontal and stacked bars, stacked area, donut, scatter, radar, radial bar, funnel, treemap, and composed bar/line charts.
- Support long-form grouped bars with `group_key`. Give each group a distinct color within its chart, consistent across x-axis categories.
- Describe when each view fits the result in the tool description and SQL guidance; retain the existing opt-in threshold for generating charts.
- Validate view-specific numeric and series constraints in the tool and restored chat renderer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-chart-rendering`: accepted chart types, faithful rendering, color distinction, and chart selection guidance.

## Impact

- SDK chart schema and built-in catalog, generated runtime OpenAPI type, chat Recharts renderer, SQL guidance, focused tests, and the existing chart spec.
- No new data fetches, SQL execution path, dependency, or persistence format. Existing chart parts remain valid.
