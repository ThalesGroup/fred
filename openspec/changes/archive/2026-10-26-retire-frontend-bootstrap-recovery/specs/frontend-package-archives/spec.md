## ADDED Requirements

### Requirement: First-release incident operations are retired from the preparation workflow

The existing `.github/workflows/Publish-frontend-packages.yml` SHALL remain a `workflow_dispatch`-only workflow restricted to `swift`, with candidate preparation and application compatibility validation as its only active operation. The preparation path MUST retain the exact immutable archive transfer between the separately selected release and application toolchains, with no rebuild or re-baseline of candidate bytes. It MUST NOT schedule registry mutation or historical retained-artifact verification, grant `id-token: write`, receive `NPM_BOOTSTRAP_TOKEN` or another publishing credential, or use the `npm-publish` environment. The `publish-bootstrap`, `recover-bootstrap`, and `verify-existing` dispatch operations SHALL be unavailable.

The completed bootstrap-recovery and registry-verification-continuation JSON configuration files MUST be absent from the active source tree. No active workflow, contract checker, producer input selection, script, npm command, Makefile target, test loader, or package-validation path SHALL depend on or recreate either incident configuration. Package manifests, versions, the private producer root, candidate evidence, and the approved release contract MUST remain unchanged by this retirement.

#### Scenario: Preparation is dispatched without publication

- **WHEN** a maintainer dispatches the existing workflow on `swift` using its default preparation operation
- **THEN** candidate production, immutable transfer, and application compatibility validation run under their respective toolchains without publication approval, registry mutation, a bootstrap secret, or OIDC write permission

#### Scenario: An obsolete workflow operation is requested

- **WHEN** a caller requests `publish-bootstrap`, `recover-bootstrap`, or `verify-existing` after retirement
- **THEN** the operation is unavailable or rejected and cannot schedule candidate publication or historical-artifact verification

#### Scenario: Completed incident configuration is absent

- **WHEN** either obsolete first-release JSON file is absent
- **THEN** preparation, release-contract checking, package selection, and offline validation continue without reading or recreating that file

#### Scenario: Preparation retains exact archive transfer

- **WHEN** the application compatibility job receives the producer's candidate transfer
- **THEN** it verifies the approved source, execution identity, evidence, and original archive bytes before and after its isolated-consumer, browser, and host checks without rebuilding candidates

### Requirement: Generic registry verification and historical evidence survive incident retirement

The supported generic registry verifier SHALL continue to validate exact expected package coordinates and archive SHA-512 against the approved contract and candidate evidence; independently verify the registry dependency graph and installed tree, npm signatures, Sigstore certificate and expected repository/commit/workflow/artifact identity; and exercise clean registry consumers, browser smoke, and production-host compatibility without workspace, checkout, local-tarball, or application-dependency fallback. Bounded read-only metadata visibility checks MAY retry transient 404 results but MUST fail on unauthorized, malformed, or identity/integrity-mismatched responses. Retired recovery and continuation CLI options MUST fail with an actionable unsupported-option error rather than be ignored and produce a weaker apparent success. Controlled local tooling tests MUST NOT claim genuine public-registry success.

The original validated candidate record, historical initial and partial publication identities, per-package archive integrities and provenance expectations, and successful later verification identity and gates SHALL remain traceable in a compact historical record. Removing active incident configuration MUST NOT change those original records, package versions, registry state, or attestations. Publication source identities MUST remain separate from later verifier execution identity. An expiring or unavailable GitHub artifact MUST be identified as such; a source-history link MUST NOT be treated as replacement archive bytes.

#### Scenario: Generic registry verification still works

- **WHEN** an authorized caller supplies exact approved coordinates, candidate integrity, and independent expected publication identities through the supported generic verifier entry point
- **THEN** a fresh process loads without incident modules and retains installed-tree signature, cryptographic provenance, clean-consumer, browser, and host checks with no local fallback

#### Scenario: A retired verifier option is supplied

- **WHEN** the verifier CLI receives a `--recovery-*` or `--verification-*` option
- **THEN** it exits nonzero with an actionable unsupported-option error before reporting successful verification

#### Scenario: Temporary registry visibility differs between endpoints

- **WHEN** exact-version metadata is visible but package-wide metadata temporarily returns 404
- **THEN** bounded read-only readiness checks may reach matching metadata without repeating a publication command, while an unauthorized, malformed, or integrity-mismatched result fails

#### Scenario: Registry validation cannot establish the intended release

- **WHEN** a package has a validly signed attestation or matching metadata but an unexpected archive digest, repository, publication commit, workflow identity, dependency graph, or installed-tree resolution
- **THEN** verification fails rather than accepting signature validity or downloaded metadata alone

#### Scenario: Completed first-release evidence is reviewed

- **WHEN** a maintainer consults the initial publication, partial recovery, and successful later registry-verification history
- **THEN** original candidate and publishing identities, each package's SHA-512 and provenance expectations, the distinct verifier commit/run/attempt, and artifact retention limitations remain traceable without active incident configuration

#### Scenario: Only generic verifier tooling was tested locally

- **WHEN** controlled offline tests of the generic verifier pass without genuinely published packages and full registry gates
- **THEN** the result remains tooling evidence and does not claim public-registry success

### Requirement: Publication and adoption gates remain distinct after first-release retirement

Release documentation SHALL distinguish repository readiness, completed first-package creation and partial recovery, later Trusted Publishing configuration, optional staged-publishing policy, actual future publication, registry verification, FRED adoption, and external adoption. New public-package creation MUST require confirmed scope ownership and an account/organization permission model capable of creating the package; it MUST NOT assume a package-scoped credential can create a nonexistent package. The historical bootstrap actor and any later Trusted Publishing workflow identity MUST be recorded separately, and one identity MUST NOT be inferred from the other. Unconfirmed trust setup or bootstrap-token revocation MUST remain an explicit maintainer gate rather than be inferred from registry-verification success. The selected subsequent release policy remains direct Trusted Publishing with GitHub environment approval, whose implementation is deferred to another change; staged publishing is a documented alternative only for already-created packages when its prerequisites are approved.

A compatible design-token version SHALL precede its UI consumer; the independent SDK MAY be sequenced separately in a later release. FRED adoption SHALL follow genuine verification of its required registry prereleases, and any later SDK protocol-ownership transfer that changes SDK bytes MUST be validated and published at a corresponding version before FRED adopts it. RAGS adoption remains separately tracked under the same generic external-application contract. Published versions MUST remain immutable: correction or partial-failure recovery MUST use a previously validated version or a new version, never overwrite the existing bytes. Adoption rollback SHALL restore a prior validated dependency/lockfile set or application image.

#### Scenario: A future new public package is proposed

- **WHEN** a selected package name does not yet exist in the approved npm scope
- **THEN** maintainers establish scope ownership and actual package-creation authority before authorizing a distinct future publication path, rather than reactivating the retired bootstrap operation

#### Scenario: Later publishing trust is unconfirmed

- **WHEN** public-registry verification succeeds but Trusted Publisher configuration or bootstrap-token revocation has not been evidenced
- **THEN** that maintainer gate remains explicit and preparation-only operation does not claim routine publishing is enabled

#### Scenario: Maintainers choose staged publishing

- **WHEN** staged publishing is selected as a later release policy
- **THEN** it is used only after package creation and required npm, Node, access, two-factor, and maintainer approval prerequisites are satisfied

#### Scenario: FRED adoption is proposed

- **WHEN** maintainers prepare a later change to consume registry packages in FRED
- **THEN** required prereleases have matching integrity, provenance, and clean-consumer registry evidence, and any changed SDK artifact is released first

#### Scenario: A released candidate must be rolled back

- **WHEN** a defect is found after publication or adoption
- **THEN** maintainers supersede the affected version and restore a prior validated dependency set or image without replacing published bytes

### Requirement: CI selection covers every active package-validation input

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

## REMOVED Requirements

### Requirement: Bootstrap, publication, and adoption remain separate gates

**Reason**: Its first-release publication, partial-recovery, and `verify-existing` workflow/CLI scenarios describe completed historical incident operations and cannot remain active after their configuration and jobs are deleted.

**Migration**: Use `First-release incident operations are retired from the preparation workflow` for the interim dispatch, `Generic registry verification and historical evidence survive incident retirement` for reusable verification/history, and `Publication and adoption gates remain distinct after first-release retirement` for the preserved release/adoption policy. Future routine OIDC publication is separately scoped.

### Requirement: CI selection covers every package-validation input

**Reason**: The predecessor block selects bootstrap/recovery inputs as active validation dependencies; those inputs are retired while all canonical package, archive, consumer, host, and release-readiness selection guarantees remain.

**Migration**: Use `CI selection covers every active package-validation input`. Its scenarios retain the unaffected producer, canonical CSS/component/protocol/asset/license, React, transfer, consumer-provisioning, validation-orchestration, and unrelated-file behavior and replace incident-only workflow selection with preparation-only selection.
