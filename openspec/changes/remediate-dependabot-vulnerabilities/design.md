## Context

See proposal.md. Current alerts on existing manifests cover PyJWT in ten `uv.lock` files, Knowledge Flow's pinned ML and development dependencies, and npm dependencies in `apps/frontend` and `libs/frontend`. Another 98 alerts point to ten paths absent from the current tree. Knowledge Flow uses different torch wheels for Linux x86_64 and other architectures.

## Goals / Non-Goals

**Goals:** Resolve currently actionable alerts using normal package-manager resolution, preserve supported platforms, and leave traceable evidence for obsolete alerts.

**Non-Goals:** Change authentication policy, ingestion features, public APIs, or add a standing dependency policy to product specs.

## Decisions

- Update direct constraints where they block safe releases, then regenerate each affected lock with `uv` or `npm`. Avoid manual lockfile edits because hashes, markers, and transitive versions must remain consistent.
- Use the vendor-published PyTorch 2.13.0 / torchvision 0.28.0 pair, retaining CPU wheels on Linux x86_64 and existing macOS/ARM markers. Transformers must reach at least 5.10.0. If resolution or focused tests fail, fix compatibility in the affected application and document any upstream blocker precisely.
- Use `npm` overrides only where the owning direct dependency cannot yet resolve a fixed transitive release. Keep overrides narrow and explain why in the PR.
- Docling 2.131 resolves OpenVINO RapidOCR artifacts itself. Remove the build-time patch written for Docling 2.78, which accesses a class attribute no longer present in the upgraded module.
- Treat alerts on removed paths as inventory debt. Confirm each path is absent on swift and check its live replacement. All 98 obsolete-path alerts were dismissed as not used, each with an auditable comment after the current replacement locks were checked.

## Risks / Trade-offs

- [Major ML package upgrades alter APIs or wheel availability] -> Resolve for existing platform markers and run Knowledge Flow import and ingestion tests.
- [Shared PyJWT changes token validation] -> Run authentication-focused tests in components that verify tokens.
- [Transitive npm upgrades alter build tooling] -> Run builds and focused package tests for both npm projects.
- [GitHub alert closure lags the PR] -> Record before/after manifest versions and revisit the alert state after merge.

## Migration Plan

Publish a migration note. Normal deployment should install the refreshed locks; no data or configuration migration is expected. Rollback to the previous image restores prior dependencies but reintroduces the reported vulnerabilities, so operators should redeploy a corrected image promptly.
