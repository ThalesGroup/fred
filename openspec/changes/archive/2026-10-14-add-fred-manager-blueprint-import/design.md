## Context

Baseline: `0d18fbaff`. The Rust importer already provisions identities and roles
with preflight, platform/root checks and additive reconciliation. Its space model
supports projects; its importer currently accepts one organization and teams.

The control-plane `build-demo-bundle` target packages checked-in fixtures using
`zip -q -X`. Fred-manager keeps the Make target and file-variable convention;
Python standard-library packaging quotes no shell paths and replaces the output
atomically without retaining stale archive entries.
The user's latest instruction explicitly removes legacy input compatibility.

## Goals / Non-Goals

Deliver one generated demo ZIP that the Rust HTTP and CLI entry points can import.
Reuse the existing mutation services and correct their shared role-write protocol
before adding archive parsing, explicit hierarchy, project reconciliation and the
HTTP adapter. The developer approved that scope extension after the task 2.2
reproduction. See the proposal for exclusions.

## Authorization storage decision

Two real-OpenFGA fault tests reproduced the baseline unknown-completion gap: a delayed
child grant becomes effective after parent revocation (I4), and a delayed platform
grant becomes effective after its actor loses platform-admin authority (I5).
The proxy explicitly models an accepted request surviving caller cancellation;
this is a tested failure mode, not a claim about every OpenFGA timeout.

The approved correction covers shared role mutations, bootstrap and provisioning,
including timeout, cancellation and process restart. Every effective role change
must have one publication point ordered with caller/parent revocation. A retry
must reauthorize against current state. Existing role meanings, direct/effective
role distinctions, space IDs, identity profiles and bootstrap state are preserved.

The developer confirms that direct roles remain in OpenFGA and requires precise
request-type and complexity analysis as the implementation evolves. D1's role
ownership is retained. SQL-authoritative grants with contextual-only evaluation
are not selected. Maintaining a second authoritative grant store or a duplicate
permission evaluator in Rust is outside this change.

### Guarded atomic Write

The selected correction uses OpenFGA's transactional Write API itself as an upstream
fence. A dedicated guard object holds one current random revision per organization
or platform scope. Capture every required revision before any authority or role
state checks. In the same Write as the role changes, delete each captured revision
with `on_missing: error` and add a fresh revision. Only one competing mutation can
consume a revision. An old delayed mutation either wins first or fails as a whole
after a newer operation consumes its revision; it cannot apply a stale role delta.
An unacknowledged write can still commit if its revisions remain current. This is
ordered mutation, not cancellation rollback, consistent with the import's existing
explicit no-rollback contract. The earlier draft's absolute ban on an unpublished
grant becoming effective did not express that contract and is corrected in the
acceptance scenarios; timeout is never evidence of absence of effects.

Keep SQL platform/organization locks and their ordering. Delegated operations
consume platform and organization guards together. An unsuccessful attempt returns
an explicit error; any replay starts with fresh authorization and state checks.
Never replace a guard on an already computed delta. No-op successful revocations
also consume guards. Optional missing role deletions are omitted after a guarded
state read; strict guard deletion is never weakened to `ignore`.

Guard initialization requires an immutable sentinel and the initial random version
in one strict Write, preventing a delayed initializer from adding a second version.
Missing/multiple versions in an initialized scope are errors, not instructions to
reinitialize. This protocol retains stable role subjects and objects after cutover
and needs no per-mutation full-role copies, retained generations or cleanup worker.

The native atomicity is documented by the
[OpenFGA SDK Write contract](https://github.com/openfga/python-sdk/blob/main/docs/OpenFgaApi.md#write).
Independent source review also checks the v1.15.1 PostgreSQL writer and strict-delete
handling. The integration protocol experiment exercises an accepted delayed Write
after timeout and competing consumers of one revision. Application regressions separately exercise the shared services, multi-scope writes
and local SQL fences.

With `k` guarded scopes and `n` actual role tuple changes, the Write has
`n + 2k` operations: one old-revision delete and one fresh-revision insert per scope.
Capturing guards requires `k` exact-object/relation Reads, each expecting one tuple.
With a total limit of 100 operations, batches contain at most `100 - 2k` role changes
(98 for one scope, 96 for two). Record actual wire counts in regression tests;
separate these fixed protocol costs from existing paginated invariant checks.
This formula excludes initialization, migration, failed attempts and retries.

For comparison, a complete per-object snapshot with `R` existing and `R'` resulting
grants needs all `P(R)` Read pages and `ceil(R'/100)` Writes instead of one delta
Write, plus active-pointer handling and cleanup. Repeating a complete platform
copy for each imported grant can produce quadratic tuple traffic. That cost makes
full snapshots a fallback rather than the default implementation choice.

Cutover stops old writers and migrates all existing supported
direct grants before enabling the new path. Preserve bootstrap claimant/completion
and all space IDs. Validate parent and administrator constraints; reject invalid
state with a repairable diagnosis rather than silently dropping roles. A failed
cutover is replayable and cannot expose a partial migration. New initialization
must never fall back to old mutable authorization objects. CLI import retains
read-only schema/model/authorization initialization checks. Add a migration; do
not edit an applied migration or silently reset an existing store.

Legacy unguarded requests bypass any newly introduced guard. A new SQL singleton
binds the configured logical name and source store provenance to the active store
and model IDs. Each cutover attempt prepares a fresh store, validates the legacy
model/tuple shapes and SQL hierarchy, copies roles, checks parent access with
OpenFGA and initializes guards before publishing the binding. An existing binding
always wins over source-name discovery; ambiguous unbound source names are refused.
CLI import only loads the binding and verifies its pinned model.

`migrate-authorization` is an explicit offline operator command for existing state.
The operator stops legacy writers and settles pending requests before source
capture; software does not detect quiescence. The contract preserves the validated
captured state, not unknown legacy request outcomes. Normal `serve` initializes
only empty SQL/bootstrap/source state. Failed destinations remain unpublished and
are never reused; replay after uncertain SQL publication reads the binding first.

Required regressions cover the two reproduced interleavings, cancellation and
restart with writes in flight, failed/ambiguous acknowledgments, replay after caller
revocation, complete role-matrix preservation, and migration with a late legacy
write. Guarded Write tests additionally cover both winning orders, complete rollback
on a missing revision, no-op revocation, multi-scope atomicity, initialization races
and guarded batch sizing. SQL-only mutations need guard-only compare-and-swap after
their checks and before writing, while holding their SQL lock through commit:
otherwise an older delayed revoke can invalidate their earlier check.

### Query cost acceptance

The implemented baseline lives in `docs/architecture/09-quality.md`, not a second
status or benchmark document. Each changed flow records operation types, exact
filters, request count, sequential/concurrent dependencies, pagination, tuple
volume and lock hold scope. Cardinalities distinguish users, memberships, spaces
and documents. Request counts are tested on the generated fixture and on inputs
crossing relevant page/batch boundaries. Measured latency, concurrency and memory
require named fixture sizes, backend/configuration and environment; correctness
or fixed RPC counts alone do not establish scalability. No generic telemetry or
load-testing framework is added as part of this import step.

I5 orders role publication and local SQL commits, not HTTP response completion.
Content mutations capture and consume the organization guard under the SQL lock,
using its held connection through commit. Keycloak identity creation and Temporal
submission are authorized at dispatch under the relevant lock and guard fence;
their remote completion can follow revocation/cancellation. This is the existing
no-distributed-rollback boundary, not a claim that role fencing cancels external
work. No worker authorization/recovery protocol is added in this step.

## Decisions

### Five files, one supported version

The ZIP contains exactly these root files:

```text
manifest.json
users.json
organizations.json
teams.json
projects.json
```

The manifest is `{"format_version":2,"users_schema_version":2,"source_platform":"swift"}`.
The data files are arrays. Version 2 distinguishes this format from the Python
snapshot; no conversion is attempted. Old JSON and version-1 ZIP input return
`not_yet_supported` before writes. Other unknown versions/sections do likewise;
malformed current-format input returns a validation error.

Users contain `username`, optional `email`, `first_name`, `last_name`, `password`
and `platform_roles` (default empty). Preserve existing identity creation and
platform-role alias meanings. No legacy `teams`/`team_roles` fields are accepted.
Each space contains `ref`, `name` and `roles` mapping usernames to role arrays.
Teams additionally contain `organization` (organization ref); projects contain
`team` (team ref). References are unique across the bundle; every parent and
role target is declared. Names can repeat under different parents.

Example space entries, one per corresponding file:

```text
organization: {"ref":"tsn","name":"TSN","roles":{"alice":["admin","member"]}}
team:         {"ref":"bid","name":"BID","organization":"tsn","roles":{"alice":["admin","member"]}}
project:      {"ref":"p1","name":"P1","team":"bid","roles":{"alice":["admin"]}}
```

All four space roles are supported and cumulative. Store exactly the declared
roles: no implicit content for an administrator. A child grant requires declared
or existing parent content access; preflight and locked mutation both check it.
Every new space needs a declared admin. Existing undeclared grants remain intact.
The demo writes organization membership explicitly, including for team-role
holders, preserving the approved demo behavior without implicit format rules.

Resolve spaces by root/parent and name, reusing current SQL uniqueness and replay
semantics. References are bundle-local, not new persisted identities. Reject
personal-space/kind collisions and validate the entire bundle before writes.
Use the existing platform-first locking order and acquire organization locks in
stable UUID order. Preserve caller checks after lock waits and before mutations.

### Minimal archive and HTTP boundary

Read ZIP entries without filesystem extraction. Reject duplicate/path-bearing,
symlink/encrypted or corrupt entries and duplicate JSON keys. Support ordinary
stored/deflated ZIP entries produced by the Make command. Enforce 50 MiB archive
size (the control-plane bound) and 100 MiB expanded data, using actual bytes read.
Run decompression outside the async executor; keep the parsing code free of I/O
side effects. Require the five exact files and reject unknown fields/roles.

HTTP accepts one multipart `file`. Authenticate and require current platform admin
before reading it; root remains required for platform-admin grants. Use the
manager's existing service account for Keycloak, not as operator authority.
Return HTTP 200 with the existing reconciliation counts only after completion.
Use Fred's `detail` envelope for safe errors: unsupported input is 422 with
`not_yet_supported`, invalid input 400/422, input size 413, unauthorized caller
401/403, state conflict 409, unavailable dependency 503 and internal failure 500.
Preserve safe phase/count information on partial failure. Neither adapter echoes
passwords, tokens, input bodies or upstream responses.

Do not add a process-wide admission slot, execution deadline, stored bearer,
detached background job or recovery framework. Preserve the existing operational
error/replay behavior without claiming distributed atomicity. HTTP disconnects
and uncertain remote writes must not be presented as a rollback or success.

### Generated fixture is the acceptance input

Add the same Make target and variables as control-plane, with quoted paths and
an exact five-file allowlist. Adapt its curated demo identities/roles to explicit
organizations/teams; include all platform roles in the Rust fixture. Keep projects
empty in the first demo and cover nonempty projects with an automated variant.
Tests invoke the real Make target and import its output, not a separate hand-built
archive that could diverge. Keep generated ZIPs under ignored `target/`.

## Risks / Trade-offs

- Old inputs deliberately stop working: explicit `not_yet_supported` tests and
  updated README replace any compatibility implementation.
- The two reproduced authorization races require the storage decision above.
  A longer timeout, cancellation shielding, read-back, retry or compensating
  deletion cannot prove that an earlier remote write will never arrive later.
  A durable uncertainty barrier alone can only remain blocked indefinitely or
  reopen without that proof; it is not a complete recovery solution.
- The generated fixture and backend tests establish this step only. The following
  generated-client/browser step remains necessary for product acceptance.
