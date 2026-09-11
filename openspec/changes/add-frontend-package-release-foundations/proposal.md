## Why

FRED can build and validate three development archives, but their manifests,
validators, and consumers still assume `0.0.0-development` and do not produce the
immutable evidence needed to release exactly the bytes that were reviewed. A bounded
repository-readiness slice is needed before maintainers configure npm ownership or
authorize any publication.

## What Changes

- Add release metadata and independently selected package coordinates for the design-token,
  UI, and iframe SDK members while keeping the producer workspace private and excluded from
  release.
- Replace hard-coded development coordinates in packing, validation, tests, and isolated
  consumers with an explicit release contract that synchronizes manifests, peer dependencies,
  and the producer lockfile.
- Validate actual candidate tarballs against selected expected coordinates and the complete
  existing archive contracts rather than trusting metadata declared by an archive.
- Record immutable candidate evidence: source commit, exact Node/npm versions, package
  coordinates, archive filenames, and SHA-512 integrity. Any rebuilt or modified archive
  requires new validation and evidence.
- Add a registry-verification command that requires exact package coordinates and recorded
  integrity, rejects local/workspace fallback, checks public-registry integrity and provenance,
  and exercises clean registry-installed consumers. Local tests of the command remain distinct
  from evidence of a successful run against genuinely published packages.
- Pin the producer release toolchain exactly and preserve the separately controlled tooling
  used by CI jobs that also run FRED application tests.
- Extend CI selection and regression coverage for release inputs, and add a compact release
  runbook plus a targeted RFC sequencing clarification separating readiness, publication,
  FRED adoption, and external adoption.
- Keep `@fred/design-tokens`, `@fred/ui`, `@fred/iframe-sdk`, `0.1.0-alpha.1`, and the `next`
  dist-tag as proposals until maintainers confirm scope ownership, coordinates, access,
  publishing owners, registry settings, workflow identity, and bootstrap authorization.

This change does not publish packages, add a publishing workflow, configure registry access,
or migrate FRED or RAGS.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Add release-coordinate, immutable candidate-evidence,
  registry-verification, release-toolchain, sequencing, and CI-selection requirements while
  preserving every existing design-token, UI, and iframe SDK archive guarantee.

## Impact

- Producer manifests and lockfile under `libs/frontend/`, package scripts and validators,
  isolated consumer fixtures, browser/host integration orchestration, and their tests.
- Frontend-package Makefile targets, exact CI input selection, and a release-readiness command;
  application-owned Node/npm tooling remains independently controlled.
- `libs/frontend/` release documentation and the existing
  `docs/swift/FRED-FRONTEND-PACKAGING-RFC.md`; the RFC remains authoritative for broader
  publication, adoption, and future package work.
- No application or RAGS source changes, registry mutation, package publication, protocol
  ownership transfer, or package adoption are part of this change.
- Tracking issue to create after approval: **Frontend packages: establish release-ready
  manifests, versioned archives, and registry verification foundations**.
