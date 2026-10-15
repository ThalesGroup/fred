## 1. Contract and dispatch

- [x] 1.1 Add the generic factory reset target and optional hook dispatch; command tests prove no build, no sync and no default deletion, including checkout paths with spaces.
- [x] 1.2 Implement the Fred preview and dedicated-cluster/storage checks; tests prove unsupported/shared setups fail before mutations and real-cluster preview performs only reads.

## 2. Coherent reset

- [x] 2.1 Implement stop/wait, bounded storage cleanup, installed migration replay and replica restoration; tests cover operation ordering, retained identities/infra, empty stores and original images.
- [x] 2.2 Implement local serialization and failure retry; regression tests cover cleanup, migration and readiness failures, saved replica counts and changed deployment identity refusal.

## 3. Verification and documentation

- [x] 3.1 Run focused factory/Fred tests, applicable quality checks and architecture check; distinguish simulated orchestration, disposable service evidence and live read-only preview from a live destructive reset.
- [x] 3.2 Obtain independent read-only review of both diffs, correct findings with regression coverage and review corrections.
- [x] 3.3 Update existing factory guides, Fred deployment/architecture operations and migration note; reconcile specifications and commit separately in each repository without pushing. Archive only when acceptance verification is complete.

Scope: the developer authorized the improvement and confirmed a dedicated Fred k3d with refusal of other applications. Execution on the populated developer cluster is not authorized by this implementation task.


Verification and review (2026-10-15):

- Factory command suite: 14 tests pass, including confirmation propagation, no build/sync, missing-hook refusal and shared target state across product checkouts. `make check-pure-infrastructure` and shell syntax checks pass. Companion commit: `fddfeef`, branch `chore/local-app-reset`, based on `2521459`; not pushed.
- Fred `make k3d-tests`: 22 pass, one opt-in storage test skipped in the offline suite. The 16 reset orchestration tests cover refusal of unmanaged producers, shared/custom storage, paginated FGA inventory, retained migration Pods, foreground retry Job deletion, incomplete multi-completion Jobs, missing database recovery, migration/readiness failures, saved replicas, changed images, concurrent invocation and an unwritable state directory.
- Opt-in storage test run separately: one real test passes against disposable pgvector/PostgreSQL 17, OpenFGA 1.11.0, OpenSearch 2.19.3 and SeaweedFS 4.29. Two cleanups erase Fred data and preserve Keycloak/evaluation database markers and an infrastructure index. No k3d data is used. Initial fixture failures (PostgreSQL user environment, FGA listen port) were corrected before the passing run.
- All three currently installed Python migration image/command pairs initialize a fresh disposable PostgreSQL database successfully; this separate check reads installed definitions but writes only to disposable Docker containers.
- Read-only factory preview succeeds against `k3d-fred`. Root `make code-quality`, targeted Python lint, manager `make test` (35 unit + 4 OpenAPI), `make test-integration` (48), manager quality, architecture check and migration check pass.
- Independent read-only review: Fred base `aaaab7efb`, factory base `2521459`, final staged reset scope and affected consumers/docs. Findings about unmanaged producers, retry Jobs, missing databases, target-scoped locking, dependent-Pod deletion and partially successful Jobs are fixed with regression coverage and re-reviewed. An author finding about state-write failure cleanup is also fixed and independently re-reviewed. Final reviewer reports no remaining blockers.
- Exclusions: this is not a historical branch audit. No full destructive reset of the user's k3d, Temporal schema/restart cycle or browser rebootstrap was performed. Tests distinguish real storage/migration behavior from simulated Kubernetes orchestration. The existing unrelated `deploy-fred-with-helmfile` change remains untouched.
