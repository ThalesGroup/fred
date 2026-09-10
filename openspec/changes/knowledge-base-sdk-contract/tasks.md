One working branch, one potential PR. The groups are ordered as a single
vertical slice: each is worth starting only because the previous one works.

The HTTP/WebDAV/Markdown synchronizer is **not** in this plan. It is the
immediate external consumer that will validate the published contract once
group 6 passes.

## 1. SDK author contract and manifest artifact

- [x] 1.1 Add the Knowledge Base declaration to `libs/fred-sdk` — identifier, version, display metadata and one list of instance configuration fields as `FieldSpec`; verify with tests that a well-formed declaration validates, a malformed identifier is rejected, and a duplicate field key is rejected naming the key
- [x] 1.2 Add the synchronization-handler decorator accepting exactly one handler per declaration; verify with tests that a declaration with no handler fails with a clear error and that a second handler is rejected
- [x] 1.3 Add the run context and the bounded sync result — five generic counters, bounded summary, bounded warnings and errors, optional JSON-safe metrics map; verify with tests that bounds truncate and that a metrics map round-trips unmodified
- [x] 1.4 Add the JSON-safe manifest artifact producer an operator installs into deployment configuration; verify with a round-trip test and a test that the artifact carries no configured value and no secret
- [x] 1.5 Add a test asserting the author-facing package's public exports and handler signature contain no workflow, activity, task-queue, retry, heartbeat or schedule type or term — public surface only, not module imports

## 2. Control Plane configured catalog

- [ ] 2.1 Add configured-definition parsing to the control-plane deployment configuration, carrying identity/version, display metadata, configuration fields, expected M2M client identity and internal execution routing; verify with tests for a valid definition and for each missing required part
- [ ] 2.2 Add startup validation refusing to serve an invalid configured definition; verify with a test that startup rejects it rather than exposing a half-valid catalog
- [ ] 2.3 Expose the configured catalog to Platform Admin and reuse the existing team enablement mechanism over it, storing no configuration on enablement; verify with tests that an unenabled definition cannot be instantiated, enabling permits it, disabling blocks new instances, and no surface reports a definition as online

## 3. Team instances and schedule lifecycle

- [ ] 3.1 Add the instance table and store, keyed so one team holds several instances of one definition, with its Alembic migration; verify with tests that two instances coexist independently and that an instance is bound to its creating team
- [ ] 3.2 Add instance configuration validation against the definition's declared fields with pass-through storage; verify with tests for an invalid value rejected naming the field, a missing required field rejected, and secret-declared values absent from display reads
- [ ] 3.3 Add the typed recurrence — daily or weekly, local time, IANA time zone, and a no-recurrence state; verify with tests for the weekly case across a daylight-saving transition, no-recurrence as valid, and rejection of cron-shaped input
- [ ] 3.4 Add per-instance Temporal Schedule lifecycle over the existing schedule primitive — create, update in place, suspend on disable, resume on re-enable, delete on instance delete, with the skip-while-active overlap default; verify with tests that one instance never has two schedules, that no schedule outlives its instance, and with a recurrence-to-schedule mapping test needing no scheduler connection
- [ ] 3.5 Add team isolation on instance read, update, delete and run listing; verify with tests that a non-member is refused and run listing returns only the caller's team's runs
- [ ] 3.6 Regenerate the frontend API client for the new control-plane controllers with the documented make target and commit the regenerated file alongside the backend change

## 4. SDK worker, generic workflow and Control Plane calls

- [ ] 4.1 Add the SDK worker bootstrap and its internally derived task-queue identity, started by the run entry point; verify with a test that the queue identity is derived rather than author-declared
- [ ] 4.2 Add the generic workflow and activity adapter with all I/O in the activity and heartbeat, cancellation and retry plumbing inside the adapter; verify with tests that the workflow performs no I/O and that a run identifier is derived at workflow start rather than read from a static schedule argument
- [ ] 4.3 Add the pod's confidential M2M client using the existing `M2MTokenProvider` client-credentials pattern; verify with a test that no user token is used or propagated on any outbound Fred call
- [ ] 4.4 Add the authenticated run-context endpoint returning one run's configuration, verifying the signature-derived client identity against the definition's configured client and scoping access to the active run, its instance and its team; verify with tests that another definition's client is refused and that a broad service role alone does not authorize
- [ ] 4.5 Add the run record, terminal states and the bounded result-reporting endpoint, contributing to the existing task state and event vocabulary rather than a parallel status surface; verify with tests for succeeded, failed and cancelled, and that oversized content is truncated

## 5. Minimum authorized Knowledge Flow document boundary

- [ ] 5.1 Determine whether today's Knowledge Flow push APIs already support scoped document read, list, upsert and delete restricted to one team and instance with exact-client and active-run validation; record the finding in design.md and, if they do not, scope the smallest extension as a task here — do not design or implement it in this group's investigation step
- [ ] 5.2 Implement that smallest boundary or adapter so a run's document operations are confined to its team and instance; verify with tests that an attempt to reach another instance's documents is refused and that no OpenSearch or object-storage credential is exposed through the SDK contract

## 6. One fixed-result end-to-end proof

- [ ] 6.1 Add an in-repo example declaration whose handler returns fixed counters and writes one document through the boundary from group 5; verify it validates and uses only existing `FieldType` values
- [ ] 6.2 Prove the slice: definition configured, validated at startup, enabled for a team, instance created and configured, schedule fires, handler invoked, document written within scope, structured result recorded and readable — asserting the run input carried identifiers only and no secret appears in durable run history
- [ ] 6.3 Prove the failure paths on the same example: handler raises is recorded failed, cancellation is terminal and distinguishable, a due run is skipped while one is active, and a run with no worker reaches a terminal failure without being reported at enablement time

## 7. Quality gate

- [ ] 7.1 Run `make code-quality` from the monorepo root and fix everything it reports
- [ ] 7.2 Run `make test` from the monorepo root and confirm the new tests pass with no regression elsewhere
- [ ] 7.3 Run `/code-review` on the diff before reporting done, per the repository's Step 5 rule
