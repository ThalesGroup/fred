## Why

The first three `@fred-oss` prereleases are published and verified, and the retained workflow now prepares candidates safely but cannot perform routine releases. A reviewed version/changelog change should release only selected packages without hand-editing incident identifiers, archive names, source hashes, or copies of package manifests in release scripts.

## What Changes

- Replace the three-role, manifest-duplicating release contract with one extensible registered-package inventory plus centrally maintained repository release policy. Package manifests remain authoritative for names, versions, dependencies, peers, and exports; a release PR explicitly changes selected versions, dependency ranges, and changelog entries.
- Select one or several registered packages for preparation/publication. Producer-wide regression coverage remains separate from the selected candidate set: a future SDK-only version needs no token/UI candidate or publication. UI-only tests use a durable, source-reviewed and cryptographically verified exact token baseline even after its historical CI artifact expires; selected tokens precede selected UI.
- Generate one logical release record from the reviewed source and retain it with the exact validated archives. Bind selected coordinates, compatibility baselines, policy, source commit, observed producer/application toolchains, actual filenames, byte lengths, SHA-512 values, and expected provenance. Before any publish command, durably retain and verify a separately bound attempt record for the actual publishing execution. Preserve immutable candidate fields when adding publication outcomes and later verifier identities; reconcile against the attempt if an outcome is never saved.
- Extend the existing `.github/workflows/Publish-frontend-packages.yml` with ordinary `prepare-only`, `publish`, and `verify` dispatches. Publication uses one `npm-publish` environment approval and direct npm Trusted Publishing/OIDC on GitHub-hosted runners; only the publishing job receives `id-token: write`. Neither preparation nor verification receives publishing credentials. No retired bootstrap/recovery mode returns.
- Make verification independently repeatable from a specifically selected retained candidate and attempt record. Reconcile exact versions, integrity, and provenance before any partial-publication continuation, including a successful npm publish whose final outcome was lost; retry registry reads only. Reject missing/expired *candidate or attempt* evidence or changed bytes instead of rebuilding or overwriting a published version. A verified, self-contained prior-dependency baseline does not depend on retaining its old candidate ZIP.
- Preserve token/UI/SDK archive validation, npm installed-tree signature auditing, Sigstore identity checks, clean consumers, browser smoke, production-host compatibility, offline/provisioning separation, and canonical-input CI selection. Maintainers review exact direct-publish trust settings; CI checks repository policy/context but does not inspect npm settings without credentials, and npm authorization failures stop without token fallback. Document fourth-package registration and its distinct initial-creation/trust gates.

This change plans repository implementation; it does not authorize actual publication, npm/GitHub configuration, package creation, FRED/RAGS adoption, or changes to historical first-release evidence. The [frontend packaging RFC](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md) remains the governing broader plan.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Modify the existing release-coordinate, candidate/evidence, toolchain, fixture-transfer, isolated-consumer, and registry-verifier requirements where first-release coordinates or three-candidate assumptions would contradict independent releases; add manifest-derived selection, a durable compatibility baseline, pre-publication attempt evidence, ordinary OIDC publication, and repeatable verification. The delta succeeds both the synchronized [main specification](../../specs/frontend-package-archives/spec.md) and the active [retirement change](../retire-frontend-bootstrap-recovery/specs/frontend-package-archives/spec.md); it must not reintroduce the active [first-release foundation change](../add-frontend-package-release-foundations/specs/frontend-package-archives/spec.md)'s obsolete incident operations.

## Impact

- Workflow and CI: `.github/workflows/Publish-frontend-packages.yml`, `.github/workflows/Check-pending-requests.yml`, `libs/frontend/scripts/package-inputs.mjs`, and workflow-selection tests. Preserve the existing workflow filename and its `swift` guard.
- Producer: member `package.json` files and changelogs, `libs/frontend/package-lock.json`, the release contract/schema and fixture equivalents, `libs/frontend/scripts/{release-contract,check-release-contract,release-candidate,release-evidence,fixture-transfer,fixture-transfer-validation,registry-verifier,dependency-boundaries,consumer-contract}.mjs`, packers/validators, `libs/frontend/package.json`, `Makefile`, and affected release/archive/consumer tests. Add only a compact package registration/policy input and shared publishing/release-record logic; do not copy package manifests or specialized validators.
- Documentation: `libs/frontend/RELEASE.md`, `libs/frontend/README.md`, and minimal RFC sequencing clarification during implementation; the historical evidence appendix stays immutable.
- Tracking: [#2630](https://github.com/ThalesGroup/fred/issues/2630) covers predecessor foundations, not routine independent publication. No matching new issue was found; propose one before implementation without creating it in this planning step. Predecessor task 12.7 stays unchecked until actual trust setup and token-revocation evidence exists.
