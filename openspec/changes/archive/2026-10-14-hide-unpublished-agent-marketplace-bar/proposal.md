## Why

Most team agents are never published. Showing a "Not published" bar on each of their cards adds visual weight and height without helping the usual task of finding and using an agent.

## What Changes

- Hide the entire marketplace state bar, including its background and reserved space, when an agent has no visible publication state.
- Keep the existing Published, Modified, and Removed states for agents that have been published, subject to their current role and team visibility rules.
- Keep Publish in the editor's more menu.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-marketplace`: Change when the team agent card renders its marketplace state bar.

## Impact

Frontend team agent cards, their targeted tests, the marketplace UX guidance, and the existing `agent-marketplace` specification. No API or database changes.
