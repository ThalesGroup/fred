## Why

Users need two independent token volumes for each tool: all parameters sent by the model to that tool, and the complete result returned to the model. Provider prompt/completion totals include other context and cannot substitute for those volumes; hiding the totals does not fulfill this requirement. Tracked by #3527, draft PR #3528, Epic #2738.

## What Changes

- Add per-call tool payload counts, identified by session/exchange/call ID and separate from model API usage and billing.
- Count the complete parameter JSON and complete model-visible result with the verified tokenizer for the actual model. Record tokenizer/model identity and measurement provenance; never estimate from characters or differences between requests.
- Propagate counts through runtime events, existing JSON history and SSE, so live and reloaded details agree.
- Restore two compact badges, `Tokens envoyés` and `Tokens reçus`, beside existing status/duration. Tooltips define the directions. Do not restore the rejected explanatory paragraph or change SQL/JSON presentation.
- Start with verified Mistral Small 4 support, the model used by David v3. Unverified model/tokenizer bindings and missing historical measurements must remain explicitly unavailable, not guessed or zeroed.
- Preserve the separately corrected five-row preview with every returned column and complete supported copying. Preview limits never affect token counts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: expose isolated per-tool parameter/result token volumes while prohibiting full-context model attribution.

## Impact

Additive SDK runtime/history contracts and regenerated frontend types; managed tool execution and model/tokenizer resolution; exact Mistral tokenizer dependency/assets; frontend drawer/locales; runtime/UX/operator documentation. Reuse existing Postgres JSON history with no new table, production backfill or model re-execution. Model API usage and existing billing remain unchanged. The implementation requires scope/acceptance confirmation before applying under AGENTS.md.
