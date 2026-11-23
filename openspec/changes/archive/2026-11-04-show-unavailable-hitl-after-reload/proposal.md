## Why

Managed chat reconstructs a pending HITL card whenever history lacks its response, even if the runtime has already consumed the occurrence or no longer has a matching pause. The user then receives a 409 and reload restores the same unusable card. Follow-up to #2337; refresh support and execution recovery remain outside scope as requested.

## What Changes

- Enrich history reads with an authoritative, read-only availability signal for unanswered HITL occurrences in the trailing exchange.
- Restore answer controls only for confirmed pending occurrences; show a noninteractive, localized unavailable notice for occurrences that can no longer accept a response.
- Replace the misleading waiting/running presentation of the unavailable question with a neutral unavailable state, without inventing a successful or failed tool result.
- Distinguish an unavailable occurrence from an availability lookup failure; preserve history and offer a retry of the lookup on failure.
- Preserve genuinely pending cards across reload, including unanswered siblings, and retain server-side admission checks for races after loading.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: reconstruct HITL actions from current runtime availability rather than incomplete history alone.

## Impact

Runtime history endpoint and shared checkpoint/claim reads, history response schema and generated client, managed-chat reconstruction and trace presentation, both locales, tests and compact contracts. Existing history/checkpoint tables and configured pools are reused. No migration, new execution endpoint, claim release, automatic resume, disconnected-turn history persistence, background execution, or repair of existing rows is included. Existing historical inconsistencies can be displayed safely through the read-time signal.
