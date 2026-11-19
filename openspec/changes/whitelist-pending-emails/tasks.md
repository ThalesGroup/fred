## 1. Backend

- [x] 1.1 Model `PlatformAccessPendingEmailRow` + control-plane Alembic migration (single head)
- [x] 1.2 Store: list, add, delete, and `claim_pending(user)` conversion under the policy lock
- [x] 1.3 `admitted()`: on refusal, try `claim_pending` and admit when converted
- [x] 1.4 API + service: `GET/POST /admin/platform/access/pending-emails`, `POST .../pending-emails/remove`, `409 platform_access_email_known`
- [x] 1.5 Tests: conversion, `email_verified: false`, case-insensitive match, known email refused, non-admin refused

## 2. Cleanup filter and bulk removal (backend)

- [x] 2.1 `overlap=rule|whitelist_only|unknown` on the users listing: rule evaluation on stored evidence, team members via one `lookup_subjects` per eligible team
- [x] 2.2 `POST /admin/platform/access/users/revoke` (`user_ids` or `all_matching` + `excluded_ids`), atomic, actor safeguard
- [x] 2.3 Tests: unknown evidence listed only under "To check", both filters, counts, select-all with exclusions, safeguard refusal, non-admin refused

## 3. Frontend

- [x] 3.1 Regenerate the control-plane client
- [x] 3.2 Pending chip switching the table to pending emails, with selection and bulk removal
- [x] 3.3 Add dialog: "Add <email>" when the search is a valid email with no match
- [x] 3.4 Chip bar (All / Admitted by the rule / Whitelist only / To check) with per-chip counts
- [x] 3.5 Row checkboxes, header select-all across pages, bulk bar with Remove and confirmation
- [x] 3.6 fr/en strings, tests

## 4. Close-out

- [x] 4.1 Contract doc entry, migration note, `make code-quality` + `make test`

## Verification

- Independent review (base `origin/swift`, head `b702a9fd9`): 7 findings. Fixed: per-person fallback now only after a lookup reaches the ListUsers cap; a concurrent claim of the same pending email now admits the losing request; `IconButtonMenu` start alignment made opt-in; duplicate `aria-description` on chips dropped; migration note label; the rejected email is named when adding fails. Kept by design: a select-all removal re-resolves the matching set at confirm time.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` → 2252 passed, 10 skipped, plus `test_authz_endpoint_matrix` after adding the five new routes to `authz-endpoint-matrix.yaml`; `ruff --select I` clean.
- `libs/fred-core`: `make code-quality` clean; `make test` → 1309 passed.
- `apps/frontend`: `make code-quality` (tsc, prettier, eslint) clean; `make test` → 5225 passed, 8 skipped.
- Alembic: single head `e5b1c9d3a742`; real `alembic upgrade head` on the local PostgreSQL (backup taken first).
- Tooltip placement measured in headless Chrome: chip tooltips end 4px above chips at the same height on one row.
- Owner live test on the local stack: pending email, chips, counts, tooltips, selection, bulk removal, "Add all existing accounts" confirmation.
