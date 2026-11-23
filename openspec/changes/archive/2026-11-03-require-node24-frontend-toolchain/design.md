## Context

See proposal.md for the CI failure and selected compatibility policy. The application currently pins Node 22.13.0 in its Makefile, Dockerfiles and four CI setup steps. The package producer advertises >=22.13.0 <25; its three distributed members advertise >=22.13.0. Release preparation already pins Node 24.21.0/npm 11.19.0, but application evidence fixtures still describe Node 22/npm 10.

## Goals / Non-Goals

One supported Node major across application builds, local tests, producer tooling and package consumers. Preserve immutable archive transfer and separate evidence ownership even when producer and application toolchains match. Dependency security updates remain in #3298; publication, release versions, backend code and browser contracts are outside this change.

## Decisions

1. Reuse Node 24.21.0/npm 11.19.0 as the exact reproducible baseline for both toolchain roles. Package support is >=24.21.0 <25, not exact-patch-only support. Retaining a Node 22 lane contradicts the developer's decision; floating Node 24 pins weaken reproducibility.
2. Align CI, both frontend Dockerfiles, the Makefile check/regeneration image, application/producer/member engines and active setup instructions. Use existing Makefile and npm engine mechanisms to reject unsupported Node majors before installing or building. Keep the release preflight's stricter exact Node/npm check.
3. Update both release-contract JSON files and successful evidence fixtures. Keep role-specific evidence and archive transfer checks; identical version numbers do not justify combining environments or accepting the producer's installed tree as an application consumer.
4. Regenerate lock metadata using the selected toolchain. Inspect structural package changes and exclude unrelated dependency upgrades; #3298 remains authoritative for Happy DOM, Undici, fast-uri and KaTeX.

## Risks / Trade-offs

- External build consumers lose Node 22 support: publish clear prerequisites and a migration note; package publication/version selection remains a separate release decision.
- A CI-only fix would leave local and container tests broken: validate every active application toolchain reference, including release receiver fixtures and lock metadata.
- Matching toolchain versions could conceal archive-transfer regressions: retain independent producer/receiver evidence and the existing isolated consumer/browser checks.
- No runtime hot path, shared state, query, memory or multi-pod ownership changes are introduced; the deployed frontend still serves browser assets through its existing server.

## Migration Plan

Land the toolchain change first, then update #3298 with swift and require fresh green checks before merging it. Custom build environments and package consumers install Node 24.21.0/npm 11.19.0. Official images use the updated builder automatically. Roll back source/toolchain pins and matching manifests/locks together; Node 22 cannot validate the new dependency graph. Document actual operator impact in the implementation PR's migration note. No tags or package publication are part of this work.
