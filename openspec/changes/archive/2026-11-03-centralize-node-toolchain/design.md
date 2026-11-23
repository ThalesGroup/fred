## Context

Make uses one Node constant for both a build image and a compatibility minimum. CI and the devcontainer repeat that constant. Release contracts record exact producer/application versions and must stay reproducible. See proposal.md for scope and motivation.

## Goals / Non-Goals

Use .nvmrc as the exact current repository baseline. Preserve the separately declared supported engine range and historical release records. Do not repair the already excluded legacy development Dockerfiles or change the deployed nginx runtime.

## Decisions

- Select 24.22.2: the official October 21 security release is 24.22.1, followed by 24.22.2 on October 28. This is an advisory-based choice, not a claim of zero known CVEs or a completed container scan. References: https://nodejs.org/en/blog/release/v24.22.1 and https://nodejs.org/en/blog/release/v24.22.2.
- Make reads the root file relative to node.mk, while its minimum remains 24.21.0. CI setup-node uses node-version-file; current release contracts record 24.22.2 and retain npm 11.19.0.
- Frontend Docker builds receive NODE_VERSION read from .nvmrc through Make or CI before FROM is resolved. The build context copies .nvmrc for Make. No floating Docker default is introduced.
- Devcontainer initialization prepares an ignored Dockerfile with the Node argument default read from .nvmrc, using the existing Dockerfile as its template. This avoids a second maintained version in devcontainer.json, which cannot evaluate shell substitutions in build arguments.
- Root version changes select frontend package/application CI and the frontend image. Tests verify those consumers and reject divergent release toolchain records before new evidence is produced.

## Risks / Trade-offs

- An exact local version may be missing: nvm must report nvm install guidance; tasks do not download automatically.
- New release evidence must be regenerated with the selected toolchain. Existing archives and historical records are not rewritten.
- Image scanner results depend on the OS variant, digest and vulnerability database. Verify the actual build image separately; do not compare different OS variants as evidence about Node core.

## Migration Plan

Developers run nvm install once after the pin changes. Normal deployment suffices. Revert the coherent tooling change to roll back; no database or distributed-state migration is needed.
