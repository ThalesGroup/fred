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
