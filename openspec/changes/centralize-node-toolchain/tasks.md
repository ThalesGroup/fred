## 1. Shared version selection

- [ ] 1.1 Pin .nvmrc to 24.22.2 and load it from shared Make while preserving the >=24.21.0 <25 compatibility check; verify task startup from apps/frontend and the existing Node version matrix tests.
- [ ] 1.2 Switch all ten setup-node steps to node-version-file and include .nvmrc in application/package CI selection; verify ci-selection.test.mjs and package input contracts.

## 2. Build images

- [ ] 2.1 Feed NODE_VERSION from .nvmrc into frontend Make/CI Docker builds and copy the file into the build context; verify image selection tests, rendered build arguments and a frontend build check without publishing.
- [ ] 2.2 Prepare the devcontainer Dockerfile from .nvmrc during initialization with generated output ignored; verify generation from a different working directory, exact version selection and Dockerfile syntax.

## 3. Release compatibility and documentation

- [ ] 3.1 Update current release toolchain records to 24.22.2 and validate their agreement with .nvmrc without rewriting historical evidence; verify release contract/toolchain tests and regenerate/validate all three package archives with npm 11.19.0.
- [ ] 3.2 Update installation/release documentation and the PR migration note; verify migration-check and remove obsolete active setup version instructions while preserving historical notes.

## 4. Close-out

- [ ] 4.1 Run focused affected tests and root make code-quality, obtain author and independent read-only review, and record results and any environment limitations in this task file and the PR.
- [ ] 4.2 Reconcile and validate the change, sync its delta and archive only after acceptance and verification are complete; verify OpenSpec validation and the final PR diff against swift.
