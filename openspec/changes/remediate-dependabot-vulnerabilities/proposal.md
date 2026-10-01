## Why

Dependabot reports 222 open alerts on `swift`, including critical PyJWT alerts. Current lockfiles still contain affected releases, while 98 alerts refer to paths removed or moved during repository restructuring. Issue #2854 tracks one reviewable remediation.

## What Changes

- Upgrade affected Python and npm dependency declarations and regenerate current lockfiles to fixed releases.
- Keep PyTorch and torchvision on a published compatible pair for all existing platform markers, and validate Knowledge Flow after the Transformers upgrade.
- Verify that current manifests no longer resolve reported vulnerable versions and triage obsolete-path alerts against the current tree.
- Add a migration note with deployment and rollback guidance for the dependency refresh.

## Capabilities

No product capability or public contract changes are intended. This maintenance change opts out of delta specs because the existing behavior is preserved.

## Impact

Affected components: Control Plane, Fred Agents, Fred core/runtime/SDK and capabilities, Knowledge Flow, both frontend npm projects. No API, database, or configuration contract changes are planned. Runtime package changes require focused compatibility verification, especially for authentication and document ingestion.
