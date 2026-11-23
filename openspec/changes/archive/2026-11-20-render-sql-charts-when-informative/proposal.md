## Why

The current opt-in guidance prevents the SQL expert from rendering a chart even when it would make the answer materially clearer. The guidance should preserve that useful behavior without turning every tabular result into a chart.

## What Changes

- Render a chart automatically when it materially clarifies a trend, comparison, or distribution in the answer.
- Answer without a chart when text or a compact table conveys the result just as clearly.
- Continue rendering charts on explicit user request, using actual query rows and disclosing truncation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-chart-rendering`: Replace the opt-in-only SQL chart guidance with selective, informative automatic charting.

## Impact

- Packaged tabular capability prompt and `chat-chart-rendering` specification.
- No change to chart tool registration, payload validation, or frontend rendering.
