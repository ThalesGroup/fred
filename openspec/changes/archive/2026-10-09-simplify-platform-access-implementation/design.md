## Context

See `proposal.md` for scope. The reference is `e239bd1e3f141e029ce3ee969930552a20d8b3a9`, with merge base `9a57933e24325ae75ffb52e291aed44edf69c46d` against `origin/swift`. Initial worktree has only untracked local screenshots. The complete PR has 223 changed files, 14,584 additions and 444 deletions. File-category totals are:

| Category | Added | Removed |
| --- | ---: | ---: |
| Code/configuration, including styles and translations | 6,414 | 388 |
| Test files | 4,489 | 34 |
| Generated client and lockfiles | 512 | 1 |
| Current documentation/specifications | 894 | 21 |
| Archived OpenSpec changes | 2,275 | 0 |

There are also 28 tracked historical screenshots (1,288,525 bytes). Do not count binary size or test deletion as application-code savings. The read-only frontend and backend reviews found modest concrete code reductions; most authorization code implements separate required guarantees.

## Goals / Non-Goals

- Prefer deletion and existing conventions to new abstractions. Retain the present UI, API contracts and all current admission semantics.
- Restrict implementation to this feature and directly affected consumers. Keep unrelated local work and historical OpenSpec archives intact.
- Preserve all meaningful regression cases. Parameterize tests only where identical setup can be reduced without hiding distinct assertions.
- No new caching, broader whitelist behavior, authentication shortcut, UI redesign, dependency or global overlay framework. No remote writes or pushes.

## Decisions

1. **Start with proven duplication.** Fold the 25 platform-access hook aliases into the existing destructuring export. Reuse the local copy-action renderer. Narrow claim-picker output to its actual path value, and keep only the selected condition index because its claim already belongs to the draft. Remove unused CSS and confirmed unused translation keys, checking dynamically constructed keys manually.
2. **Remove dead persistence, retain evidence.** `admission_claim_path` has no readers: remove its hash computation/writes and model/pending-migration declaration. Preserve `admission_attribute`, issued/expiry times and conflict state. Existing local databases may keep the unused nullable column; verify both fresh migration and previously migrated database compatibility without resetting user data.
3. **Consolidate small backend plumbing.** Reuse the canonical condition-reason type; share the count/list search predicate; remove redundant consecutive state reads; flatten T0 conditions already guaranteed by the locked early return. Regenerate OpenAPI and prove the public contract unchanged. A shared observed-evaluation helper is optional only if it preserves unknown versus mismatch and reduces code overall.
4. **Keep important distinctions explicit.** Retain the observation fast path plus locked reprojection, expiry recheck under mutation lock, monotonic/conflicted evidence, full regex evaluation budget, actor lockout, source precedence, and OpenFGA response validation. Do not merge single/bulk grant paths or add membership caching simply for fewer lines. Batch-read performance changes with new snapshot semantics are deferred.
5. **Reduce review noise independently.** The translations contain 122 English and 150 French existing-key edits outside this feature, largely punctuation replacements, plus key reordering. Revert only verified unrelated churn to the base text/order, preserving all feature keys and required integration strings. Report this as reduced diff churn, not reduced runtime code.
6. **Use the actual services for browser evidence.** The user identified provisioning ZIPs in Control Plane and authorized new dedicated test identities if necessary. The demo bundle contains credentials and two accounts with platform roles; validate their current access without printing credentials. Preserve existing user/team data. Use designated test teams, capture the initial configuration, and restore reversible changes. Exercise irreversible initial import on an isolated test database, never reset the developer's completed import.

## Verification and Acceptance

Before edits, run targeted existing suites and capture the key live journeys as a reference. Reproduce any baseline failure before assigning it to the refactor. After implementation, run root `make test` and `make code-quality`, plus PostgreSQL integration tests with `FRED_PLATFORM_ACCESS_TEST_DATABASE_URL` supplied securely. The existing fixture creates and drops a uniquely named schema; default SQLite tests skip nine concurrency cases and do not replace this run. If the root command stops at a failure, record it and run remaining suites so exclusions are explicit.

| Invariant | Evidence required |
| --- | --- |
| Allow/block, AND/OR, missing versus uninspected claims, negative arrays, regex/timeouts | Core/backend tests; live draft test/save and user admission/refusal |
| Save conflicts, stale preview, selected field/value flow and unsaved drafts across tabs | Existing component tests; Playwright picker/cancel/manual value, explicit save, reload/conflict |
| Whitelist search begins on typing; more than 100 selections remain atomic | Component/API tests; browser search, clear, paging, user and team exceptions |
| Initial import fixed population; activation warning, dry run and refresh | Backend isolated-state tests; browser pre/post import on isolated state, confirm/cancel and fresh saved revision |
| Actor cannot remove last access source; suspension and legal checks remain stronger | Backend/PostgreSQL tests; dedicated-account browser refusal/CGU journeys |
| Direct/cached/delegated requests recheck live authority | Core/integration tests across affected readers; fail-closed unavailable-authority cases |
| Link creation, expiry, revocation, suspension/resumption and reusable original URL | Real admin/recipient browser contexts; time-based expiry and API/member checks |
| Cleanup affects only chosen team's obsolete history | PostgreSQL/API tests; browser confirmation/cancel and confirmed cleanup on expendable links in two test teams |
| Copy uses shared receipt without layout shift; manual fallback; tokens not retained | Component tests, browser clipboard success/failure and dialog geometry; inspect mutation reset paths |
| Fixed table/JSON headers, responsive layout, nested modal context and focus | Playwright desktop/narrow captures, row scroll, Tab/Escape, focus restoration; shared component and packed-consumer tests |
| Generated contract, single migration and adjacent raw-download/PDF/SSE consumers | OpenAPI comparison, fresh migration, full suites and branch review |

Retain screenshots and a local scenario-to-result recap under `screenshots/platform-access-simplification/`, without credentials, reusable URLs or token values. Real end-to-end captures must not substitute mocked API responses. Compare code against both the reference commit and actual PR base. Obtain independent read-only review of the final local delta and replay prior bot findings without posting to GitHub. Record exact test counts, skips, failures, limitations, line deltas by category, and retained safeguards in the final local recap.

## Risks / Trade-offs

- A lower line count can hide a security regression. Require existing counterexample tests and independent review; abandon an extraction if it obscures decisions or increases code.
- Current infrastructure or test-account drift can prevent a live path. Resolve only within authorized local fixtures, and label an unverified path rather than fabricate evidence.
- Changing the pending migration does not remove a column from an already migrated database. Treat the harmless leftover as local compatibility, not a reason for destructive reset or a second PR migration.
- Root test failures may predate this pass. Compare on the reference tree and report them separately; do not silently broaden into unrelated fixes.

## Migration Plan

No deployed-state transition is introduced. Keep the PR's single migration. Use separate local commits for coherent backend and frontend reductions after checks, without rewriting the published baseline. Local commits can be reverted independently. Restore test configuration and remove only test-created resources; leave application changes and screenshots available for the user's inspection, with nothing pushed.
