## MODIFIED Requirements

### Requirement: Bootstrap, publication, and adoption remain separate gates

Release documentation SHALL distinguish repository readiness, the completed initial npm package creation and partial recovery, subsequent Trusted Publishing configuration, actual publication, registry verification, FRED adoption, and external adoption. The confirmed scope, package-creation authority, bootstrap actor, and historical publishing workflow identity MUST remain traceable in durable historical evidence; a later Trusted Publishing identity MUST be recorded separately and MUST NOT be inferred from that bootstrap identity. Unconfirmed later trust or credential-revocation evidence MUST remain an explicit maintainer gate rather than be inferred from a successful registry-verification run. The selected policy for subsequent FRED frontend releases remains direct Trusted Publishing with GitHub environment approval, but enabling routine publication is outside this cleanup.

The existing `workflow_dispatch` workflow at `.github/workflows/Publish-frontend-packages.yml` SHALL reject refs other than `swift` and, during this interim cleanup slice, SHALL offer preparation only. It MUST build and validate candidate archives under the release toolchain, transfer that exact immutable set for separately provisioned application-toolchain compatibility validation, and MUST NOT rebuild or re-baseline candidate bytes during transfer. Its dispatch, authorization, preparation, and compatibility paths MUST NOT schedule registry mutation or historical retained-artifact verification, grant `id-token: write`, receive `NPM_BOOTSTRAP_TOKEN` or other publishing credentials, or require the `npm-publish` environment. The operator path MUST NOT offer `publish-bootstrap`, `recover-bootstrap`, or `verify-existing` choices.

Active release-contract checking, producer inputs, commands, and generic verifier loading MUST NOT require the completed bootstrap-recovery or registry-verification-continuation configuration. The two incident configuration files SHALL be absent from the active source tree, and no live workflow, script, command, test loader, or package input selection SHALL read them or silently recreate equivalent active configuration. Retired recovery/continuation CLI options MUST fail with an actionable unsupported-option error; they MUST NOT be ignored while a weaker generic check runs. The generic registry verifier MUST retain exact coordinate and archive-integrity comparison, installed-tree and dependency-boundary checks, npm signature auditing, Sigstore certificate and independent provenance-identity matching, bounded read-only registry-visibility handling, and clean consumer/browser/host gates when invoked for a future authorized verification. Controlled tests MUST NOT claim public-registry success unless the genuine registry gates complete.

Dependencies SHALL be released before consumers: a compatible design-token version before its UI consumer, while the independent SDK may be sequenced separately in a later publication change. FRED adoption SHALL occur only after required prereleases pass genuine registry verification. If later protocol-ownership transfer changes SDK bytes, its corresponding version MUST be built, validated, and published before FRED adopts it. RAGS adoption remains separately tracked under the generic contract. Published versions MUST remain immutable; a future correction SHALL use a newly versioned candidate rather than overwrite an existing version. Adoption rollback SHALL restore a prior validated dependency set or application image.

The completed first-release source, candidate, publication, recovery, and successful verification identities and recorded SHA-512 integrities SHALL remain available as a compact historical record. Deleting active incident configuration MUST NOT alter historical evidence, package versions, registry state, or attestations. The record MUST identify historical publication identities separately from the later verification execution and link to retained original artifacts while available; artifact expiry MUST NOT be concealed by treating source history as a replacement for archive bytes.

#### Scenario: Preparation remains runnable without publication

- **WHEN** a maintainer dispatches the existing workflow on `swift` with its default preparation input
- **THEN** candidate production, immutable transfer, and application compatibility validation run under their respective toolchains without publication approval, registry mutation, a bootstrap token, or OIDC write permission

#### Scenario: A retired dispatch operation is requested

- **WHEN** a caller requests `publish-bootstrap`, `recover-bootstrap`, or `verify-existing` from the cleanup workflow
- **THEN** the input is unavailable or rejected, and no candidate publication or historical-verification job is scheduled

#### Scenario: An incident configuration file is removed

- **WHEN** either completed bootstrap-recovery or registry-verification-continuation JSON file is absent
- **THEN** preparation, release-contract checking, CI input selection, and a fresh-process generic verifier load continue without reading or recreating that file

#### Scenario: A retired verifier option is passed

- **WHEN** the generic registry-verifier CLI receives a recovery-plan, recovery-evidence, recovery-artifact, verification-plan, or verification-inputs option
- **THEN** it exits nonzero with an actionable unsupported-option error before reporting successful verification

#### Scenario: Generic registry verification is still authorized

- **WHEN** a future authorized caller supplies exact approved coordinates, candidate integrity, and independent expected publication identities through the supported generic verifier interface
- **THEN** the verifier retains exact registry resolution, installed dependency-tree signature audit, cryptographic provenance matching, and clean consumers without checkout, workspace, or local-tarball fallback

#### Scenario: Temporary registry visibility differs between endpoints

- **WHEN** approved exact-version metadata is visible but package-wide metadata returns a temporary 404
- **THEN** bounded read-only readiness checks may proceed to matching metadata without repeating any publication command, while malformed, unauthorized, or integrity-mismatched data fails

#### Scenario: Historical release evidence is consulted after cleanup

- **WHEN** a maintainer reviews the initial and partial publication and the later successful registry verification
- **THEN** the original candidate and publishing commits/runs, each package's recorded integrity and provenance expectations, and the separate verifier commit/run remain traceable without an active incident configuration file

#### Scenario: Later publishing trust is not evidenced

- **WHEN** registry verification succeeds but Trusted Publisher configuration or bootstrap-token revocation remains unconfirmed
- **THEN** the maintainer gate remains explicit and the cleanup does not claim those actions completed or enable routine publication

#### Scenario: FRED adoption is proposed

- **WHEN** maintainers prepare a later change to consume registry packages in FRED
- **THEN** required prereleases have matching integrity, provenance, and clean-consumer evidence, and any changed SDK artifact is released first

#### Scenario: A released candidate must be rolled back

- **WHEN** a defect is found after publication or adoption
- **THEN** maintainers supersede the affected version and restore a prior validated dependency set or image without replacing published bytes

### Requirement: CI selection covers every package-validation input

Pull-request validation SHALL select the frontend-package job when the producer workspace; a consumed canonical component, type, stylesheet, protocol source, or path validator; the FRED frontend React manifest or lockfile baseline; a packaged Geist or Material Symbols asset; an applicable license or notice input; an SDK compatibility or isolated-consumer fixture; or relevant validation orchestration changes. Release readiness validation SHALL also be selected when a release coordinate contract, candidate metadata, exact producer-toolchain pin, release-evidence schema, generic registry verifier, fixture-transfer helper or metadata, release runbook, retained workflow, governing frontend packaging RFC, or release-specific orchestration changes. It MUST NOT depend on the deleted incident configuration or select obsolete bootstrap/recovery/continuation scripts as active release inputs. It MAY skip that job for application changes that affect neither package generation nor package/host compatibility or release validation. Existing frontend selection MUST continue to run the FRED host, request, path, and proxy regressions when their application inputs change. Every selected job that executes isolated-consumer validation MUST provision its own exact consumer prerequisites in a distinct network-capable step before offline tests begin; it MUST NOT depend on another job's filesystem or introduce network fallback into validation.

#### Scenario: Release readiness provisions its isolated consumers

- **WHEN** the release-readiness job installs producer dependencies and will subsequently run consumer-dependent package tests
- **THEN** it provisions the isolated-consumer caches in that job before those tests, after which archive installation and validation remain offline

#### Scenario: Fixture transfer inputs change

- **WHEN** a pull request changes fixture-transfer production, verification, evidence, workflow-artifact orchestration, or a downstream transferred-archive gate
- **THEN** CI selects both the release-toolchain producer and its application-toolchain receiver while unrelated application-only changes retain their existing selection behavior

#### Scenario: The producer workspace changes

- **WHEN** a pull request changes a file in the frontend package producer workspace
- **THEN** CI selects the frontend-package validation job

#### Scenario: Consumed canonical CSS changes

- **WHEN** a pull request changes a canonical FRED stylesheet consumed by token, font, shared-base, or component-style generation
- **THEN** CI selects the frontend-package validation job

#### Scenario: A consumed component or type changes

- **WHEN** a pull request changes a canonical component, shared prop or visual type, or Sass support file in the UI package allowlist
- **THEN** CI selects the frontend-package validation job

#### Scenario: A canonical protocol or path rule changes

- **WHEN** a pull request changes the maintained protocol source or relative-path rules consumed by the SDK and host compatibility checks
- **THEN** CI selects both frontend-package validation and the applicable FRED frontend regression checks

#### Scenario: A host compatibility input changes

- **WHEN** a pull request changes the application host page, request adapter, frame/path integration, or their compatibility tests
- **THEN** CI selects the FRED frontend regression checks and every declared SDK/host compatibility gate affected by that input

#### Scenario: The tested React baseline changes

- **WHEN** a pull request changes the FRED frontend manifest or lockfile entries that establish the UI package's tested React or React DOM baseline
- **THEN** CI selects the frontend-package validation job

#### Scenario: A packaged Geist asset changes

- **WHEN** a pull request changes either canonical Geist font binary packaged by the design-token member
- **THEN** CI selects the frontend-package validation job

#### Scenario: The packaged Material Symbols asset changes

- **WHEN** a pull request changes the canonical Material Symbols Outlined binary used by the UI member
- **THEN** CI selects the frontend-package validation job

#### Scenario: An applicable license input changes

- **WHEN** a pull request changes a license, provenance record, glyph inventory, or notice input applicable to a generated archive
- **THEN** CI selects the frontend-package validation job

#### Scenario: Release readiness input changes

- **WHEN** a pull request changes selected release coordinates, package metadata, dependency ranges, a toolchain pin, candidate evidence or generic registry-verification logic, release documentation, or the preparation-only workflow
- **THEN** CI selects frontend-package release readiness and applicable existing archive regression jobs

#### Scenario: Retired incident input is removed

- **WHEN** a pull request deletes first-release recovery or verification-continuation configuration and its live readers
- **THEN** CI still selects the affected release and archive regression jobs for that deletion, but subsequent runs do not require the deleted files as inputs

#### Scenario: Preparation-workflow input changes

- **WHEN** a pull request changes the retained preparation workflow, release transfer/evidence logic, selected manifest metadata, or its workflow-contract tests
- **THEN** CI selects release readiness and existing archive, consumer, and compatibility regressions without exposing a publication credential to those jobs

#### Scenario: Validation orchestration changes

- **WHEN** a pull request changes a root command, workflow, setup action, build configuration, fixture lockfile, or validation script that controls frontend-package or host-compatibility gates
- **THEN** CI selects the affected validation jobs

#### Scenario: An unrelated application file changes

- **WHEN** a pull request changes only application files that are not consumed by or responsible for frontend-package, SDK/host compatibility, or release validation
- **THEN** CI may skip the frontend-package job while retaining normal application validation
