## 1. Establish the implementation baseline

- [x] 1.1 Confirm this Fred-only scope and acceptance criteria with the developer; record confirmation, identify/create the GitHub issue, and isolate factory work from its dirty observability branch. Verify Fred remains on the user-selected branch and unrelated edits are preserved.
- [x] 1.2 Select and install a verified Helmfile release compatible with local Helm, documenting the prerequisite; verify its version and commands against an inert test state.

Evidence: scope confirmed on 2026-10-05 with local-only simplification; tracking #2957. Factory worktree `/home/dimi/Fred/fred-deployment-factory-helmfile`, branch `codex/fred-k3d-helmfile`, based on `cde7890`; original dirty worktree unchanged.

## 2. Product preparation and installation composition

- [x] 2.1 Add Fred image preparation using existing Make builds, content tags and backend/worker mappings; test generated Helm values/image lists, unchanged tags, build failures and paths with spaces using command doubles.
- [x] 2.2 Add factory Helmfile state and the explicit deployment/validation entrypoints with installation/image values and a release override (local chart only); verify real Helm lint/template against the existing installation values and prepared overrides.
- [x] 2.3 Move narrowly scoped Fred operations to product tooling and retain factory-owned import/recovery; test secret redaction, model consumer refresh, dashboard changes and bootstrap retrieval guidance.
- [x] 2.4 Make context targeting explicit throughout called helpers without changing existing evaluator behavior; test context preservation, PVC recovery refusal and stop-before-mutation behavior on validation/build failures.

## 3. Replace the old entrypoint and document usage

- [x] 3.1 Remove `k3d-fred` and its obsolete launcher without compatibility aliases; update Make help and active references in both repositories, excluding historical archives and immutable notes. Verify searches and help show the replacement commands.
- [x] 3.2 Update existing deployment guides and add the Fred migration note for local prerequisite/command changes; document direct Helmfile use versus full preparation/deploy, and verify `make migration-check`.

## 4. Verify and deliver

- [ ] 4.1 Run targeted command tests and required repository quality checks; record exact results separately from real Helm rendering evidence.
- [ ] 4.2 Deploy Fred on the existing cluster, verify all six deployments, worker image consistency, dashboard availability and frontend access, then rerun to check convergence. Record remaining authenticated/manual checks and explicitly state that fresh-cluster installation was not tested. Never wipe/delete the cluster or uninstall infrastructure.
- [ ] 4.3 Apply the branch audit procedure and obtain an independent read-only review of both diffs; record base/head, coverage, findings, dispositions and exclusions in the task/PRs.
- [ ] 4.4 Reconcile and validate the artifacts, sync/archive after acceptance and completed verification, commit reviewable blocks and open linked draft PRs in Fred and factory; verify unrelated edits are excluded.

Verification so far: Helmfile 1.8.1 archive checked against the upstream release SHA256, Helm 3.21.2. Real Helmfile lint/template pass with installation values; lint skips its schema pass because it retains null deletion markers, while template and sync enforce the schema. Four Fred and five factory command tests pass; these are simulated commands, not cluster evidence. Migration note validation passes.
