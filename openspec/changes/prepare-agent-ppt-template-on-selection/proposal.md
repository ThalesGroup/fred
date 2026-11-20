# Proposal

## Why

Selecting an agent's PowerPoint template currently stores the file only in the browser. Authors see no upload or worker activity until they save the agent, which makes the template control appear unresponsive and delays a potentially long analysis.

## What Changes

- Start the bounded template upload and durable PPT Builder preparation when the file is selected, in both agent creation and editing.
- Keep the upload and preparation in a temporary, user-scoped draft until Save atomically adopts its current revision. Cancel or close leaves the agent unchanged and lets the draft expire.
- Show transfer, preparation, result, and failure states in both agent form layouts. Saving may proceed after transfer completes while preparation continues in the worker.
- Fence replaced files and changed analysis settings so stale results cannot become the agent's active template. Retain the existing save-time upload route for other clients.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ppt-builder`: Agent template transfer and preparation begin on selection, with a temporary draft that is adopted only on Save.

## Impact

- Agent form, PPT Builder UI and generated control-plane API types.
- Control-plane upload, preparation admission, draft authorization, persistence, cleanup and agent save APIs; one database migration for draft ownership and expiry.
- The shared preparation work contract and fred-agents worker dispatch; PPT Builder analysis logic remains in the capability.
- Focused frontend, API and migration tests, plus a local worker check; agent template UX and product contract documentation.
