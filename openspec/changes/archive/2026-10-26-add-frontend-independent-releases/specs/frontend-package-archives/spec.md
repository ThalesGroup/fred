## ADDED Requirements

### Requirement: Portable release identity is manifest-derived

The release interface SHALL accept exactly one stable package selector: `design-tokens`, `ui`, or `iframe-sdk`. It SHALL read the npm name and independently maintained version from that member's committed manifest and MUST exclude the private producer workspace root.

Preparation SHALL create a portable release directory containing exactly one validated tarball and automatically generated metadata that binds the selector, npm name, version, source commit, archive filename, and SHA-512 integrity. Operators MUST NOT construct JSON, supply hashes, or duplicate manifest coordinates. A default versioned output path SHALL be provided and an explicit release directory SHALL be supported for environment transfer.

#### Scenario: One package is prepared

- **WHEN** an operator prepares a supported package from a clean committed checkout
- **THEN** the package manifest supplies its name and version and the release directory contains its exact tarball plus generated commit and integrity metadata

#### Scenario: Package input is invalid

- **WHEN** the selector is empty, unknown, duplicated, or identifies the private workspace root
- **THEN** preparation fails before a build, pack, registry, or publication operation

#### Scenario: A transferred directory is selected

- **WHEN** an operator supplies an explicit release directory to publication or verification
- **THEN** the operation resolves and validates its generated metadata and archive without requiring GitHub APIs or manually entered identity fields

### Requirement: Prepared release bytes are immutable

Preparation SHALL build only the selected member and run its applicable archive and isolated-consumer checks, including browser or host checks where required by that package contract. The prepared archive SHALL remain byte-identical through publication and verification. Every consuming operation MUST reject missing, additional, escaping, inconsistent, or altered release files before registry mutation.

Publication MUST upload the exact prepared tarball, MUST NOT rebuild or silently prepare another archive, and MUST disable package lifecycle scripts. A dry run MUST validate the same release identity, bytes, dependency state, and registry preflight while invoking no publish or distribution-tag mutation.

#### Scenario: Prepared bytes are reused

- **WHEN** publication receives a valid transferred release directory
- **THEN** it passes the recorded tarball path directly to npm with lifecycle scripts disabled and does not invoke a builder or packer

#### Scenario: Prepared output changes

- **WHEN** the tarball checksum, manifest identity, version, filename, or metadata differs from the prepared release
- **THEN** publication and verification stop before any registry mutation

#### Scenario: Publication is dry-run

- **WHEN** the operator requests a publication dry run
- **THEN** local validation and read-only preflight complete but no package upload or tag change command is invoked

### Requirement: Registry comparison is exact and retry-safe

Publication and verification SHALL query the configured registry for the exact prepared name and version and compare registry SHA-512 integrity with the prepared archive. An existing matching version SHALL be reported as success without upload. An existing version with different bytes SHALL be a conflict. Only a definite exact-version absence MAY authorize one publication attempt.

Registry handling MUST distinguish absence from authentication, authorization, network, timeout, redirect, malformed-response, identity, and integrity failures. After an accepted publication, bounded read-only exact-version checks MAY wait for visibility. Exhausted temporary absence or an upload whose result cannot be established MUST produce an uncertain outcome and the exact verification instruction; it MUST NOT repeat publication automatically.

Verification MUST use registry bytes and metadata and MUST NOT substitute a local rebuild, source tree, mutable tag, or unrelated version for the prepared identity.

#### Scenario: Exact version already matches

- **WHEN** registry metadata for the prepared name and version reports the same SHA-512 integrity
- **THEN** publish and verify report success and no upload command runs

#### Scenario: Exact version conflicts

- **WHEN** the registry contains the prepared name and version with different integrity
- **THEN** the operation stops with a conflict and does not overwrite or republish the version

#### Scenario: Visibility is delayed

- **WHEN** npm accepts one upload and exact-version reads return temporary 404 responses before returning matching metadata
- **THEN** bounded read-only checks report success without a second upload

#### Scenario: Upload outcome is uncertain

- **WHEN** the upload fails ambiguously or bounded visibility checks cannot establish the exact matching version
- **THEN** the operation records an uncertain result, prints the exact read-only verification command, and performs no automatic retry

#### Scenario: Registry access is unauthorized

- **WHEN** an exact-version read returns an authentication or authorization failure
- **THEN** the operation reports that class of failure and does not treat it as package absence

### Requirement: Shared commands drive local and CI releases

`libs/frontend` SHALL expose `make prepare-release`, `make publish`, `make verify-release`, and `make promote` with one `PACKAGE` per operation. The same implementation SHALL run locally and in CI without depending on GitHub APIs. Publish SHALL default to the `next` distribution tag; promotion SHALL require an explicit existing version and channel and remain separate from publication.

Local authentication SHALL use normal npm login and interactive authorization without claiming CI provenance. CI token and GitHub OIDC authentication SHALL be explicit, MUST NOT fall back to another mode, and GitHub OIDC publication SHALL request provenance only for bytes prepared from the workflow's committed source. Promotion and publication dry runs MUST perform no registry mutation.

#### Scenario: Local operator publishes prepared output

- **WHEN** an authenticated local operator runs publish for a valid release directory
- **THEN** the shared implementation uses the operator's npm configuration, publishes to `next` without CI provenance, and never calls GitHub APIs

#### Scenario: GitHub CI publishes prepared output

- **WHEN** the protected GitHub publication job invokes the same Make target in explicit OIDC mode
- **THEN** only that job receives `id-token: write`, provenance describes its committed source truthfully, and no local or token fallback is attempted

#### Scenario: Promotion targets an existing version

- **WHEN** an operator requests a channel change for an exact version that exists
- **THEN** the shared command updates only that distribution tag and does not rebuild or publish a package

#### Scenario: Promotion target is absent

- **WHEN** the requested exact version is absent or registry verification fails
- **THEN** promotion stops before any distribution-tag command

### Requirement: Package dependency order is enforced without coupling independent releases

UI preparation and publication SHALL validate its declared `@fred-oss/design-tokens` peer range against an exact compatible published design-token version. If none is available, the operation MUST direct the operator to publish a compatible design-token version first. The iframe SDK SHALL remain independent and MUST NOT require UI or design-token preparation, publication, or registry availability.

#### Scenario: UI has a compatible published token

- **WHEN** at least one exact published design-token version satisfies UI's declared peer range
- **THEN** UI preparation and publication may continue without publishing tokens in the same operation

#### Scenario: UI has no compatible published token

- **WHEN** no exact published design-token version satisfies UI's peer range
- **THEN** the UI operation stops and identifies design tokens as the prerequisite package

#### Scenario: iframe SDK is selected

- **WHEN** an operator prepares, publishes, verifies, or promotes iframe-sdk
- **THEN** no UI or design-token build, consumer, publication, or dependency lookup is required

### Requirement: The GitHub workflow is a thin release adapter

The existing publication workflow filename SHALL be preserved and expose simple operation and package inputs. It SHALL invoke the shared Make commands, retain GitHub-specific artifact upload/download and an optional explicit run selector in the adapter, preserve the `npm-publish` approval boundary, restrict mutation credentials and `id-token: write` to mutation jobs, and serialize publication per package.

The workflow MUST NOT require manual candidate, attempt, terminal, hash, or JSON inputs; enumerate repository-wide artifact history; dispatch another workflow; or implement a second publication/recovery engine. Verification and preparation jobs MUST remain read-only with respect to npm.

#### Scenario: Preparation and publication use separate runs

- **WHEN** CI publishes a release directory prepared by an earlier workflow run
- **THEN** the adapter resolves the selected package artifact from the explicit run selector, downloads it, and invokes the same publish Make target without exposing artifact mechanics to the shared implementation

#### Scenario: Publication requires approval and serialization

- **WHEN** two GitHub publication jobs target the same package
- **THEN** the protected environment remains the authorization boundary and the workflow concurrency key serializes those mutations by package

#### Scenario: CI provider changes

- **WHEN** another CI system transfers the same prepared release directory
- **THEN** it can invoke the shared Make targets without GitHub workflow IDs, artifact APIs, or a separate release implementation

## MODIFIED Requirements

### Requirement: CI selection covers every package-validation input

Pull-request validation SHALL select the frontend-package job when the producer
workspace; a consumed canonical component, type, stylesheet, protocol source, or path
validator; the FRED frontend React manifest or lockfile baseline; a packaged Geist or
Material Symbols asset; an applicable license or notice input; an SDK compatibility or
isolated-consumer fixture; or relevant validation orchestration changes. Release
readiness validation SHALL also be selected when package manifest metadata, the portable
release-directory contract, an exact producer-toolchain pin, release-evidence schema,
registry verifier, fixture-transfer helper or metadata, a shared release command, the
release runbook, the thin publication workflow, the governing frontend packaging RFC,
or release-specific orchestration changes. It MAY skip that job for application changes
that affect neither package generation nor package/host compatibility or release
validation. Existing frontend selection MUST continue to run the FRED host, request,
path, and proxy regressions when their application inputs change. Every selected job
that executes isolated-consumer validation MUST provision its own exact consumer
prerequisites in a distinct network-capable step before offline tests begin; it MUST NOT
depend on another job's filesystem or introduce network fallback into validation.

#### Scenario: Release readiness provisions its isolated consumers

- **WHEN** the release-readiness job installs producer dependencies and will subsequently run
  consumer-dependent package tests
- **THEN** it provisions the isolated-consumer caches in that job before those tests, after which
  archive installation and validation remain offline

#### Scenario: Fixture transfer inputs change

- **WHEN** a pull request changes fixture-transfer production, verification, evidence,
  workflow-artifact orchestration, or a downstream transferred-archive gate
- **THEN** CI selects both the release-toolchain producer and its application-toolchain receiver
  while unrelated application-only changes retain their existing selection behavior

#### Scenario: The producer workspace changes

- **WHEN** a pull request changes a file in the frontend package producer workspace
- **THEN** CI selects the frontend-package validation job

#### Scenario: Consumed canonical CSS changes

- **WHEN** a pull request changes a canonical FRED stylesheet consumed by token, font,
  shared-base, or component-style generation
- **THEN** CI selects the frontend-package validation job

#### Scenario: A consumed component or type changes

- **WHEN** a pull request changes a canonical component, shared prop or visual type, or
  Sass support file in the UI package allowlist
- **THEN** CI selects the frontend-package validation job

#### Scenario: A canonical protocol or path rule changes

- **WHEN** a pull request changes the maintained protocol source or relative-path rules
  consumed by the SDK and host compatibility checks
- **THEN** CI selects both frontend-package validation and the applicable FRED frontend
  regression checks

#### Scenario: A host compatibility input changes

- **WHEN** a pull request changes the application host page, request adapter, frame/path
  integration, or their compatibility tests
- **THEN** CI selects the FRED frontend regression checks and every declared SDK/host
  compatibility gate affected by that input

#### Scenario: The tested React baseline changes

- **WHEN** a pull request changes the FRED frontend manifest or lockfile entries that
  establish the UI package's tested React or React DOM baseline
- **THEN** CI selects the frontend-package validation job

#### Scenario: A packaged Geist asset changes

- **WHEN** a pull request changes either canonical Geist font binary packaged by the
  design-token member
- **THEN** CI selects the frontend-package validation job

#### Scenario: The packaged Material Symbols asset changes

- **WHEN** a pull request changes the canonical Material Symbols Outlined binary used by
  the UI member
- **THEN** CI selects the frontend-package validation job

#### Scenario: An applicable license input changes

- **WHEN** a pull request changes a license, provenance record, glyph inventory, or
  notice input applicable to a generated archive
- **THEN** CI selects the frontend-package validation job

#### Scenario: Release readiness input changes

- **WHEN** a pull request changes package manifest metadata, dependency ranges, a
  toolchain pin, portable release identity or registry-verification logic, release
  documentation, or the workflow that validates them
- **THEN** CI selects the frontend-package release-readiness and applicable existing
  archive regression jobs

#### Scenario: Shared release workflow input changes

- **WHEN** a pull request changes a shared release command, the thin publication workflow,
  selected manifest metadata, or their workflow-contract tests
- **THEN** CI selects release readiness and the existing archive, consumer, and compatibility
  regressions without exposing a publication credential to those jobs

#### Scenario: Validation orchestration changes

- **WHEN** a pull request changes a root command, workflow, setup action, build
  configuration, fixture lockfile, or validation script that controls the
  frontend-package or host-compatibility gates
- **THEN** CI selects the affected validation jobs

#### Scenario: An unrelated application file changes

- **WHEN** a pull request changes only application files that are not consumed by or
  responsible for frontend-package, SDK/host compatibility, or release validation
- **THEN** CI may skip the frontend-package job while retaining normal application
  validation

## REMOVED Requirements

### Requirement: Release coordinates and metadata are explicit

**Reason**: The contract duplicates package coordinates, ownership, initial-release identities, and three-package assumptions that no longer describe independent routine releases.

**Migration**: Read name, version, dependencies, and package metadata from the selected member manifest and generate the portable release identity automatically.

### Requirement: Candidate archives and evidence are immutable

**Reason**: The existing candidate-evidence requirement assumes a three-package GitHub artifact and provenance record rather than one transferable package directory.

**Migration**: Preserve immutability through the selected tarball and generated `release.json`; publish and verify those exact bytes without rebuilding.

### Requirement: Registry verification is exact and cannot fall back locally

**Reason**: The existing verifier is coupled to retained GitHub candidates, attempts, historical publishing identities, Sigstore outcome reconstruction, and full registry-consumer orchestration.

**Migration**: Compare the prepared exact coordinate and SHA-512 directly with bounded registry reads. Keep package/archive/consumer validation in preparation and pull-request CI.

### Requirement: Bootstrap, publication, and adoption remain separate gates

**Reason**: The requirement embeds the completed first-release incident, bootstrap token, retained candidate ZIP, attempt/terminal history, recovery, and `verify-existing` orchestration into routine publication. Issue #3281 replaces that GitHub-specific recovery engine with one-package portable release directories and shared commands.

**Migration**: Use the shared prepare, publish, verify, and promote Make targets. Keep npm publication distinct from product adoption and treat published versions as immutable, but do not carry forward the incident artifact-history protocol.
