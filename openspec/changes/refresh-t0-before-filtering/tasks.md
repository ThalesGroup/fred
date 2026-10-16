## 1. Durable removal tracking

- [x] 1.1 Add the latest-removal model and settings completeness flag, declared table ownership and required schema checks; create one linear control-plane migration. Verify one Alembic head, a real local PostgreSQL upgrade and initialization for fresh settings versus an already-completed import.
- [x] 1.2 Record actual manual and T0 exception removals in the same transaction as revocation. Verify no-op revocation creates no history, failed revocation rolls it back, repeated removal updates it and a new reader sees persisted history.

## 2. T0 preview and refresh API

- [x] 2.1 Extend the existing preview and import contracts with explicit typed modes, confirmation preconditions, history completeness and actual additions. Verify initial-import calls remain compatible and completed status does not scan the directory; regenerate OpenAPI and the frontend client with `make update-control-plane-api` from `apps/frontend`.
- [x] 2.2 Implement both candidate sets and atomic refresh under the existing mutation lock, retaining bounded directory/SQL work and existing grant provenance. Reject preservation with incomplete history and establish the new baseline only after a successful full refresh. Extend `tests/test_platform_access.py` for new identities, both removal origins, legacy reset requirements, inclusion, preserved grants, both directory modes, unknown evidence, failures and refresh with active filtering.
- [x] 2.3 Check policy and completion preconditions at commit, advance completion and emit one audit summary with mode and actual additions. Verify stale replay after removal, concurrent PostgreSQL refreshes, policy conflicts and activation during preparation, zero additions and no audit on failure; retain ordinary completed-retry tests.

## 3. Refresh dialog

- [x] 3.1 Expose a small refresh icon after completion with filtering on or off, with the two choices and preservation initially selected when history is reliable. If history is missing, require inclusion and warn explicitly about full recalculation and the return of removed people before confirmation. Use shared dialog/selection controls and generated hooks; add French and English labels, mode-specific estimates, success counts and conflict/error handling. Verify with focused page/dialog tests, including no import on opening, cancellation, failed reset, both choices after successful reset and delayed responses after a mode change.
- [ ] 3.2 Verify integration with existing cache invalidation and activation: refreshed whitelist/status, no mutation on navigation or activation, fresh completion preconditions and successful refresh if filtering becomes active without changing that switch. Run the PlatformAccessPage component tests and inspect the dialog in a browser for keyboard access, warnings and narrow layouts.

## 4. Documentation, review and delivery

- [x] 4.1 Update `CONTROL-PLANE-PRODUCT-CONTRACT.md`, `COMPONENT-UX.md` and one English migration note covering schema ordering, incomplete historical test data and rollback. Verify `make migration-check` and review those documents against the final API/UI.
- [x] 4.2 Run affected offline suites and root `make code-quality` once near commit; run raw type checking where baselines apply and record results. Apply `audit-branch` against the actual PR base, obtain the independent review required by AGENTS.md and review async/lock behavior with `fred-performance-reviewer`; resolve findings and record evidence in this task file or the PR.
- [ ] 4.3 Reconcile these artifacts with verified behavior, sync and archive the completed change using the repository procedures. Commit reviewable blocks, push the topic branch and open a draft PR linked to issue 3140; verify its description includes validation, review coverage and migration impact.

## Verification evidence (2026-10-16)

- Scope approved by Simon before implementation, with a small refresh icon as the entry point.
- Control-plane focused platform/ownership tests: 65 passed, 12 skipped. Real local PostgreSQL migration, concurrent refresh and off-lock classification: 3 passed. New tests cover both removal origins, rollback, no-op removal, provenance, legacy reset, stale replay, zero additions, activation/policy races during preparation and one actual-count audit summary.
- Frontend PlatformAccessPage directory: 5 files, 123 tests passed. TypeScript `tsc --noEmit` passed. The real shared Dialog and Select are exercised by the refresh tests.
- `make update-control-plane-api` regenerated backend OpenAPI and the committed frontend client; backend `openapi.json` is ignored by the repository.
- `make migration-check`: one valid new declaration. `alembic heads`: one head, `d4e8b2a6f091`. The PostgreSQL migration test upgrades an isolated legacy schema and verifies completed/uncompleted settings and fresh defaults.
- fred-core full suite using the existing control-plane Python 3.12.8 / SQLite 3.47.1 interpreter: 1257 passed, 1 skipped, 42 deselected. The fred-core venv uses Python 3.12.3 / SQLite 3.45.1 and fails three unchanged accent-search tests with SQLite `parser stack overflow`; reproduced with the unchanged `fold_accents` SQL expression. No search code changed.
- Independent read-only `audit-branch` and `fred-performance-reviewer` review covered base/HEAD `d8aa32f752bd8376a643482cb00c8bd02e00d058` plus the working-tree implementation and affected consumers. Two findings (accidental join argument and stale ownership expectation) were fixed and re-reviewed; no remaining actionable finding. No new admission hot-path history scan, LLM/tool call or KPI was introduced.
- Browser visual/keyboard inspection for task 3.2 remains unavailable: CUA reports no connected browser and the in-app browser is unavailable. Automated dialog tests pass; visual verification is not claimed. Leave the change active until this check and close-out can be completed.

- Full control-plane offline suite: 1966 passed, 10 skipped, 13 deselected. Scoped raw type check of the control-plane package and touched tests: 0 errors; full raw check reports two pre-existing errors in ignored `target/company-jwt-provisioning` scripts. Raw fred-core: 0 errors, 2 pre-existing unreachable-code warnings.
- Root `make code-quality` was blocked only by those ignored local scripts. Root `UV_NO_SYNC=1 make code-quality` passed on staged tree `8030cd3f8fad3700e3904afc4102a420c4ec8661`, materialized under `/tmp` without ignored developer artifacts and reusing installed Python dependencies. All component quality gates, frontend TypeScript, Prettier and ESLint passed. User files and baseline suppressions were not changed to obtain the result.
- Simon requested a general table-reuse preference in `AGENTS.md` and explicitly allowed keeping this removal table when clearer. The design now records the old-reader compatibility reason for retaining the separate table. This small governance addition uses the lightweight documentation workflow; no separate OpenSpec capability is needed.

- Wording follow-up: French and English visible titles, confirmation, warnings and success messages use whitelist/import wording without "T0". Translation keys and placeholders are unchanged; JSON and targeted formatting checks pass. This localized wording correction uses the lightweight workflow.

## Approved follow-up

- [x] 5.1 Allow explicit refresh with active filtering, including activation during preparation, without changing the switch or stale-confirmation protection. Use generic import wording in both locales and the PR title. Verify affected backend and frontend tests and obtain an independent delta review before pushing.

- Approved follow-up verification: platform-access backend tests 65 passed, 12 skipped; frontend access administration 125 tests passed across 5 files. Active-filter tests exercise both removal origins and both modes, preserved filtering, admission after import, denied ungranted identities and activation during off-lock preparation. First-import refusal and stale policy/replay checks remain covered. TypeScript and scoped raw control-plane types passed; migration-note validation and strict OpenSpec validation passed.
- Independent delta review covered committed HEAD `ed378a9e49b9a6d9cb23cceeeb8adf0678980cbc` plus the working-tree change and affected consumers. One stale contract summary was corrected and independently rechecked; no remaining findings in that scope. The earlier full branch review remains recorded above. The current target `origin/swift` is `4ed180acec2edcb97f8df3d9ae82f29e57498a19`; its subsequent changes only affect migration-guide rendering and do not overlap this behavior. Browser validation remains excluded and task 3.2 stays pending.
- UI wording uses "Import completed" / "Import terminé" and origin "Import". Help says the import can be run again at any time without discussing filtering state. PR 3141 was renamed to "feat(#3140): refresh the platform access whitelist" and issue 3140 was reconciled with the approved behavior.

- Follow-up root quality passed on staged source tree `34f19eb61c7227eb6f892b36e594f6b7eb8bf7a1`: `UV_NO_SYNC=1 make code-quality` from the clean tracked snapshot, reusing installed Python dependencies and excluding the already-documented ignored local scripts. All modules passed, including frontend TypeScript, Prettier and ESLint. Subsequent edits only record this evidence.
