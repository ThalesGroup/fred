## Why

FRED can build and validate three development archives, and the coordinate-independent
release tooling is implemented. Maintainers have now selected the `@fred-oss` coordinates,
public npm policy, bootstrap account, and guarded workflow identity. The repository needs
release-ready manifests and a manual first-release workflow. Maintainers have now confirmed the
remaining ownership and direct-publication policy while preserving fail-closed execution gates
that publish only exact reviewed bytes after explicit approval.

## What Changes

- Add release metadata and independently selected package coordinates for the design-token,
  UI, and iframe SDK members while keeping the producer workspace private and excluded from
  release.
- Replace hard-coded development coordinates in packing, validation, tests, and isolated
  consumers with an explicit release contract that synchronizes manifests, peer dependencies,
  and the producer lockfile.
- Validate dependency references by boundary: permit only npm-generated links for the declared
  private-workspace members; reject local and local-Git dependency protocols from published
  manifests; permit
  integrity-verified candidate-tarball references in disposable offline consumers only when every
  declaration uses the exact generated `file:<approved filename>` form, every package-resolution
  entry supplies matching SHA-512 integrity, and the reference matches an approved package
  identity and archive; validate that graph before dependency installation; and require
  registry-installed consumers to resolve exact registry versions without local fallback.
- Validate actual candidate tarballs against selected expected coordinates and the complete
  existing archive contracts rather than trusting metadata declared by an archive.
- Record immutable candidate evidence: source commit, exact Node/npm versions, package
  coordinates, archive filenames, and SHA-512 integrity. Any rebuilt or modified archive
  requires new validation and evidence.
- Exercise that immutable-byte boundary before coordinate approval by transferring one explicitly
  fixture-labelled three-archive set from the release-toolchain job to the application-toolchain
  job in the same workflow run. The receiver independently verifies commit, contract, run/attempt,
  package identity, byte length, and SHA-512 before passing only those archive paths to the
  existing offline consumers, browser smoke, and production-host compatibility gates.
- Add a registry-verification command that requires exact package coordinates and recorded
  integrity, rejects local/workspace fallback, cryptographically verifies provenance against
  the expected signer certificate URI and issuer, compares
  its artifact digest, source repository, source commit, and publishing workflow identity with
  explicit release expectations, and exercises clean registry-installed consumers. A valid
  signature alone does not establish the intended release identity. Local tests of the command
  remain distinct from evidence of a successful run against genuinely published packages.
- Read npm provenance discovery from the registry's `dist.attestations.url` metadata shape,
  re-root its approved endpoint path onto the selected registry as npm does, and fail closed on
  missing, malformed, disallowed, or coordinate-mismatched attestation endpoints.
- Materialize the disposable registry verifier's already validated lock graph with lifecycle
  scripts disabled before npm signature audit, prove the selected package exists in that fresh
  installed tree, and reject lock-only, linked, escaped, mismatched, or locally resolved trees.
- Bind post-publication browser verification to the same explicit pre-provisioned Playwright
  directory used by its workflow provisioning step; missing or differently resolved Chromium
  fails actionably without downloading during verification.
- Pin the producer release toolchain exactly and preserve the separately controlled tooling
  used by CI jobs that also run FRED application tests.
- Extend CI selection and regression coverage for release inputs, keep release-readiness jobs
  self-contained by provisioning their isolated-consumer caches before offline package tests,
  and add a compact release runbook plus a targeted RFC sequencing clarification separating
  readiness, publication, FRED adoption, and external adoption.
- Record the confirmed `fred-oss` organization, three `@fred-oss/*@0.1.0-alpha.1`
  coordinates, public npm registry/access, `next` tag, `marc.fawaz` bootstrap account and
  verified organization-owner authority; record `marc.fawaz` as package API, SDK protocol,
  release, and enduring npm-publishing owner and select direct Trusted Publishing for subsequent
  releases. GitHub reviewer `marcfawaz` remains a distinct operational identity.
- Add a `workflow_dispatch`-only, `swift`-restricted publication workflow that defaults to
  preparation only, transfers immutable candidates across the release and application
  toolchains, uses the protected `npm-publish` environment and its bootstrap token only in an
  explicitly selected initial or partial-recovery publishing step, and performs genuine registry verification
  after publication.
- Correct exact-version post-publication reconciliation to tolerate bounded npm visibility lag
  through a shared, bounded exact-version HTTP adapter that does not depend on npm's package-wide
  metadata lookup, without ever retrying publication, and add an explicit protected recovery operation for the
  partial first release from run `34853407387`. The recovery preserves the original candidate
  artifact and evidence, derives all candidate inputs from the hash-pinned ZIP at both trust
  boundaries, rejects inconsistent transferred copies and unsafe ZIP entries, verifies the
  already-published design-token bytes and provenance, and publishes only the still-absent UI and
  SDK archives from the verified extraction while binding their provenance to the recovery
  workflow's actual `GITHUB_SHA`.

This change prepares but does not trigger the publishing workflow. It does not create GitHub/npm
settings, publish or stage packages, claim public-registry success, or migrate FRED or RAGS.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Add release-coordinate, immutable candidate-evidence,
  boundary-aware dependency validation, release-identity-bound provenance,
  registry-verification, release-toolchain, sequencing, and CI-selection requirements while
  preserving every existing design-token, UI, and iframe SDK archive guarantee.

## Impact

- Producer manifests and lockfile under `libs/frontend/`, package scripts and validators,
  isolated consumer fixtures, browser/host integration orchestration, and their tests.
- The producer lockfile retains only npm's expected links to declared workspace members;
  disposable consumers may refer only to integrity-verified candidate tarballs, while published
  manifests and registry consumers remain free of local/workspace dependency fallback.
- Frontend-package Makefile targets, exact CI input selection, a release-readiness command, and
  `.github/workflows/Publish-frontend-packages.yml`;
  application-owned Node/npm tooling remains independently controlled while verified fixture
  archives cross the CI job boundary without dependency trees or consumer caches.
- `libs/frontend/` release documentation and the existing
  `docs/swift/FRED-FRONTEND-PACKAGING-RFC.md`; the RFC remains authoritative for broader
  publication, adoption, and future package work.
- No application or RAGS source changes, registry mutation, package publication, protocol
  ownership transfer, or package adoption are part of this change.
- Tracking: [ThalesGroup/fred#2630](https://github.com/ThalesGroup/fred/issues/2630) —
  **Frontend packages: establish release-ready manifests, versioned archives, and registry
  verification foundations**.
