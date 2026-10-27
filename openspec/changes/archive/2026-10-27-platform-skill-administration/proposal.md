## Why

Feature managers need a global inventory and a shared per-skill opt-out that remains effective across runtime replicas and existing conversations.

Tracking: #3301, #3303; parent #3081. Scope and acceptance approved in the conversation on 2026-10-27; developer explicitly requested the complete local implementation.

## What Changes

- Add Administration > Features > Skills and global packaged inventory with source status.
- Persist per-skill overrides, default enabled, and resolve trusted policy on every turn/resume.
- Prevent new disabled-skill loads across ReAct, Deep, pins, children and capability reads; preserve already-read history.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: Feature managers need a global inventory and a shared per-skill opt-out that remains effective across runtime replicas and existing conversations.

## Impact

Control-plane administrative API/store/migration/binding; runtime catalog/filtering and enforcement; frontend admin UI and generated clients.

## Non-goals

No push/PR, skill editing UI, per-team/agent enablement, new tools or execution permissions.
