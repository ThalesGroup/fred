## Why

Issue #3527: tabular details must expose the actual API usage available for the model call that requested an action. Guessed payload counts were rejected. The preview notices must also fit into one compact sentence while preserving the original syntax-colored presentation. The developer explicitly requested this follow-up after the source and scope of the available counters were explained.

## What Changes

- Forward optional, explicitly scoped model-call input/output counters through runtime events, stored history and the tabular drawer, without changing turn billing totals.
- Preserve missing values as unavailable and identify counts shared by multiple calls from one model response.
- Combine preview limits and full-copy information into one localized sentence.
- Recover the reported local conversation's counters only from recorded model observations matched by exact tool-call identifiers.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: recorded API model usage in tool details, and compact preview information.

## Impact

Additive SDK/runtime/history metadata and regenerated frontend client. Reuses existing shared history storage; no table, migration, new service, model invocation or trace lookup in the request path. Existing records without counters remain readable. Extends PR #3528 under Epic #2738.
