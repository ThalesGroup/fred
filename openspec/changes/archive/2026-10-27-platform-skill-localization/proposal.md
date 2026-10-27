## Why

Workplace users should see skill titles and descriptions in their interface language without changing English instructions or canonical commands.

Tracking: #3077. Scope and acceptance approved in the conversation on 2026-10-27; developer explicitly requested the complete local implementation.

## What Changes

- Add frontend French/English presentation of packaged skills in menus, badges, previews, history and activity.
- Carry reliable packaged provenance with catalog and successful-load metadata; custom name collisions retain authored text.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: Workplace users should see skill titles and descriptions in their interface language without changing English instructions or canonical commands.

## Impact

SDK provenance metadata, runtime catalog/activity and frontend i18n/presentation/tests.

## Non-goals

No push/PR, skill editing UI, per-team/agent enablement, new tools or execution permissions.

