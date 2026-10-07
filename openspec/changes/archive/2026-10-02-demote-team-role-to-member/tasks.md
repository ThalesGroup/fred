## 1. Track and implement

- [x] 1.1 Create or reuse a GitHub issue and a dedicated branch for this change; verify the branch and issue refer to the same scope and preserve unrelated local edits.
- [x] 1.2 Update `revoke_team_member_role` to grant direct `team_member` before removing a sole elevated role, after the last-admin and both permission checks; verify focused service tests for active and pending admins, editors and analysts, an existing direct baseline, and a sole member.
- [x] 1.3 Cover write failure and retry, shared locking with explicit removal and charter promotion, and higher-consistency role reads with focused service tests.

## 2. Integrate and close

- [x] 2.1 Verify the existing members-table toggle calls the revoke endpoint for active and pending admins and renders the returned simple-member state; run the focused frontend test, changing the UI only if this behavior needs it.
- [x] 2.2 Update `REBAC.md`, `CONTROL-PLANE-PRODUCT-CONTRACT.md`, and the superseded charter design text, then add the required migration note; verify the docs describe both demotion and explicit member removal.
- [x] 2.3 Run the root quality check and relevant backend/frontend tests, review the diff, reconcile the change artifacts, and sync the durable spec; verify the checks and independent review pass.
