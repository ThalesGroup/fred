## 1. Backend

- [x] 1.1 Model `PlatformAccessPendingEmailRow` + control-plane Alembic migration (single head)
- [x] 1.2 Store: list, add, delete, and `claim_pending(user)` conversion under the policy lock
- [x] 1.3 `admitted()`: on refusal, try `claim_pending` and admit when converted
- [x] 1.4 API + service: `GET/POST/DELETE /admin/platform/access/pending-emails`, `409 platform_access_email_known`
- [x] 1.5 Tests: conversion, `email_verified: false`, case-insensitive match, known email refused, non-admin refused

## 2. Cleanup filter and bulk removal (backend)

- [x] 2.1 `overlap=rule|whitelist_only|unknown` on the users listing: rule evaluation on stored evidence, team members via one `lookup_subjects` per eligible team
- [x] 2.2 `POST /admin/platform/access/users/revoke` (`user_ids` or `all_matching` + `excluded_ids`), atomic, actor safeguard
- [x] 2.3 Tests: unknown evidence listed only under "To check", both filters, counts, select-all with exclusions, safeguard refusal, non-admin refused

## 3. Frontend

- [x] 3.1 Regenerate the control-plane client
- [x] 3.2 Pending emails list with Remove on Whitelist > Users
- [x] 3.3 Add dialog: "Add <email>" when the search is a valid email with no match
- [x] 3.4 Chip bar (All / Admitted by the rule / Whitelist only / To check) with per-chip counts
- [x] 3.5 Row checkboxes, header select-all across pages, bulk bar with Remove and confirmation
- [x] 3.6 fr/en strings, tests

## 4. Close-out

- [x] 4.1 Contract doc entry, migration note, `make code-quality` + `make test`

## Verification

- `apps/control-plane-backend`: `pytest tests/test_platform_access.py tests/test_table_ownership.py` → 74 passed, 12 skipped (PostgreSQL-only); ruff, `ruff --select I`, basedpyright clean.
- `libs/fred-core`: `pytest fred_core/tests/security/test_platform_access.py fred_core/tests/security/test_oidc_provider_tokens.py` → 83 passed.
- `apps/frontend`: `vitest run PlatformAccessPage DataTable` → all passed; `tsc --noEmit`, prettier, eslint clean.
- `alembic heads` → single head `e5b1c9d3a742`. Not yet run: a real `alembic upgrade head` on PostgreSQL, and the owner's live test.
