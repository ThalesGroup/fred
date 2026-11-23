## 1. Shared version selection

- [x] 1.1 Pin .nvmrc to 24.22.2 and load it from shared Make while preserving the >=24.21.0 <25 compatibility check; verify task startup from apps/frontend and the existing Node version matrix tests.
- [x] 1.2 Switch all ten setup-node steps to node-version-file and include .nvmrc in application/package CI selection; verify ci-selection.test.mjs and package input contracts.

## 2. Build images

- [x] 2.1 Feed NODE_VERSION from .nvmrc into frontend Make/CI Docker builds and copy the file into the build context; verify image selection tests, rendered build arguments and a frontend build check without publishing.
- [x] 2.2 Prepare the devcontainer Dockerfile from .nvmrc during initialization with generated output ignored; verify generation from a different working directory, exact version selection and Dockerfile syntax.

## 3. Release compatibility and documentation

- [x] 3.1 Update current release toolchain records to 24.22.2 and validate their agreement with .nvmrc without rewriting historical evidence; verify release contract/toolchain tests and regenerate/validate all three package archives with npm 11.19.0.
- [x] 3.2 Update installation/release documentation and the PR migration note; verify migration-check and remove obsolete active setup version instructions while preserving historical notes.

## 4. Close-out

- [x] 4.1 Run focused affected tests and root make code-quality, obtain author and independent read-only review, and record results and any environment limitations in this task file and the PR.
- [x] 4.2 Reconcile and validate the change, sync its delta and archive only after acceptance and verification are complete; verify OpenSpec validation and the final PR diff against swift.

## Verification and review

- Developer confirmed the complete plan with "ok go" before implementation; the topic branch was moved into the main checkout at the developer's request.
- Exact .nvmrc discovery and Make Node check pass with inherited Node 24.15.0 and selected Node 24.22.2. The compatibility matrix still accepts >=24.21.0 <25.
- Complete producer suite: 400 tests passed under Node 24.22.2/npm 11.19.0 after provisioning the existing React/iframe offline caches. Initial cache/stamp failures were resolved without changing those tests.
- Producer ESLint and release-contract checks passed. All three archives were regenerated and validated with npm 11.19.0. Fifteen image-selection tests passed; the migration note is valid.
- Frontend and generated devcontainer Docker --check passed without warnings using Docker Hub's official Node image for metadata resolution. The configured mirror returned HTTP 429, so a complete image build against that mirror was not verified. Production Docker requires the version argument from Make/CI; its default-argument check is explicitly skipped to avoid a floating fallback.
- Independent read-only review covered the complete change against origin/swift at a997ee4b3f8ff3053477c0d2399c2f79abadd580, HEAD c207112a2f75facffca1203b4f57696e740f5625 plus local changes. One P2 found a bypass at candidate/fixture evidence creation. Shared baseline checks now cover candidate, transfer and direct evidence production; three boundary regressions pass. A second review replayed all three paths and confirmed resolution, with no new findings. Historical verification remains unchanged.
- No service API, data migration, concurrency, distributed-state or runtime performance path changed. Live VS Code/devcontainer startup, complete Docker image builds, browser compatibility gates and registry publication were not exercised.

- Root make code-quality passed across all modules with PIP='uv pip' UV=uv, using the existing global uv bootstrap because the ordinary invocation stops at the pre-existing missing .venv/bin/pip. The check commands themselves were unchanged; the root migration-tool suite passed 28 tests.
- All 38 main specs validate. Final bounded independent review accepted the required Docker version-argument directive and the synced specification with no additional findings.
