## Context

The production Dockerfiles copy a Python virtual environment created by `make dev`. That installs the default development group, including a Node.js toolchain used by basedpyright. The first Trivy run on the three Python images found 29 critical findings: 3 embedded npm, 2 Chroma, and 24 OS package findings. Knowledge Flow still builds on Python 3.12.8 slim (Debian 12); the other Python images use 3.12.13 slim (Debian 13).

## Goals / Non-Goals

**Goals:** Keep production runtime dependencies and editable local packages, remove development-only tooling, consume available OS fixes, and measure the outcome with the PR scanner.

**Non-Goals:** Change application behavior, suppress scanner findings, or upgrade Chroma without a verified compatible fix.

## Decisions

- Add a standalone production dependency target to the shared Make recipe, using `uv sync --locked --no-default-groups`. Leave `make dev` unchanged. The final Knowledge Flow image installs system pandoc.
- Build the three Python production environments with that target. This removes basedpyright and its embedded Node.js packages from the shipped virtual environments without changing runtime lock resolution.
- Refresh OS packages at build time in each final stage. Align Knowledge Flow's builder and final stages with the Debian 13 Python 3.12 base already used by the other services. This provides available security fixes and keeps Python ABI consistent across build and runtime stages.
- Use the existing PR Trivy workflow to compare findings with the original JSON reports. Record unfixed and Chroma server findings explicitly; do not add ignore rules for them.

## Risks / Trade-offs

- A package incorrectly classified as development-only could be needed at runtime. Mitigation: inspect the production environment and run service smoke checks in CI.
- A newer OS package or Debian release could affect document processing or native libraries. Mitigation: keep Python minor version 3.12, validate image builds and representative imports, and document image rollback.
- Debian packages without published fixed versions remain visible. Mitigation: report residual CVEs and follow upstream fixes separately.

## Migration Plan

Build and deploy the updated images through the normal release process. No data migration or configuration change is needed. Roll back to the previous images if runtime behavior regresses.

## Follow-up decisions

- Use Python 3.12.15 slim-trixie for all production Python stages, retaining the
  existing stable Debian release and normal apt security upgrades. Remove the
  installed pip copies after the last installation; do not remove package
  metadata or suppress scanner findings.
- Knowledge Flow imports Embeddings directly from langchain-core. Remove its
  unused langchain meta-package and relock, retaining the existing providers.
  Update Docling to the patched 2.132.0 and MCP to the patched v1 line. Keep
  Writer, Calc and Impress conversion support with their headless packages;
  retain document/media tools with active consumers.
- Temporal 1.30.0 is the smallest inspected release correcting four of the five
  reported embedded-crate findings. Set a matching floor in fred-core and the
  SDK knowledge-base extra and refresh dependent locks. Later inspected releases
  through 1.34.0 still contain the affected rustls version, so a larger upgrade
  offers no demonstrated security benefit for that finding. Version 1.30 supports
  compression downgrade for older gRPC proxies; Fred has no custom affected
  update-with-start interceptor or AWS Lambda worker. Verify actual workflows,
  payload conversion and client/worker interoperability before accepting it.
- Require uv 0.12.23 or newer in fred-core and refresh older consumer locks.
  Knowledge Flow's shipped uv/uvx binaries embed affected quinn-proto and rustls;
  the already scanned control-plane uv 0.12.23 has neither reported finding.
- Increment each modified library's patch version as requested, and propagate
  the corrected internal dependency floors to capabilities and applications.
  Keep capability configuration versions unchanged because their schemas and
  persisted configuration semantics do not change. Validate wheels and sdists
  without publishing, including an independent consumer of the new versions.
- Compare fresh final-image scans with v3.6.1, using the same Trivy database;
  retain the frontend image and npm evidence from the preceding verified slice.
  Record OS, Python and embedded-crate findings separately. For residual critical
  findings, distinguish upstream fix availability from assessed reachability.

Acceptance: supported API imports, SDK sandbox workflow preparation, document
conversion and existing offline suites remain valid; production dependency
inventories exclude removed packages; every remaining critical/high library
finding has a disposition. No deployment, release, or PR is part of this pass.
