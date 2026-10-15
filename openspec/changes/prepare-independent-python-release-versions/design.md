## Context

`make libs-version VERSION=...` currently rewrites every package in `PYPI_PACKAGES` to one version, raises their internal floors to that version, relocks consumers, and sets both pod chart `appVersion` values. `scripts/validate_python_release.py` requires one version across all distributions and exact same-version floors. This conflicts with selected capability increments. Some capability distributions own several `CapabilityManifest` values; `fred-capability-mcp` owns none. A manifest version is a saved-config schema version, not the PyPI distribution version. See `docs/swift/capabilities/AUTHORING.md` and `fred_runtime/capabilities/assembly.py`.

The paired `code/v...` and `chart/v...` version is independently set by migration impact. The shared release skill stops for tag approval; `make publish-libs` is a separate manual PyPI operation. The current `fred-pod` chart `appVersion` tracks `fred-pod` package metadata and must not be changed merely because the other libraries advance.

## Goals / Non-Goals

**Goals:**

- Make the three shared library increments repeatable, idempotent within one release, and independent of the application/chart version.
- Keep each package's `[project].version` authoritative; select changed capability packages and affected manifests from the stable-tag diff with human review.
- Validate exact artifacts and dependency floors across mixed package versions before PyPI upload.

**Non-Goals:**

- Automatic PyPI publication, package creation, release tagging, or changing the migration-impact version rule.
- A new version registry or a blanket update of unchanged capability packages.
- Automatically proving stored-config compatibility from a manifest version string alone.

## Decisions

### 1. Use the stable code tag as the release comparison boundary

The release helper already identifies the correct branch-ancestry baseline. The skill will use that tag for a package diff and compare package versions against the tagged manifests. Changes under a capability distribution's maintained files make it a bump candidate; generated locks, build outputs, and a version-only preparation diff do not. Review the candidate list and explicitly select affected manifests, including shared-code effects across a multi-manifest distribution. A repeat run compares the intended next patch against the current worktree and does not increment twice. Unexpected current versions or pre-existing independent PyPI publication require review instead of an automatic rewrite.

Alternative: bump all packages together as today. This is simpler but contradicts independent coordinates and makes unchanged capability releases indistinguishable from changed ones.

### 2. Extend the existing version and publication tools around package coordinates

Refactor `scripts/libs_version.py` and the root release target to prepare the three shared libraries plus an explicit reviewed set of changed capability distributions. Derive each next patch from its tagged `[project].version`; apply selected package versions, selected manifest literals, and only necessary internal dependency floors. Read the resulting per-package map from `pyproject.toml` rather than maintaining a second version ledger. Keep package build and upload in existing dependency order. `fred-pod` participates only if changed; update pod chart `appVersion` only when its own version advances.

Refactor `scripts/validate_python_release.py` to validate each selected package against its own manifest and artifact coordinate, and validate internal requirements against the map. An unchanged package with a compatible older floor is valid; an advanced package whose published dependency contract needs a new library must raise that floor. The prepublication target must decide pending packages before any upload and reject missing/stale selected artifacts. Existing PyPI coordinates remain immutable and are skipped only when registry checks confirm them.

Alternative: add a release-specific side script that bypasses the current validator. That would leave two conflicting publication contracts and allow a manual publish path to accept the wrong artifacts.

### 3. Treat manifest bumps as config migrations, including additive cases

For each selected manifest, test a representative saved envelope from the tagged version against the new version. The default `upgrade_config` can validate additive shapes on a version mismatch; breaking shapes require a capability-specific upgrade path and tests. Update the pre-GA no-bump guidance in `AUTHORING.md` to describe release-time patch bumps and their compatibility check. Manifests are not forced to equal their distribution's version, and unrelated manifests in the same distribution remain unchanged.

Alternative: blindly patch every manifest in a changed package. This could invalidate stored agent configurations and would create needless cache invalidations.

### 4. Relock affected uv projects after the final version map is written

Use `uv lock` on every project whose committed lock resolves an advanced distribution, including apps and capability projects. Reuse the existing lock discovery where possible. Verify that lockfile package versions match the source map and inspect the diff for unrelated dependency churn. Do not use a broad dependency upgrade as the release synchronization step.

## Risks / Trade-offs

- **Incorrect capability selection** -> show the stable-tag diff and reviewed selected/unchanged list in the release approval packet; fail on unexplained version drift.
- **Saved configs fail after manifest bumps** -> run focused old-envelope tests and require an upgrade hook for incompatible shapes before readiness.
- **A mixed-version wheel references an unavailable dependency** -> validate internal floors and artifact metadata against the package map, then preserve dependency-order publication and registry-readiness checks.
- **Lockfile churn** -> relock only affected projects and review unexpected changes.

## Migration Plan

1. Update the version helper, publication validator and focused tests using a controlled mixed-version fixture. Keep existing published 4.5.0 coordinates intact until a real release is prepared.
2. Update the root targets, release skill, release strategy, and capability authoring policy. Validate a dry run with one changed multi-manifest capability and one unchanged capability without publishing or tagging.
3. During a real release, prepare and review the exact version map and locks with the notes and operator guide. After the existing explicit tag approval, commit those files with the release documents, tag and push. PyPI publication remains a separately approved manual step.

Rollback before publication is restoring the preparation commit. Once PyPI coordinates are published, retain them and issue a later version for fixes; never overwrite a published coordinate.
