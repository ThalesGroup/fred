## Why

Fred's release skill prepares the application and chart tags without preparing Python library versions. The current Python release tooling forces every distribution to share one version, so it cannot advance the three shared libraries on each Fred release while advancing only capabilities that changed.

Tracking: https://github.com/ThalesGroup/fred/issues/3126

## What Changes

- Prepare one patch increment for `fred-core`, `fred-sdk`, and `fred-runtime` before each paired code/chart release. Keep the application/chart version governed by migration impact; Python package versions are separate coordinates.
- Identify capability code changed since the previous stable code tag. Advance each affected capability distribution and each affected `CapabilityManifest.version` by one patch after reviewing saved-config compatibility. Leave unchanged distributions and manifests at their existing versions. `fred-pod` advances only when its own package changes.
- Replace the all-packages version assumption in preparation and publication validation with a reviewed per-package version map. Update dependency floors where a changed distribution needs the newly prepared libraries, synchronize affected `uv.lock` files, and keep the pod chart `appVersion` fields aligned with their SDK/runtime libraries.
- Update the release skill and release strategy to present the package/manifest version map, lockfile result, and compatibility findings before tag approval. Preserve separate approval for actual PyPI publication.

## Capabilities

### New Capabilities

- `python-package-releases`: Independent Python distribution and capability manifest version preparation, dependency and lockfile consistency, and prepublication validation.

### Modified Capabilities

None. The existing release migration guide contract continues to set only the paired application/chart version minimum.

## Impact

Release tooling and tests under `scripts/`, root `Makefile`, Python package manifests and lockfiles under `libs/` and `apps/`, capability manifest authoring guidance, `docs/swift/RELEASE-STRATEGY.md`, and the shared `push-release` skill. This change does not publish packages, place tags, or change a running deployment.
