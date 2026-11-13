## Why

The SQL trace drawer shows only five recorded result rows with no way to inspect the remaining rows. Users need ten rows initially and a small action to reveal ten more at a time while retaining the existing readable SQL/JSON presentation. Tracked by #3527, draft PR #3528, Epic #2738.

## What Changes

- Start SQL result inspection with up to ten recorded rows and reveal the next ten rows on each click of a small localized button below the JSON preview.
- Keep previously revealed rows visible, show every returned column with its complete name, and retain existing SQL/JSON syntax colors, status, duration and complete-copy behavior.
- Show the actual remaining count when fewer than ten rows remain; remove the action when all recorded rows are visible. Reset to ten rows when changing or reopening the inspected call.
- Reveal data already present in the recorded result, without re-executing SQL or changing the tool's returned-row limits, its own notices or model-visible response.
- Cancel the unimplemented per-tool token-counting proposal and remove the unused attribution code introduced for it: dedicated model-call usage fields, extraction, event/history/frontend propagation and obsolete tests. Keep tool token badges and the rejected model-usage explanation absent; existing conversation/model accounting remains unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: progressive SQL trace inspection in ten-row increments, preserving responsiveness and complete column visibility.

## Impact

Frontend SQL trace detail, row-preview helper, French/English locales and existing component interactions/tests; removal of unused attribution fields/helpers in fred-core, SDK, runtime, history/SSE consumers and regenerated runtime OpenAPI/client. Reuse existing design-system controls and the stored response; no backend endpoint, tokenizer, provider call, dependency, database or shared state is added. Reconcile the existing runtime contract, UX and migration guidance when implementing. The developer's follow-up explicitly requests implementation and removal of the legacy token code.
