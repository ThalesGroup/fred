## 1. Admission behavior

- [x] 1.1 Verify and cover disable/re-enable on the existing SQL state and admin UI, including retained rules, user/team exceptions and Free links; run the targeted platform-access backend and page tests.
- [x] 1.2 Add current platform-management permission as a shared eligibility source for direct and delegated people, including actor safeguards and preview; run targeted `fred-core` and control-plane tests for admin admission, role removal and authority failure.
- [x] 1.3 Remove the file whitelist gate and conflict checks, then cover direct and delegated admission with the SQL filter disabled.
- [x] 1.4 Remove the legacy Helm values, ConfigMap, mount, core module and obsolete frontend route, and document the operator migration from `users.txt`.

## 2. Free-link join history

- [x] 2.1 Add one migration and shared model for per-link/per-user join records with cascade deletion and stable pagination indexes; verify migration upgrade/downgrade and model tests.
- [x] 2.2 Record only successful new membership grants in the existing enrollment path; run targeted tests for failed joins, repeated joins, different links, later departure and link cleanup.
- [x] 2.3 Add a platform-admin-only paginated joiner API with current first name, last name, username and join time; regenerate the frontend API client and run targeted authorization/pagination tests.
- [x] 2.4 Add a localized joiner action and paginated list in the existing link manager; run its focused Vitest suite for loading, empty/error, permission and revoked/expired-link cases.

## 3. Integration and close-out

- [x] 3.1 Update the compact product/operator contract for the joiner API, retention and migration with no backfill; verify it agrees with the delta spec and implementation.
- [x] 3.2 Run focused backend/frontend integration checks and a real Playwright walkthrough using the local services, capturing the filtering action, administrator admission and a link's joiner list; record what was and was not exercised.
- [x] 3.3 Run the root quality gate once, review the full branch against `swift` with the audit-branch procedure and obtain an independent read-only review; resolve findings and record verification in the draft PR.
- [x] 3.4 Reconcile and validate the OpenSpec artifacts, sync and archive the completed change, then push the branch and open/update the draft PR linked to #3061; verify the PR shows the final commits and evidence.
