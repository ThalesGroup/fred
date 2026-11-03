## Why

The frontend dependency update in PR #3298 cannot complete CI under Node 22.13.0: 16 jsdom workers fail while importing Undici. The developer selected Node 24 as the only supported major, using the existing release baseline instead of maintaining Node 22 compatibility. Tracking: #3416.

## What Changes

- **BREAKING**: require Node >=24.21.0 <25 for the frontend application, producer workspace and distributed frontend packages.
- Pin CI, development/build images and local tooling to Node 24.21.0. Reuse npm 11.19.0, already required by release preparation, for reproducible application and producer validation.
- Update active toolchain contracts, setup/release instructions and successful test fixtures; reject unsupported Node versions at existing command entry points before installation/build.
- Regenerate affected npm lock metadata without duplicating the dependency updates owned by #3298.
- Validate the complete frontend and packed consumers under the selected tooling, then update #3298 with the resulting swift baseline.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: restrict supported Node tooling to major 24 and align application and release toolchain pins while preserving archive/evidence separation.

## Impact

Affected surfaces: `.github/workflows/Check-pending-requests.yml`, frontend Dockerfiles/Makefiles/manifests and locks, `libs/frontend` package manifests, release contracts and associated tests, root/frontend setup and release documentation, and a migration note. Node-based build consumers must upgrade; browser APIs, backend behavior, authorization and persisted data are unaffected. No package publication, version tags or release workflow approval changes are included.
