## ADDED Requirements

### Requirement: Release coordinates and metadata are explicit

The release-readiness process SHALL consume an explicitly selected contract for the
independently versioned design-token, UI, and iframe SDK packages. The contract MUST
state the expected package names, exact versions, dependency and peer ranges, release
metadata, and intended dist-tag; validation MUST compare candidate contents with that
contract rather than accepting metadata declared by an archive as its own expectation.

The producer workspace root MUST remain `private: true`, MUST NOT be a release
candidate, and MUST be distinguished from the publication eligibility and configuration
of each member package. Published member manifests MUST agree with the selected contract,
MUST contain no `workspace:`, `file:`, `link:`, directory, source-checkout, or other local
dependency reference, and MUST preserve the existing exports, asset, license, notice,
CSS, React-peer, and protocol contracts.

The private producer lockfile MAY contain npm-generated `link: true` entries only for the
exact members declared by the root workspace manifest. Each such entry MUST resolve to
its declared member directory within the producer workspace. The lockfile MUST reject an
undeclared linked package, a member-name mismatch, an escaping target, or any other link
that is not npm's representation of an explicitly declared producer member.

The `@fred` scope, the three current package names, version `0.1.0-alpha.1`, and the
`next` dist-tag SHALL remain proposed values until maintainers record confirmation of
scope ownership, final coordinates, registry policy, publishing owners, workflow
identity, and bootstrap authorization. Repository tooling MAY be implemented and tested
with explicit non-authoritative fixture coordinates before that confirmation, but it
MUST NOT represent such a test as an approved release candidate.

#### Scenario: A confirmed coordinate set is selected

- **WHEN** maintainers select confirmed names, independent exact versions, dependency
  ranges, release metadata, and an intended dist-tag
- **THEN** synchronized member manifests, peer requirements, and the producer lockfile
  match that external expected contract exactly

#### Scenario: The workspace root is inspected for release

- **WHEN** release readiness enumerates packable members
- **THEN** it excludes the private producer workspace root and evaluates each of the
  three member packages independently

#### Scenario: npm links the declared producer members

- **WHEN** the private producer lockfile represents each explicitly declared token, UI,
  and SDK member with `link: true` and a contained member-directory target
- **THEN** release validation accepts those expected workspace links while continuing to
  exclude the root from release

#### Scenario: A producer link is unexpected or escapes

- **WHEN** the producer lockfile links an undeclared package, resolves a declared member
  outside the producer workspace, or maps a package name to the wrong member directory
- **THEN** release validation fails and identifies the invalid link target

#### Scenario: A published manifest uses a local dependency

- **WHEN** a packed member manifest declares a `workspace:`, `file:`, `link:`, directory,
  checkout-source, or other local dependency reference
- **THEN** archive validation fails even if the producer workspace could resolve it

#### Scenario: An archive self-declares different metadata

- **WHEN** a candidate archive declares a name, version, dependency, export, license,
  repository field, or other required value that differs from the selected contract
- **THEN** validation fails even if the archive is internally self-consistent

#### Scenario: Coordinates have not been confirmed

- **WHEN** a command attempts to create approved release evidence while the selected
  scope, package names, versions, or bootstrap authorization remain provisional
- **THEN** it fails actionably and does not label the archives release candidates

#### Scenario: A fixture contract is relabelled without maintainer decisions

- **WHEN** a fixture contract's state is changed while it retains fixture approval
  identities, development versions or tag, or non-authoritative provenance identities
- **THEN** validation rejects it before packing and it cannot produce approved candidate
  evidence

### Requirement: Candidate archives and evidence are immutable

Release-candidate validation SHALL operate on the actual packed bytes for all three
packages and SHALL preserve every existing design-token, UI, iframe SDK, isolated
consumer, browser, and production-host compatibility guarantee. A successful candidate
record MUST bind the source commit, exact Node and npm versions, selected package
coordinates, archive filenames, and SHA-512 integrity values to those bytes. It MUST also
bind the expected provenance source repository, source commit, authorized publishing
workflow identity, and artifact digest used by later registry verification. These
expected values MUST come from the approved release contract and candidate evidence, not
from a downloaded provenance statement.

Any archive that is rebuilt, renamed in a way that changes its recorded identity,
modified, or replaced after validation MUST receive fresh archive, consumer, browser,
host-compatibility, and integrity evidence. A later publication step MUST use the exact
validated bytes; it MUST NOT rebuild packages and treat the prior evidence as valid.

#### Scenario: Three candidate archives pass validation

- **WHEN** the selected source commit produces token, UI, and SDK tarballs whose metadata
  and contents satisfy the expected release contract and all existing archive gates
- **THEN** evidence records the exact toolchain, coordinates, filenames, and SHA-512
  integrity for each tarball together with its expected repository, commit, authorized
  publishing workflow identity, and attested artifact digest

#### Scenario: Candidate bytes change after validation

- **WHEN** any candidate tarball is rebuilt or its bytes no longer match the recorded
  SHA-512 integrity
- **THEN** prior candidate evidence is rejected and the complete validation sequence
  must run again

#### Scenario: Publication input differs from candidate evidence

- **WHEN** a future publication operation receives archive bytes other than the bytes
  identified by the reviewed evidence
- **THEN** it must stop before registry mutation rather than publishing a rebuild

### Requirement: Release validation uses an exact producer toolchain

Candidate generation and release-evidence production SHALL require exact, non-floating
Node and npm versions recorded in the release contract. The initial recommended pin is
Node `24.21.0` with npm `11.19.0`, which satisfies the currently documented minimums for
npm Trusted Publishing and staged publishing; changing either pin MUST be a reviewed
contract change with renewed validation.

FRED application tests that participate in compatibility validation MUST remain under
their separately controlled application toolchain. Release evidence MUST record exact
Node and npm versions for that application-test environment. Release orchestration MUST identify
which toolchain produced each item of evidence and MUST pass immutable candidate
archives between producer and application-test environments rather than resolving the
producer's installed dependencies from the application environment.

#### Scenario: Candidate production uses the pinned versions

- **WHEN** a release-candidate command starts with Node or npm different from the exact
  selected versions
- **THEN** it fails actionably before packing or recording candidate evidence

#### Scenario: Application compatibility runs on its own tooling

- **WHEN** CI executes FRED application regression or production-host compatibility
  checks against candidate archives
- **THEN** the application uses its independently pinned tooling and receives the exact
  candidate bytes without using the producer dependency tree

#### Scenario: The toolchain pin changes

- **WHEN** maintainers select a different exact Node or npm version
- **THEN** all three archives and their release evidence are regenerated and revalidated

### Requirement: Candidate versions work in isolated consumers

The existing neutral token, React UI, and framework-independent iframe SDK consumers
SHALL accept the exact selected candidate coordinates and install the actual candidate
archives in fresh locations outside the FRED checkout. Provisioning MAY populate only
the lockfile-pinned caches and browser prerequisites declared for those selected
coordinates. Offline validation MUST retain source isolation, production builds,
browser checks, and SDK production-host compatibility without network access, directory
dependencies, workspace links, local source fallback, or resolution from FRED's installed
dependency tree.

Disposable offline consumer manifests and lockfiles MAY contain npm-generated `file:`
references to the exact staged candidate `.tgz` files. Each permitted reference MUST
map by package identity to an approved candidate evidence record, identify a regular
non-symlink tarball file whose real path remains inside the disposable consumer, and match
the recorded archive filename, bytes, and lock integrity. Validation MUST inspect all
applicable root and nested manifest/lock dependency fields and local lock resolutions before
dependency installation; a matching archive basename alone MUST NOT authorize a reference.
Permitted generated `file:` references MUST use unencoded, unambiguous relative paths; percent
encoding, query strings, fragments, and backslashes MUST be rejected so validation and npm
cannot resolve different targets.
No directory target, unexpected or additional local file, checkout path, unmatched nested
dependency, symlinked package, or reused FRED dependency tree is permitted.
Production-host integration MUST run the host with dependencies installed from the FRED
application's own lockfile while loading the SDK under test only from its verified archive
or exact registry installation.

#### Scenario: Candidate archives replace development versions

- **WHEN** isolated consumers are configured with the selected token, UI, and SDK
  candidate coordinates and matching lockfiles
- **THEN** offline installation, type checking, production builds, browser smoke, and
  host compatibility pass with the actual candidate tarballs

#### Scenario: npm records a verified candidate tarball

- **WHEN** disposable offline installation records a `file:` dependency or lockfile
  resolution for a staged candidate `.tgz` whose bytes match the recorded SHA-512
- **THEN** validation accepts that archive reference and installs the packed package

#### Scenario: A local reference targets a directory or different file

- **WHEN** a disposable consumer reference resolves to a directory, workspace member,
  symlink, checkout path, or local file other than the integrity-verified staged tarball
- **THEN** isolated-consumer validation fails before building

#### Scenario: An additional lock entry reuses an approved filename

- **WHEN** a root or nested lock entry names an unapproved package, escapes the consumer, or
  resolves different bytes under the same basename as an approved candidate archive
- **THEN** isolated-consumer validation fails before `npm ci` despite the filename match

#### Scenario: A nested local dependency lacks matching evidence

- **WHEN** any dependency-reference field or local lock resolution identifies a package,
  archive real path, version, or integrity value that does not match its approved evidence
- **THEN** isolated-consumer validation rejects the complete graph before dependencies are used

#### Scenario: A file reference encodes a different path

- **WHEN** a local tarball reference uses encoded traversal or separators, a query, a fragment,
  or a backslash that npm could interpret differently from a literal filesystem check
- **THEN** isolated-consumer validation rejects the ambiguous reference before dependency use

#### Scenario: A consumer resolves a development or workspace package

- **WHEN** a candidate consumer graph contains `0.0.0-development`, a workspace link, a
  directory dependency, an unverified local file dependency, or a package resolved from
  the FRED checkout or its installed dependency tree
- **THEN** release-candidate validation fails

#### Scenario: Production host compatibility uses the packed SDK

- **WHEN** the production-host integration gate exercises an SDK candidate
- **THEN** the host test runner and application modules resolve from the FRED application's
  own lockfile installation while the SDK entry resolves from the integrity-verified
  candidate archive, not the producer workspace

#### Scenario: Candidate provisioning is incomplete

- **WHEN** an exact dependency or browser prerequisite is absent from the prepared cache
- **THEN** offline validation fails actionably without fetching or installing it

### Requirement: Registry verification is exact and cannot fall back locally

The repository SHALL provide a registry-verification command that accepts the exact
expected coordinate and previously recorded archive SHA-512 integrity for each FRED
package. Against a real public registry, it MUST resolve those exact versions, verify
registry-reported and downloaded-byte integrity, cryptographically verify provenance for
each package, and exercise fresh clean consumers installed from the registry.

Cryptographic signature validity alone MUST NOT establish a matching release. Cryptographic
verification MUST require the signing certificate identity to equal the explicitly authorized
GitHub workflow URI and its issuer to equal the explicitly expected GitHub Actions OIDC issuer.
For every package, verification MUST then independently compare the attested artifact digest,
source repository,
source commit, and publishing workflow identity with the explicit expected values bound
to the approved release contract and candidate evidence. It MUST NOT accept values merely
because they appear in a validly signed downloaded attestation. The expected bootstrap
identity and the later authorized Trusted Publishing workflow identity MUST remain
distinct and explicit; an unconfirmed identity MUST fail closed as a maintainer decision.

The command MUST reject tags, ranges, unexpected registries, missing provenance,
integrity mismatches, local tarballs, workspace packages, source-checkout resolution,
and silent fallback. Its local automated tests MUST use controlled registry fixtures or
equivalent deterministic responses and MUST label their result as tooling validation,
not as proof that packages were genuinely published.

The command MUST discover the attestation document from npm's raw
`dist.attestations.url` version-metadata field, MUST validate that it is an allowed npm
attestation endpoint for the exact expected coordinate, and MUST re-root its pathname onto
the explicitly approved registry before fetching. It MUST reject a missing, malformed,
credential-bearing, non-HTTP(S), fragment-bearing, endpoint-mismatched, or
coordinate-mismatched URL. The sibling provenance predicate metadata MUST NOT be treated as
the endpoint location.

#### Scenario: Published candidates match recorded evidence

- **WHEN** the command is given the three exact published coordinates and their recorded
  integrity values and the public registry serves matching packages with provenance
- **THEN** clean registry-only token, UI, and SDK consumers pass their applicable build,
  browser, and compatibility checks

#### Scenario: npm metadata provides the attestation endpoint

- **WHEN** exact-version metadata supplies a valid `dist.attestations.url` for the selected
  coordinate
- **THEN** the verifier fetches that endpoint only through the approved registry and performs
  the required cryptographic and expected-release identity checks

#### Scenario: The attestation endpoint metadata is invalid

- **WHEN** `dist.attestations.url` is absent, malformed, disallowed, or names a different
  package coordinate or endpoint
- **THEN** registry verification fails before accepting or fetching provenance

#### Scenario: Valid provenance names an unexpected repository

- **WHEN** a provenance statement is cryptographically valid but its source repository
  differs from the repository expected by the approved contract and candidate evidence
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected commit

- **WHEN** a provenance statement is cryptographically valid but its source commit differs
  from the candidate source commit recorded as expected
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected workflow

- **WHEN** a provenance statement is cryptographically valid but its publishing workflow
  identity differs from the explicitly authorized Trusted Publishing identity
- **THEN** registry verification fails the release-identity comparison

#### Scenario: A valid Sigstore bundle has an unauthorized signer identity

- **WHEN** a provenance bundle is cryptographically valid but its signing certificate URI
  or issuer differs from the expected Trusted Publishing workflow certificate policy
- **THEN** registry verification fails before accepting statement identity claims

#### Scenario: Valid provenance names an unexpected artifact digest

- **WHEN** a provenance statement is cryptographically valid but its attested artifact
  digest differs from the expected digest of the candidate tarball
- **THEN** registry verification fails even if registry metadata reports another
  internally consistent integrity value

#### Scenario: Registry content does not match the candidate

- **WHEN** registry metadata, downloaded bytes, or provenance is missing or differs from
  the expected coordinate and integrity
- **THEN** verification fails and does not substitute a local archive or source tree

#### Scenario: A registry consumer attempts local fallback

- **WHEN** a registry-installed consumer resolves a FRED package from a tag, range, local
  tarball, directory, workspace, checkout source, or reused FRED dependency tree instead
  of the expected exact registry version
- **THEN** verification fails rather than accepting the consumer result

#### Scenario: Only verifier tooling was tested locally

- **WHEN** the verifier passes against controlled local fixtures without genuinely
  published package coordinates
- **THEN** evidence reports only that verifier behavior passed and does not report a
  successful public-registry release verification

### Requirement: Bootstrap, publication, and adoption remain separate gates

Release documentation SHALL distinguish repository readiness, initial npm package
creation, later Trusted Publishing configuration, optional staged-publishing policy,
actual publication, registry verification, FRED adoption, and external adoption.
Initial creation MUST require confirmed scope ownership and an account or organization
permission model capable of creating each package; it MUST NOT assume that a
package-scoped credential can create a nonexistent package. Staged publishing MUST be
documented as a maintainer policy choice and MUST NOT be used for brand-new package
creation. The bootstrap actor or credential identity and the later Trusted Publishing
workflow identity MUST be recorded separately. Neither identity may be inferred from the
other, and an unconfirmed identity remains a maintainer gate.

Dependencies SHALL be released before consumers: a compatible design-token version
before its UI consumer, while the independent SDK may be sequenced separately. FRED
adoption SHALL occur only after the required prereleases pass genuine registry
verification. If later protocol-ownership transfer changes SDK bytes, the corresponding
SDK version MUST be built, validated, and published before FRED adopts it. RAGS adoption
remains separately tracked and MUST use the same generic contract as any external
application.

Published versions MUST be treated as immutable. Recovery SHALL select a previously
validated version or publish a newly versioned correction; it MUST NOT overwrite a
published version. Adoption rollback SHALL restore a prior lockfile/dependency set or
redeploy a prior application image.

#### Scenario: Maintainers bootstrap a new public package

- **WHEN** one of the selected package names does not yet exist in the approved npm scope
- **THEN** maintainers verify organization ownership and package-creation authority and
  record the authorized bootstrap identity before using the approved bootstrap process
  and separately configuring the later Trusted Publishing workflow identity

#### Scenario: Maintainers choose staged publishing

- **WHEN** staged publishing is selected as release policy
- **THEN** it is used only after the package exists and the required npm, Node, access,
  and two-factor approval prerequisites are satisfied

#### Scenario: FRED adoption is proposed

- **WHEN** maintainers prepare a later change to consume registry packages in FRED
- **THEN** the required prereleases already have matching integrity, provenance, and
  clean-consumer registry evidence, and any changed SDK artifact is released first

#### Scenario: A released candidate must be rolled back

- **WHEN** a defect is found after publication or adoption
- **THEN** maintainers deprecate or supersede the affected version and restore a prior
  validated dependency set or image without replacing published bytes

## MODIFIED Requirements

### Requirement: CI selection covers every package-validation input

Pull-request validation SHALL select the frontend-package job when the producer
workspace; a consumed canonical component, type, stylesheet, protocol source, or path
validator; the FRED frontend React manifest or lockfile baseline; a packaged Geist or
Material Symbols asset; an applicable license or notice input; an SDK compatibility or
isolated-consumer fixture; or relevant validation orchestration changes. Release
readiness validation SHALL also be selected when a release coordinate contract,
candidate metadata, exact producer-toolchain pin, release-evidence schema, registry
verifier, release runbook, or release-specific orchestration changes. It MAY skip that
job for application changes that affect neither package generation nor package/host
compatibility or release validation. Existing frontend selection MUST continue to run
the FRED host, request, path, and proxy regressions when their application inputs change.

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

- **WHEN** a pull request changes selected release coordinates, package metadata,
  dependency ranges, a toolchain pin, candidate evidence or registry-verification logic,
  release documentation, or the workflow that validates them
- **THEN** CI selects the frontend-package release-readiness and applicable existing
  archive regression jobs

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
