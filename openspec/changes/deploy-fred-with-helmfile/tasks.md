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

## 3b. Generalize (2026-10-05)

- [x] 3b.1 Move the release, the k3d values and the hooks into `deploy/k3d/` (helmfile, values, build, prepare, finish); the factory deploys any product through `make k3d-app DIR=...`. Verified: renders identical to the former factory values; 5 Fred and 8 factory command tests pass.

## 3c. Published releases without a checkout (2026-10-16)

Evidence already gathered: published chart `fred` 3.6.0 with its `v3.6.0` images and the current k3d values deployed successfully on a freshly wiped k3d (developer-run); chart `fred-evaluator` 1.2.0 renders with its k3d values, every container on `:v1.2.0`.

Factory (one PR, merged first; the product-owned `DIR` contract keeps working throughout):
- [x] 3c.1 `bin/k3d-app.sh`: `APP` resolves `k3d-apps/<APP>/`; with `DIR`, export `K3D_APP_CHECKOUT` and run the checkout's `deploy/k3d/build`; refuse a non-version `RELEASE`. Command tests in `bin/test_k3d_app.py`.
- [x] 3c.2 `k3d-apps/fred/`: helmfile (OCI chart pinned to 3.6.0, checkout chart in development mode), values (moved from Fred, evaluator declared at 1.2.0), `prepare` (model key from the environment), `finish` (login guidance; dashboards from the checkout in development mode). Hook tests moved from Fred's `deploy/k3d/test_hooks.py`.
- [x] 3c.3 `k3d-apps/fred-evaluator/`: helmfile (OCI chart pinned to 1.2.0), values, `identities.yaml`, `prepare`, `finish`, moved from the evaluator.
- [x] 3c.4 Factory `CLAUDE.md` model, `docs/LOCAL-DEVELOPMENT.md` (k3d walkthrough, application contract, `APP`/`RELEASE`), Makefile help.

Products (merged after the factory):
- [x] 3c.5 Fred (PR #3135): `deploy/k3d/` reduced to `build` and its test; helmfile, values, `prepare`, `finish`, `test_hooks.py` deleted; README and chart README point at `make k3d-app APP=fred [DIR=...]`; migration note updated.
- [x] 3c.6 fred-agent-evaluator (PR #58): `deploy/k3d/` reduced to `build`; docs updated likewise.

Verification:
- [ ] 3c.7 Real `helmfile template` for both applications in published, `RELEASE` and development modes; then, by the developer, a freshly wiped k3d with `make k3d-app APP=fred` and `APP=fred-evaluator`, no checkout, and the evaluation application opened in Fred.

Evidence (2026-10-16): factory `bin/test_k3d_app.py` 15 tests and `k3d-apps/fred/test_hooks.py` 5 tests pass; fred `deploy/k3d` 2 tests pass. Real `make k3d-app-validate` passes for `APP=fred`, `APP=fred-evaluator`, `APP=fred RELEASE=3.6.0`, `APP=fred DIR=<fred>`, `APP=fred-evaluator DIR=<evaluator>` and, unchanged, `DIR=<dt-agents>`; `RELEASE=latest` is refused. Real `helmfile template`: published Fred on `:v3.6.0`, evaluator on `:v1.2.0`. `RELEASE=3.5.0` is rejected by that chart's schema: the factory's values follow the pinned version, older releases are not guaranteed. The freshly wiped k3d deployment remains to be run by the developer.

## 4. Verify and deliver

- [ ] 4.1 Run targeted command tests and required repository quality checks; record exact results separately from real Helm rendering evidence.
- [ ] 4.2 Deploy Fred on the existing cluster, verify all six deployments, worker image consistency, dashboard availability and frontend access, then rerun to check convergence. Record remaining authenticated/manual checks and explicitly state that fresh-cluster installation was not tested. Never wipe/delete the cluster or uninstall infrastructure.
- [ ] 4.3 Apply the branch audit procedure and obtain an independent read-only review of both diffs; record base/head, coverage, findings, dispositions and exclusions in the task/PRs.
- [ ] 4.4 Reconcile and validate the artifacts, sync/archive after acceptance and completed verification, commit reviewable blocks and open linked draft PRs in Fred and factory; verify unrelated edits are excluded.

Verification so far: Helmfile 1.8.1 archive checked against the upstream release SHA256, Helm 3.21.2. Real Helmfile lint/template pass with installation values; lint skips its schema pass because it retains null deletion markers, while template and sync enforce the schema. Four Fred and five factory command tests pass; these are simulated commands, not cluster evidence. Migration note validation passes.
