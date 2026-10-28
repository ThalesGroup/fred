## Why

The fast PPTX extractor, used for chat attachments and for PowerPoint files attached to a mail, drops speaker notes and native charts, so questions about them get no answer. The library processors already read speaker notes. Found while testing #3306.

## What Changes

- Append each slide's non-empty speaker notes under "Notes:".
- Render each native chart as its title, type and cached values in a table, capped at 50 categories x 10 series.

## Capabilities

### New Capabilities

- `pptx-fast-extraction`: what the fast PPTX extractor keeps from a deck.

### Modified Capabilities

None.

## Impact

`lite_pptx_to_md_processor.py` and one test module in knowledge-flow-backend. No configuration, API or data change.
