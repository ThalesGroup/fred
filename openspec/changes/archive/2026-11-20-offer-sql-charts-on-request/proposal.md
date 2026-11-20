## Why

The SQL expert currently calls the chart tool whenever a chart might help, even when the user only asked for a textual answer. Charts should be a user choice unless the request already asks for one.

## What Changes

- Answer tabular questions without automatically rendering a chart.
- When a chart would clarify the answer, offer one in the response and wait for the user to opt in.
- Render a chart immediately when the user explicitly requests it, using actual query rows and the existing chart limits.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-chart-rendering`: Change SQL chart guidance from automatic rendering when useful to an opt-in offer, while honoring explicit chart requests.

## Impact

- Packaged tabular capability prompt and the `chat-chart-rendering` specification.
- No changes to the chart tool, chart payload, or chat renderer.
