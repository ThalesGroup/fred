## 1. Product and instance composition

- [x] 1.1 Confirm the proposed scope/acceptance and record Fred/factory baselines, isolating companion work from pre-existing staged changes; verify clean scope with Git diffs before edits.
- [x] 1.2 Integrate manager API/worker into Fred chart defaults and the schema generator; regenerate the schema and verify strict lint/render produces the five intended deployments, no legacy migration Jobs and correct probes/configuration/secret boundaries.
- [x] 1.3 Update the local build map and common CI image catalog for manager; verify focused image tests cover three local image references, identical API/worker references, content tagging and abort on build failure. Remove the duplicate standalone build/chart path.
- [x] 1.4 Align factory Fred values, identity provisioning and bootstrap guidance with the integrated chart while preserving its pinned published-release path; verify focused hook tests and effective Helmfile renders in checkout and published modes.

## 2. Transition and dependent consumers

- [x] 2.1 Implement the guarded standalone-release transition with protected recovery information and explicit context targeting; test fresh install, known legacy inventory, unexpected/persistent-resource refusal, failed build/render, failed sync and retry without resetting data.
- [x] 2.2 Make the existing frontend proxy start without agents/control-plane DNS and retain failing legacy routes; verify the focused nginx startup/proxy fixture with both services absent and inspect the diff for no UI changes.
- [x] 2.3 Reconcile affected reset/health/image consumers with the five-workload composition; run their relevant existing tests without performing any live reset.

## 3. Documentation and acceptance

- [x] 3.1 Update arc42 system overview/operations and manager references from implemented behavior, plus component/deployment guides and the migration note; verify generated architecture references and document links, with no architecture claims derived only from the plan.
- [x] 3.2 Complete the focused integration/review pass across both repositories, correct findings and re-review corrections; record exact tests and exclusions here. Validate OpenSpec; keep the deferred global campaign separate.
- [ ] 3.3 Developer-run acceptance (requested on 2026-10-19): validate the coordinated deployment and one rerun on the existing test cluster: five ready application deployments, preserved data/identities, matching API/worker images, frontend startup and paged manager folder response. Record who ran it and actual results; never wipe infrastructure.
- [x] 3.4 Prepare and commit the reviewable lot excluding unrelated factory changes; push only when explicitly requested. Specification synchronization and archive follow the developer-run acceptance in 3.3.

Planning evidence: the existing standalone release contains two ServiceAccounts, one empty-by-default env Secret, two ConfigMaps, one Service, two Deployments and one Ingress; no PVC appears in its current manifest. The runtime response schema observed on 2026-10-19 is still the old folder array while the deployed frontend expects a paged directory. This inventory is diagnostic evidence only; migration must perform its own fresh preflight.

Scope confirmed by the developer on 2026-10-19. Fred baseline: a17ba8ac0 on chore/rust-rebac. Factory companion worktree: /home/dimi/Fred/fred-deployment-factory-manager, codex/integrate-fred-manager, baseline 478d1ca (the touched deployment files match the original checkout). The original factory index is preserved.

Focused verification (2026-10-19): 8 manager OpenAPI/configuration tests, 25 build/reset tests (1 optional real-storage test skipped), 2 real-chart topology/rollout tests, 4 ingestion-worker chart scenarios, 14 CI image-selection tests, 21 factory hook/transition tests and 17 factory engine tests pass. Strict chart schema drift/values validation and checkout/pinned Helmfile renders pass. Frontend proxy smoke and an actual nginx startup with absent legacy DNS pass. Arc42 generated references/diagrams and migration declaration checks pass. No live data reset and no full repository/service quality campaign were run, per the requested iteration rhythm.

Independent read-only review: Fred a17ba8ac0 and factory 478d1ca plus this working delta. Coverage: chart/config schema, image build/publication, proxy startup, transition, reset consumers and updated docs. Fixed findings with regressions: shared-config worker rollout, manager reset OpenFGA typing, relative values paths, live lifecycle/credential continuity, foreground termination; restored explicit required Secret refs to match live manifests. Corrected overlay documentation and added manager schema CI coverage. Corrections re-reviewed with no remaining findings. This is a focused deployment review, not full branch/PR readiness.

The live preflight passes on the existing cluster and was stopped before uninstall. Read-only fingerprints cover 5 spaces, 0 folders/documents, 2 personal consents, 1 bootstrap record, 43 FGA tuples, 21 Keycloak users and the foundation/model Secrets. The original factory index hash remains unchanged after applying only the companion delta to its working tree.

The developer explicitly took ownership of all `make k3d-*` execution before any deployment mutation. The local image build was stopped during Knowledge Flow image export; only the manager image build completed. No integrated rollout, live folder response or convergent rerun is claimed. Run from the original factory: `make k3d-app APP=fred DIR=../fred`, inspect the result, then repeat for convergence. Keep this change active until that acceptance is recorded.
