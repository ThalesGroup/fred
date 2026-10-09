## Why

The filtering action is disconnected from the page header, and the Whitelist view mixes individual and team management. Activation also needs explicit acknowledgment when existing users have not been imported, so administrators can choose deliberately before access restrictions apply.

Tracking: GitHub issue #2965, PR #2966.

## What Changes

- Place the filtering action at the top right of the shared page header, available across Rules and Whitelist.
- Keep the Whitelist heading and introduce Users and Teams sub-tabs. Import and individual exceptions belong to Users; live team authorization belongs to Teams.
- Extend the existing activation dry-run modal with an explicit choice when the initial import is incomplete: continue without importing, or navigate to Whitelist > Users without activating.
- Preserve saved-policy, revision, admission-source and actor-lockout safeguards. Unknown import status cannot silently bypass the warning.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: section navigation and explicit activation/import confirmation.

## Impact

Frontend PlatformAccessPage, PlatformAccessActivationDialog, their focused tests, shared-component usage and English/French translations. Update the existing UX documentation and migration guide; no backend, generated API, database or dependency changes.
