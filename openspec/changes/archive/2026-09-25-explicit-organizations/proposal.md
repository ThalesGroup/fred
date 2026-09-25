## Why
Fred conflates platform governance with the hard-coded `organization:fred`. Issue #2800 introduces isolated organizations while making the existing production deployment upgrade transparently.

## What Changes
- Persist organizations and associate community teams with them.
- Separate platform organization management from organization-scoped administration.
- Keep `fred` as the default organization ID, with an optional configurable display name (default: `Fred`).
- Automatically preserve existing administrators as both platform and default-organization administrators during upgrade.
- Add backend organization management and migration/isolation tests; no UI changes.

## Capabilities
### New Capabilities
- `organizations`: Organization identity, scoped administration, isolation, and compatible bootstrap/migration.
### Modified Capabilities
None; existing published specs do not cover this surface.

## Impact
Control-plane organization/team APIs, configuration, bootstrap/reconciliation, SQL migrations, and shared ReBAC contracts/helpers. Existing team resources and IDs remain intact. No workflows, workspaces, filesystem changes, cross-organization sharing/transfers, or new dependencies are intended.
