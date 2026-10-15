## Why

Platform access currently treats Fred's `users` table as the user directory even when `security.user_directory` selects Keycloak. Its initial import can grant exceptions to profileless technical rows while missing Keycloak accounts that have not reached Fred, and administrators cannot add those accounts from the whitelist. The team membership flow already uses the configured directory and shows the expected profiles.

## What Changes

- Resolve whitelist identities and search from Keycloak when `user_directory: keycloak`, including federated accounts known to Keycloak and accounts created directly there. Use Fred's `users` table when `user_directory: local`.
- Keep individual admission exceptions in Fred. Permit a platform administrator to grant an exception to a selected Keycloak identity before its first Fred request, while validating that the identity still exists.
- Make the one-time initial-import preview and commit enumerate the configured directory's human identities. Evaluate rule matches only from Fred's fresh verified claim observations; import identities without reliable evidence conservatively.
- Show existing exceptions with current directory profiles. Preserve an exception whose identity is no longer resolvable, identified by its id so an administrator can inspect and remove it. Directory failures are explicit errors, not an empty list or a silent switch to Fred's local profiles.
- Keep completed imports fixed and preserve deliberate removals. Existing installations may need an explicit follow-up reconciliation; a code upgrade must not rerun T0 silently.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: The configured directory supplies identities for individual exception management and the fixed initial population, while Fred retains admission state and verified rule evidence.

## Impact

- Control-plane platform-access routes and services, the existing user-directory service, and the SQL store for exception paging and reference rows.
- Generated OpenAPI and frontend client if endpoint parameters or response types change; whitelist page and add dialog.
- Focused backend and frontend tests, platform access contract and UX documentation, and an operator migration note if existing completed imports require operator action.
