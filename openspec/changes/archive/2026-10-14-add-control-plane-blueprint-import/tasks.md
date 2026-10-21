## 1. One generated ZIP format

- [x] 1.1 Add the five checked-in demo JSON files and control-plane-compatible `build-demo-bundle` target/variables; verify its output paths and exact archive entries, including overridden paths with spaces.
- [x] 1.2 Implement the bounded current-version ZIP parser and remove old JSON acceptance; verify `not_yet_supported` for old inputs and preflight rejection of malformed/unknown/duplicate/path/corrupt/oversized input with offline tests.

## 2. Shared provisioning and HTTP

- [x] 2.1 Extend the existing provisioning service to explicit organizations/teams/projects and direct grants without a legacy adapter; verify all roles, parent requirements, same-name isolation, whole-bundle preflight and additive replay against real PostgreSQL/OpenFGA.
- [x] 2.2 Correct shared role mutation publication before exposing the route, keeping roles in OpenFGA. Use native guarded Writes and validate their cutover, initialization, no-op, multi-scope and batch semantics. Preserve existing grants and pass delayed-parent/actor-revocation, cancellation/restart and replay regressions. Resolve the I5 contract boundary explicitly; do not add an unapproved recovery framework.
- [x] 2.3 Add multipart HTTP import and route CLI ZIP input to the same service, preserving authorization and safe errors; verify HTTP status, non-admin/root refusals, dependency failures and absence of secret leakage through router tests.
- [x] 2.4 Invoke the real `make build-demo-bundle` output in the real-Keycloak HTTP integration test; verify identity preservation, roles, caller-visible spaces and replay; exercise a nonempty-project variant automatically with invariant markers.

## 3. Review and completion

- [x] 3.1 Obtain independent implementation review and re-review of corrected findings; record base/head, coverage and dispositions here, with a regression for each confirmed defect.
- [x] 3.2 After review, update README and applicable arc42 chapters to implemented present-tense behavior, including precise OpenFGA query filters/counts/cardinality and lock costs; verify changed request budgets, regenerate derived blocks and pass `make -C docs/architecture check`.
- [x] 3.3 Pass manager `make test`, `make test-integration`, `make code-quality` and OpenSpec validation; record evidence, reconcile/sync/archive artifacts and create clean local implementation commits per reviewed step without pushing. Do not claim the subsequent UI journey is validated.

## Planning review

Independent read-only review at `0d18fbaff` covered the draft contract and current
Rust/Python import mechanisms. The user then removed legacy compatibility and
future machinery. The added sole-upload-slot timeout concern is removed with that
slot/deadline design. The existing uncertain-FGA-write race remains an explicit
reproduction task, not a claim of an implemented or verified fix.

The same independent reviewer re-read all four narrowed artifacts: no further
actionable contract contradiction was found. `openspec validate
add-control-plane-blueprint-import --strict` passes. No implementation or runtime
verification was claimed at that planning review.

## Task 2.2 reproduction and independent review

Base/head: `0d18fbaffb25eed7dc6da831f9daa36448cb6f48`, with uncommitted
changes to `tests/integration.rs` and `tests/support/fga_proxy.rs`. The fault proxy
holds an accepted child grant before forwarding and keeps that delivery alive
after the caller times out. Parent revocation succeeds after the SQL transaction
ends. Releasing delivery then produces a real OpenFGA HTTP 200, effective child
read access, and no parent read access. This reproduces an I4 violation under the
injected delivery-survives-cancellation fault; it does not establish a production
incident or universal OpenFGA cancellation behavior. I5 is not exercised.

Verification: `make test CARGO_TEST_OPTS=--lib` passes all 32 unit tests.
`make test-integration
CARGO_TEST_OPTS=a_timed_out_child_grant_cannot_arrive_after_parent_revocation`
fails at the final I4 assertion against disposable PostgreSQL and OpenFGA.
The failing test remains a reproducer, not a passing invariant proof.

An independent read-only reviewer examined the two-file diff, mutation service,
authorization model and I4/I5 statements at the above base/head, relying on the
reported execution result without rerunning it. The reviewer confirmed the
counterexample and requested the comment say timeout does not *guarantee*
cancellation; that correction is applied. This is a focused review, not a full
branch audit. Full integration, quality, architecture checks and final review
remain outstanding.

The review found no existing lock/retry/read-back pattern that guarantees safety
when an earlier remote write can still arrive after those operations. A fix
requires an explicit decision about shared mutation ordering or authoritative
authorization state and its failure behavior. Task 2.2 remains open pending that
scope decision and correction. No recovery framework, HTTP route or ZIP feature
is implemented, and no commit or push is made at this gate.

The developer approved extending this step to shared authorization writes. A second
test, `a_timed_out_platform_grant_cannot_arrive_after_actor_revocation`, gives a
delegate platform-admin authority and delays their prompt-editor grant. After the
client timeout, the root revokes that delegate. Releasing delivery receives a real
OpenFGA 200 and leaves the target's prompt-editor role effective, violating I5.
`make test-integration CARGO_TEST_OPTS=a_timed_out_` runs both reproducers: both
fail at their final invariant assertion, with 34 tests filtered out. No fix is
claimed. This focused run does not replace the required full verification.

Independent design review at the same base/head covers the authorization client,
space/platform/bootstrap/provisioning services, API consumers, initialization and
architecture. It confirms immutable snapshots with SQL publication or SQL grants
with contextual evaluation as sound alternatives, subject to their stated migration
and consumer requirements. It rejects a retry/read-back/uncertainty-barrier-only fix.
The subsequent developer decision retains D1's OpenFGA role storage and requires
precise query-cost analysis. SQL-authoritative grants are not selected. Production
code remains unchanged while the guarded-Write candidate is evaluated.

The independent reviewer also checked the new I5 reproducer and confirmed its
causal ordering. Its sole hardening finding was to bound both revocation waits so
a permanent-blocking implementation cannot hang the suite. Both waits now have
three-second deadlines; bounded re-review confirms the correction without new
findings. Re-running the two tests still fails only at their final I4/I5 assertions
(0 passed, 2 failed, 34 filtered), not at the new deadlines. `cargo fmt --all`,
`git diff --check` and strict OpenSpec validation pass. Full readiness checks and
the arc42 implementation documentation pass await the selected correction.

## OpenFGA ownership, costs and native guard experiment

The developer confirms OpenFGA ownership of direct roles and requires precise
query-type and complexity analysis throughout reconstruction. The branch workflow
records that rule. The arc42 quality chapter inventories current source-derived
RPC counts, filters, pagination, tuple cardinalities, application memory/CPU and
lock scope, without claiming measured scalability. Independent source review at
the same base/head finds no count error; its three wording findings are corrected
(source-derived counts, organization-scoped mutations, HTTP versus CLI pools).

`openfga_strict_guard_delete_rejects_an_entire_delayed_write` passes against
OpenFGA 1.15.1 with both its memory and PostgreSQL datastores in disposable
environments. It proves the native strict-delete/Write primitive's atomic rejection
after a consumed guard, and checks competing requests for one revision. It does
not force overlapping datastore transactions or exercise application guard use,
restart, initialization or cutover. Independent read-only review confirms the
causal assertions and requests an explicit expected conflict status for the loser;
that assertion is added and the focused test passes again. Re-review finds no
remaining issue in this bounded surface, not in the whole application.

The same review identifies an inconsistent draft promise of cancellation rollback.
The spec now describes both winning orders and restart with an intervening
revocation, consistent with the existing import's no-rollback contract. A timeout
does not prove no effects; a consumed guard prevents stale effects. Re-review
confirms this distinction. Production code is unchanged; cutover representation,
the broader I5 boundary and task 2.2 remain unresolved.

Verification: `make test` passes 32 unit tests; `make code-quality` passes.
`make -C docs/architecture check`, strict OpenSpec validation and `git diff --check`
pass. The generated invariant index includes the two red application reproducers;
the structural documentation check does not establish their invariants.
The full `make test-integration` run finishes with 35 passed and 2 failed: only the
delayed child/actor grant reproducers fail, at their final invariant assertions.
No implementation commit or push is made while these regressions remain red.


## Task 2.2 implementation close-out

The selected implementation uses native atomic guarded Writes. Roles and permission
checks remain in OpenFGA; SQL publishes only the active store/model binding.
Offline migration preserves validated legacy grants and rejects incompatible
models or hierarchy. I5 orders role publication and SQL commits; Keycloak/Temporal
operations are authorized at dispatch, without promising remote rollback.

Independent read-only review covers the correction worktree against
`0d18fbaffb25eed7dc6da831f9daa36448cb6f48`: FGA protocol, initialization and
cutover, shared mutations, SQL/API consumers, importer, tests and arc42.
Confirmed findings are fixed and re-reviewed with regressions: held-connection
pool deadlock; missing legacy-model validation; concurrent discovery of distinct
source stores; invalid SQL hierarchy/path; migration failures bypassing structured
fatal logging. Follow-up fixture weaknesses (masked hierarchy failures and
same-store concurrency), source-read query cost and migration indexing are also
corrected. Final independent review reports no remaining actionable finding in
this correction, including the subsequent cancellation/client-restart test.
The reviewer inspected code without independently executing tests. This is not
full-branch/PR readiness review; live Temporal delivery and OS-process termination
are excluded. Cancellation coverage aborts the task and reconstructs clients.

Verification: `make test` passes 32 unit tests; `make code-quality` passes;
`make test-integration` passes 45 integration tests with OpenFGA 1.15.1 memory
storage. The same 45 integration tests pass with its PostgreSQL datastore.
Disposable real Keycloak is included. Both former red delayed-write reproducers
now pass, as do cutover replay, ambiguous writes, no-op/multiple-scope fencing,
SQL publication and client-restart cancellation regressions. The large import
asserts 113 Checks, 107 Reads and 111 Writes for 105 identities, including 548
tuple operations and at most 100 operations per Write.

The dedicated post-review documentation pass records implemented semantics and
request costs in arc42. Generated blocks and `make -C docs/architecture check`
pass. Strict OpenSpec validation and `git diff --check` pass. ZIP/HTTP tasks remain
open and the active change is not archived or presented as complete.


## ZIP import close-out

Reviewed base/head: `af0b412b4` plus the ZIP worktree. A separate read-only reviewer
covers archive validation, CLI/HTTP consumers, explicit hierarchy, authorization
and replay, Make packaging, fixtures, tests, README, arc42 and the synced spec.
The sole implementation finding is fixed: child names are resolved after all
organization locks, so an insertion committed during lock wait cannot escape
preflight. `blueprint_preflight_reads_child_names_after_organization_lock` forces
that interleaving and verifies a preflight conflict with zero identity creation.
Independent re-review confirms the correction. Documentation findings correct the
exact authority relation (`admin`), packaging implementation, early HTTP error
counts and unsupported-compression classification; final review finds no remaining
production defect. Tests are inspected by the reviewer, executed by the author.
This is a bounded backend step review, not full-branch/PR or UI readiness; prior
branch changes, generated frontend integration and live Temporal are excluded.

Verification: manager `make test` passes 34 unit tests; `make test-integration`
passes 47 tests against disposable PostgreSQL/OpenFGA, including real Keycloak;
`make code-quality` passes. The real Make artifact is imported through HTTP and
replayed, with existing identity profile/credential preservation, visible spaces,
all platform roles and a project variant. The artifact verifies 29 Checks,
18 Reads, 25 Writes and 89 tuple operations. The project variant verifies 15
Checks, 4 Reads and 4 Writes, including two existing-parent fallback pairs.
The 105-user batch fixture verifies 114/107/111 requests and 548 tuple operations.
Malformed/duplicate multipart input, 401/403/409/413/422/503 failures and an injected
SQL 500 preserve safe errors; invalid preflight has no valid-prefix provisioning.
ZIP unit tests cover duplicate JSON/ZIP names, local-header mismatches, paths,
encryption, symlinks, CRC/size corruption, limits, versions and Make path overrides.

The dedicated post-review arc42 pass and generated route/invariant blocks pass
`make -C docs/architecture check`. Strict change validation, all 28 main specs
and `git diff --check` pass. The current capability spec replaces the legacy input
contract and includes guard ordering, query costs, ZIP generation, HTTP and project
reconciliation. The reviewed blocks are local commits only; no push, browser
acceptance or generated frontend client is claimed.
