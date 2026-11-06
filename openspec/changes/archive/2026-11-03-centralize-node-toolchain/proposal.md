## Why

Node selection is duplicated across developer tasks, Make, CI and images. Issue #3424 started with a stale IDE PATH; the developer has confirmed centralizing an exact Node 24 version and selecting it from current security advisories.

## What Changes

- Pin root .nvmrc to 24.22.2, which includes the October 2026 Node 24 security fixes.
- Read that file in active installation/build entry points and update the current release toolchain record to match.
- Keep supported engines >=24.21.0 <25 and npm 11.19.0; preserve historical release evidence.
- Select affected CI checks and the frontend image when .nvmrc changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: use an exact repository Node baseline consistently for future release validation.

## Impact

Local task startup, shared Make configuration, frontend CI/publication, frontend production image, devcontainer, current release policy, documentation and focused tooling tests. No service API, database, shared runtime state or multi-pod behavior changes. Existing unsupported Dockerfile-dev is excluded from this tooling consolidation.
