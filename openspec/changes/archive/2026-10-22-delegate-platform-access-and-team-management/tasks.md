## 1. Authorization model

- [x] 1.1 Add `platform_access_manager` and `can_manage_platform_access` to the OpenFGA model; regenerate its JSON and verify the schema authorization tests cover role isolation, team registry read and `platform_admin` inheritance.
- [x] 1.2 Wire the new role and permissions into Python enums, platform-role grant/revoke/list, and bootstrap reporting; verify focused platform-role and bootstrap tests show the new role without unrelated powers.

## 2. Server enforcement

- [x] 2.1 Gate the complete Platform Access administration routes and live admission bypass on `can_manage_platform_access`; verify focused tests cover filtering, rules, whitelist, T0, role revocation and authority-unavailable behavior.
- [x] 2.2 Keep combined team admission and Free updates under `can_manage_platform_access`; verify focused tests cover platform access manager success, team manager denial, actor lockout and unchanged audit behavior.
- [x] 2.3 Gate Free-link creation, history, joiners, recovery, revocation and cleanup on `can_manage_platform_access`, retaining own-human token checks; verify focused link tests cover platform access manager success and team manager denial.

## 3. Frontend and contracts

- [x] 3.1 Regenerate the control-plane OpenAPI client and add the new bootstrap capability, role option, navigation and route gates; verify focused frontend tests for access-manager and team-manager isolation.
- [x] 3.2 Adapt Admin Teams so `platform_access_manager` can manage Free, `team_manager` retains team creation only, and registry editing remains admin-only; verify focused UI tests for all three roles and no permission-based request leakage.
- [x] 3.3 Update French/English role labels and help text plus the endpoint matrix, REBAC guide and product contract; verify localization keys and documented permissions match the API and OpenFGA model.

## 4. Verification and close-out

- [x] 4.1 Run the relevant backend, frontend and OpenFGA authorization tests, then the root quality gate once for the completed series; record exact commands and outcomes in the PR.
- [x] 4.2 Review the full branch against `swift` using the branch audit procedure and obtain an independent read-only review of the authorization change; resolve findings and record base/head, coverage and exclusions in the PR.
- [x] 4.3 Reconcile the final OpenSpec artifacts, validate and sync the deltas, archive the completed change, then push the topic branch and open an English draft PR linked to #3235; verify the PR diff and title.
