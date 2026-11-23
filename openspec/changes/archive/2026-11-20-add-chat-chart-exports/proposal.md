## Why

Users can inspect chart data in chat but cannot save the data or graphic for use outside Fred.

## What Changes

- Add Excel workbook download for the rows stored in each valid chart part.
- Add PNG download for plotted chart views.
- Label the actions in English and French and report export failures in the UI.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-chart-rendering`: Expose client-side Excel and PNG downloads for rendered charts.

## Impact

The frontend chart renderer, its export utility, translations, and focused tests change. The chart payload and backend APIs remain unchanged. Excel covers the bounded rows present in the chart part.
