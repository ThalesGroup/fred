# Python Package Releases Specification

## Purpose

Defines how Fred prepares and validates independently versioned Python distributions and capability manifests before a paired application and chart release.

## Requirements

### Requirement: Shared libraries receive a patch release coordinate

Release preparation SHALL advance `fred-core`, `fred-sdk`, and `fred-runtime` by exactly one patch from their previous released coordinates, independently of the Fred application/chart version. Repeated preparation for the same release SHALL preserve already prepared coordinates rather than incrementing them again.

#### Scenario: Fred minor release with unchanged Python major and minor coordinates

- **WHEN** the next Fred application/chart release is minor and the three shared libraries are at `4.5.0` in the previous release
- **THEN** their prepared coordinates are `4.5.1`, regardless of the application/chart version

#### Scenario: Preparation is repeated

- **WHEN** preparation runs again before tagging and the shared libraries already have the intended patch coordinates
- **THEN** their versions remain unchanged

### Requirement: Capability versions advance only for affected capabilities

Release preparation SHALL review changes since the previous stable code tag and advance each affected capability distribution by one patch. It SHALL advance `CapabilityManifest.version` by one patch for each affected manifest the changed distribution provides. Unaffected capability distributions and manifests SHALL retain their versions. A changed distribution with no manifest SHALL still receive its package patch increment. `fred-pod` SHALL advance only when its own package changes.

#### Scenario: One capability changes

- **WHEN** one capability distribution changes and another remains unchanged in the release range
- **THEN** only the changed distribution and its affected manifests receive patch increments

#### Scenario: A distribution contains several manifests

- **WHEN** a change affects one manifest in a distribution containing several
- **THEN** the distribution advances once and the affected manifest advances once, while unaffected manifests retain their versions

#### Scenario: Capability has no manifest

- **WHEN** a capability distribution without a `CapabilityManifest` changes
- **THEN** its distribution version advances and no manifest version is invented

### Requirement: Manifest version changes preserve stored configurations

Before a manifest version advances, release preparation MUST verify that config saved under the previous version remains readable or has a tested upgrade path. A failing compatibility check SHALL block release readiness.

#### Scenario: Additive config remains readable

- **WHEN** a manifest patch increment leaves prior stored config valid under the installed config model
- **THEN** the previous envelope resolves successfully under the new manifest version

#### Scenario: Breaking stored config shape

- **WHEN** a changed manifest cannot validate the previous stored config shape directly
- **THEN** a tested config upgrade path is required before release readiness

### Requirement: Dependency and lockfile state matches prepared versions

Release preparation SHALL update internal dependency floors for distributions that require newly prepared versions and synchronize affected `uv.lock` files. It SHALL preserve unrelated package coordinates and dependency floors when no corresponding package or compatibility need changed.

The agent-pod and knowledge-base chart `appVersion` values SHALL match the prepared `fred-runtime` and `fred-sdk` versions respectively.

#### Scenario: Shared library and one capability advance

- **WHEN** the shared libraries and one capability distribution advance
- **THEN** their own versions, necessary internal floors, both pod chart `appVersion` fields, and every affected committed lockfile resolve consistently while unchanged capability coordinates remain intact

### Requirement: Independent package artifacts are validated before publication

Prepublication validation SHALL accept a coherent mix of unchanged and newly prepared package versions. It MUST verify each selected artifact's own coordinate and internal dependency requirements against the reviewed version map and reject missing, stale, or inconsistent artifacts before any upload. Actual PyPI publication SHALL remain a separately authorized operation.

#### Scenario: Unchanged capability remains published at its prior version

- **WHEN** an unchanged capability retains its previous version while the shared libraries advance
- **THEN** validation accepts its existing package coordinate and does not require an artificial capability version increment or new artifact

#### Scenario: Artifact or dependency floor is inconsistent

- **WHEN** a wheel, source archive, or internal dependency floor disagrees with the reviewed package version map
- **THEN** validation fails before any package is uploaded

### Requirement: Release approval includes Python version changes

The release workflow SHALL present the shared library versions, selected capability distribution and manifest increments, unchanged capabilities, lockfile synchronization result, and stored-config compatibility findings alongside release notes and the operator guide before paired release tags are approved. It SHALL retain the existing explicit approval gate for tags and SHALL NOT treat that approval as authorization to publish Python packages.

#### Scenario: Review before tags

- **WHEN** a release is prepared for developer approval
- **THEN** the developer can review the exact package and manifest version map and evidence before deciding whether to create the code/chart tags
