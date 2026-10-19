## 1. Stable deployment contract

- [x] 1.1 Record the approved direction and clean factory baseline; preserve factory swift unchanged.
- [x] 1.2 Replace chart application names/configuration and schema; verify default and unchanged factory renders, migration commands, secrets, storage/queue continuity and shared rollouts.
- [x] 1.3 Publish/build Rust as control-plane-backend with matching API/worker references; verify focused build and CI selection tests.
- [x] 1.4 Implement the database-only Rust migration entry point; verify configuration-independent invocation and embedded migration execution without exposing secrets.
- [x] 1.5 Preserve generated UI paths through the existing gateway; verify both API prefixes and query/body forwarding without UI changes.
- [x] 1.6 Align reset classification with the Rust control-plane workloads and retain existing reset safeguards; run focused fixture tests only.

## 2. Verification and documentation

- [x] 2.1 Perform focused independent review, fix and re-review actionable findings; validate real factory Helmfile rendering and chart/schema/proxy checks. No full campaign or k3d execution.
- [x] 2.2 Update compact arc42 operations and migration guidance from implemented behavior, reconcile this change and validate artifacts; commit the reviewed lot.
- [ ] 2.3 Developer-run deployment and rerun: five ready application deployments, preserved folders/identities/roles, working UI and identical API/worker images. Record actual evidence before archive.

Approved revision: 2026-10-19. Fred baseline b98304de4, factory baseline 9d7d4d0. The previous factory-specific integration PR #56 is closed; commit 1ea70c8 is retained in the local recovery bundle. Earlier focused verification is recorded in Fred commit 061f42ce7. The developer reported successful deployed folder creation before this revision. All make k3d-* commands remain developer-owned; broad checks remain deferred.

Focused verification (2026-10-19): 4 real-chart rendering tests (including the unchanged sibling factory values), 2 build mapping tests, 23 reset fixture tests, 15 CI image selection tests and 9 Rust offline/CLI contract tests passed. The unmodified factory Helmfile rendered successfully. The migration command applied all 7 embedded migrations to disposable PostgreSQL 16 and replayed successfully with runtime configuration absent. A disposable real nginx verified both public prefixes preserve query, POST body and bearer; generated proxy smoke checks covered the cluster and host prefixes. No application image build or cluster mutation was performed. Arc42 generated-block checks, OpenSpec strict validation and diff whitespace checks passed; broad suites remain deferred as requested.

Independent read-only review: reviewer review_control_plane_contract inspected baseline b98304de4 through this working diff, covering deployment topology, migration independence, secrets, storage/task continuity, reset and routing. No actionable code defect remained; the stale frontend upstream documentation was corrected after the final pass. This is a focused deployment review, not full-branch readiness. Deployed upgrade/rerun acceptance remains task 2.3.

Developer deployment attempt (2026-10-19, 65900d9f7): initial lint failed because the factory's previous image cache still declared fred-manager/fred-manager-worker. Reproduced with the exact cached overlay; the earlier fresh render omitted it. Backed up the two generated manifests, reset image values to the factory's empty-cache state, then reran its exact lint and template successfully. Factory swift remains clean; no build, deployment or data reset was executed. The migration guide now documents this one-time cache invalidation. Task 2.3 remains pending the developer's retry.
