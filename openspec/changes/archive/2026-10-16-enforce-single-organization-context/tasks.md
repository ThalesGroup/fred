## Implementation

- [x] 1. Enforce unique attachment for operator creation, grants and import, preserving guarded writes and revocation repair.
- [x] 2. Resolve unique business context on the server and cover every business reader/mutator without changing platform governance.
- [x] 3. Default existing Home to the organization and keep its URL free of organization selection; regenerate affected contracts.
- [x] 4. Add concurrency, import, ambiguity/repair, foreign-object, role semantics, pagination and request-budget regressions; complete required manager and frontend verification.
- [x] 5. Independently review the implementation and correct findings with regression coverage and rereview.
- [x] 6. Update arc42 with implemented concepts, decisions, budgets and migration; validate docs/specs, sync/archive and commit locally without pushing.

## Review evidence

Design review at base 37af622d05b8f7ec340008725dd87cd0f362a666, independent agent
review_org_design, read-only: full placement needed for orphan project roles; target
uniqueness must not block revocation repair; direct authorization probes must enforce
context; document global serialization and legacy-data recovery. No implementation
readiness claimed by that review.

Implementation review against base 37af622d05b8f7ec340008725dd87cd0f362a666 by
review_org_design covered manager services/API/import, UI selection, generated
contract consumers and regression tests. Findings: missing 404 declarations and
present-empty space selection. Both corrected with HTTP/UI regressions and
rereviewed. Added post-preflight import-versus-grant coverage. Final documentation
rereview cleared stale wording, authority scope and sequence ordering. No findings
remain. Reviewer did not execute tests or measure throughput.

Full static branch audit by branch_audit against swift merge-base
e44837560a2b45df2e23802cd8c067097d5cf00d, HEAD 37af622d plus this working tree:
207 committed-diff files grouped by responsibility, deep review of authority,
provisioning, mounted frontend consumers, publication, content and deployment/reset
boundaries. No confirmed actionable finding. Archives/lockfiles inspected by
responsibility; historical upstream merges not reaudited in full. No live or
performance validation claimed by the reviewers.

## Verification

- make -C apps/control-plane test: passed (offline Rust and OpenAPI tests).
- make -C apps/control-plane test-integration: passed, 65 integration tests on
  disposable PostgreSQL/OpenFGA/Keycloak and the existing Temporal fixture.
- make -C apps/control-plane code-quality: passed (clippy, rustfmt, model parity).
- make -C apps/control-plane test-browser: passed, one real OIDC browser journey
  plus 64 integration tests before the last post-preflight race regression was added.
  The subsequent 65-test integration run includes that regression. Browser output
  screenshots remain under ignored target paths; no manual validation is claimed.
- make -C apps/frontend update-control-plane-api: passed; response-error additions
  change generated OpenAPI without changing successful RTK DTOs.
- Focused HomePage and manager-slice Vitest: 15 passed; frontend typecheck passed.
- Pagination fixture: 5 root roles, page size 2, context = 3 Reads; first member
  grant = 6 Reads, 1 Check, 1 Write, 5 tuple operations. Concurrency 1.
- Import fixture: 105 known users, 317 role tuples, one org and team: 114 Checks,
  422 Reads, 111 Writes, 550 tuple operations; maximum 100 operations/Write.
- Demo fixture: 15 users, 12 space-assigned, 2 existing IAM identities on a fresh
  Fred instance: 28 Checks, 44 Reads, 24 Writes, 90 tuple operations. One import.
- Direct competing attachment and delayed-write tests use 2 organizations;
  competing request concurrency 2. Post-preflight import/grant interleaving is
  controlled by the existing IAM gate and PostgreSQL advisory-lock waiter.
  These are wire budgets and correctness checks, not performance claims.

- Root make code-quality: passed across all configured modules. First run caught
  formatting in the changed Home test; Prettier corrected it and the full root
  gate passed on rerun. Existing baseline security reports are unchanged.
- make -C docs/architecture check: passed after final review corrections; generated
  invariant mappings refreshed and all Mermaid diagrams render.
- OpenSpec change and synchronized capability validate strictly. Migration note
  check-pr --base HEAD --worktree passed. git diff --check passed.
- Final local commit includes this lot and its documentation only; the pre-existing
  untracked personal-navigation proposal remains a separate pending lot. No push.
