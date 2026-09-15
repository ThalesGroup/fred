## ADDED Requirements

### Requirement: Registered releases derive package identity from reviewed manifests

The release process SHALL use one explicit package registration inventory that permits additional members without a schema limited to exactly the initial three roles. Each registered member's committed manifest SHALL be authoritative for its package name, exact version, dependency and peer ranges, exports, and publishable metadata; the private workspace root SHALL remain excluded. Centrally maintained release policy SHALL independently constrain the allowed source repository, `swift` branch, public registry, publishing workflow filename/identity, `npm-publish` environment, access, dist-tag, provenance issuer, and exact producer toolchain. Validation MUST compare manifest values with that policy and the registration rather than accept an archive's self-declared values or a second hand-maintained manifest copy. A selected publication MUST have a corresponding reviewed source version/changelog entry and MUST NOT automatically bump versions or publish on every merge.

#### Scenario: A reviewed selected package version is prepared

- **WHEN** a committed release PR changes a registered member's version and matching changelog entry, and a maintainer selects that member
- **THEN** candidate identity and metadata come from that manifest while repository policy is checked independently

#### Scenario: The workspace root is selected

- **WHEN** a caller selects the private producer workspace root as a publication member
- **THEN** selection fails because only explicitly registered publishable members may be released

#### Scenario: A manifest conflicts with repository policy

- **WHEN** a selected manifest advertises a different registry, access, dist-tag, repository, or provenance setting than approved policy
- **THEN** candidate approval fails before packing or publication

#### Scenario: Version or changelog review evidence is absent

- **WHEN** publication is requested for a selected coordinate without its committed matching changelog entry and approved release source
- **THEN** no publish command runs; preparation alone does not imply release approval

#### Scenario: A published manifest contains a local dependency

- **WHEN** a selected manifest declares a `workspace:`, `file:`, `link:`, directory, or checkout dependency
- **THEN** published-manifest validation rejects it while only declared, contained npm producer-workspace links remain permitted in the private lockfile

### Requirement: Publication selection and compatibility dependencies are distinct

A release SHALL accept a nonempty, duplicate-free selection of registered packages and reject unknown names or IDs before any archive is built. Only selected members SHALL be candidate archives or publication commands. Compatibility validation SHALL resolve registered dependencies separately from the publication selection, using selected candidate bytes when that dependency is also selected, or an explicitly approved exact prior registry version and immutable prior-release identity/integrity evidence otherwise. A selected UI archive MUST be tested against a token version satisfying its declared peer range. When both tokens and UI are selected, tokens MUST be published and verified before UI. The iframe SDK SHALL remain independently releasable without selecting or publishing tokens or UI. Applicable token/UI/SDK archive, declaration/runtime-reference, license, asset, isolated-consumer, browser, and host contracts MUST NOT be weakened by selection.

#### Scenario: SDK-only release

- **WHEN** a maintainer selects only the registered iframe SDK
- **THEN** the SDK alone is packed and eligible for publication, its neutral consumer and production-host compatibility are tested, and no token/UI publication or UI consumer prerequisite is imposed

#### Scenario: UI-only release with existing tokens

- **WHEN** UI is selected and a reviewed exact, previously verified token version satisfies UI's committed peer range
- **THEN** UI alone is a publication candidate while both packages are installed for React/browser compatibility checks from approved archive or exact-registry bytes, with the token's prior identity/integrity verified and no local fallback

#### Scenario: Combined tokens and UI release

- **WHEN** tokens and UI are selected together and UI's peer range accepts the selected token version
- **THEN** both exact candidates are validated together, then the token version is published and verified before the UI version

#### Scenario: Unknown or duplicate package selection

- **WHEN** selection contains an unregistered member, duplicate, empty item, or the private workspace root
- **THEN** the selection is rejected before packing or publication

#### Scenario: An incompatible dependency baseline is proposed

- **WHEN** UI's selected or existing token version is outside its committed peer range or lacks approved prior-release integrity/provenance evidence
- **THEN** UI candidate approval fails instead of installing an arbitrary registry tag, workspace member, or checkout copy

### Requirement: A generated release record binds policy, source, archives, and identities

Before publication, the release process SHALL generate a release record from the reviewed committed source and selected manifests. It MUST identify selected and compatibility-only packages; exact coordinates and dependency/peer ranges; the approved policy and its digest; source commit; observed producer and application Node/npm versions; actual archive filenames, byte lengths, and SHA-512 integrities; prior-release dependency evidence; expected registry, issuer, repository, workflow, and publication artifact digest. The record and exact candidate archives SHALL be retained together and independently rechecked before every downstream gate and publish command. Original candidate fields MUST remain immutable; actual per-package publication commit/run/attempt and a later verifier's distinct commit/run/attempt SHALL be recorded truthfully in bound release outcomes, without replacing the original record or deriving expected identity from a downloaded attestation.

#### Scenario: A selected candidate passes all applicable gates

- **WHEN** a clean reviewed source builds and validates selected archives under the separate pinned producer/application toolchains
- **THEN** the generated record names only those archive files and records their observed sizes/SHA-512, policy, source, compatibility evidence, and successful applicable gates

#### Scenario: Candidate archive changes after validation

- **WHEN** a retained tarball, transfer metadata, or release record differs from the original approved bytes or identity
- **THEN** downstream approval and publication fail; no new digest or rebuilt archive is silently substituted

#### Scenario: Publication and verifier executions differ

- **WHEN** an approved continuation or independent verification executes at a commit/run/attempt different from candidate preparation
- **THEN** original candidate source/bytes remain unchanged, each package's actual publishing execution is recorded separately, and the verifier's actual execution is recorded separately without spoofing GitHub values

#### Scenario: Fixture evidence is presented as a release record

- **WHEN** a fixture, proposed-policy, incomplete, or stale record is supplied to publication or genuine public-registry verification
- **THEN** it is rejected even if its archive metadata is internally consistent

### Requirement: Ordinary publication uses one protected direct OIDC boundary

The retained workflow SHALL expose only `prepare-only`, `publish`, and `verify` ordinary operations on committed `swift`, with no push-triggered publication or retired incident mode. `publish` SHALL validate selected archives and release records, require one protected `npm-publish` environment approval for its publishing job, and use direct npm Trusted Publishing on GitHub-hosted runners. Only that job SHALL have `id-token: write`; preparation, compatibility, and verification jobs MUST NOT receive a publishing token, environment secret, publishing environment, or OIDC write permission. Before an actual publish, each selected existing package MUST have a trusted-publisher configuration matching the exact GitHub organization/repository, existing workflow filename, environment, and permission for direct `npm publish`. Configuration or an `npm whoami`/dry-run result MUST NOT be represented as successful OIDC authentication; only a real published version with matching provenance and archive bytes establishes it.

#### Scenario: Preparation-only dispatch

- **WHEN** `prepare-only` is dispatched on committed `swift` for selected registered members
- **THEN** candidate and applicable compatibility gates run without a publication job, protected-environment approval, publishing credential, or registry mutation

#### Scenario: Publish dispatch before approval

- **WHEN** `publish` prepares and validates a candidate but protected-environment approval has not been granted
- **THEN** no npm publication runs and the exact candidate record/archives remain available for review

#### Scenario: A protected publish is approved

- **WHEN** the selected packages have exact direct-publish trust settings and the approved publishing job starts on a GitHub-hosted runner
- **THEN** only that job may exchange its OIDC token and publish the already validated tarball bytes; registry identity and provenance are verified before dependent publication proceeds

#### Scenario: Trust configuration is missing or only staged

- **WHEN** a selected package lacks the exact trusted-publisher binding or permission for direct `npm publish`
- **THEN** publication stops before mutation and reports the per-package prerequisite; it does not fall back to a bootstrap token or claim that `npm whoami` proved OIDC

#### Scenario: Verification-only dispatch

- **WHEN** `verify` is dispatched with a selected retained release record and archive identity
- **THEN** it schedules evidence retrieval/provisioning and generic read-only registry/consumer/browser/host gates only, without candidate rebuilding, publication, OIDC write permission, or `npm-publish` approval

### Requirement: Partial publication and verification retries are evidence-bound

An ordinary retry SHALL explicitly select the original release record and exact retained artifact identity, including its originating run and attempt, artifact ID, and independently checked ZIP/archive digests. Neither a failed-job rerun nor a new dispatch may infer the source artifact from the verifier's current `run_attempt`. For each selected exact version, read-only reconciliation MUST distinguish absent, matching-published, and ambiguous/mismatched states. A matching published version MUST have the original recorded coordinate, archive SHA-512, cryptographically verified provenance, and the truthful authorized publication execution; only absent versions MAY proceed after fresh approval and actual-execution identity binding. Publication commands MUST NOT be retried automatically. Visibility retries MAY repeat bounded exact-version/package-wide reads only for temporary 404s; authentication, malformed metadata, unexpected provenance, or integrity drift MUST fail immediately. Missing, expired, unsafe, or ambiguous evidence MUST produce an actionable failure rather than a rebuild, local fallback, overwrite, or false success.

#### Scenario: A verify-only retry uses a prior artifact

- **WHEN** a verifier runs again from a different commit/run/attempt with an explicitly selected intact prior release record and archives
- **THEN** it checks their original source/artifact identity and all published-package gates, records its own execution separately, and performs no publication

#### Scenario: A failed-job rerun has a new attempt number

- **WHEN** a publication or verification job is rerun after an earlier producer attempt
- **THEN** it retrieves the specifically recorded producer artifact and validates its API identity/ZIP digest instead of looking for an artifact named with the new attempt

#### Scenario: A new dispatch continues a partial release

- **WHEN** some selected exact versions already exist with the approved archive bytes and verified actual publishing identities, and others are absent
- **THEN** the continuation records the current GitHub execution truthfully, obtains a new protected approval, skips matching versions, and may publish only missing validated archives without relabeling candidate source or spoofing GitHub variables

#### Scenario: An existing exact version has different bytes or provenance

- **WHEN** registry reconciliation finds a selected version with unexpected name/version, SHA-512, repository, commit, workflow, or signer identity
- **THEN** the entire continuation stops before another publish command and does not overwrite or accept that version

#### Scenario: Temporary registry visibility lags

- **WHEN** a successful publish initially yields exact-version or package-wide 404 followed by matching metadata within the bounded read window
- **THEN** only reads are retried and publication progresses only after full exact identity/integrity/provenance checks

#### Scenario: Evidence is missing or expired

- **WHEN** the selected original artifact, release record, prior dependency evidence, or required archive bytes are unavailable or fail identity/digest checks
- **THEN** retry/verification fails with the missing prerequisite identified and never silently rebuilds or resolves local FRED files

### Requirement: Selected registry verification preserves every applicable public gate

Generic registry verification SHALL accept the exact selected release record and publication outcomes, resolve only approved exact registry versions, and compare downloaded archive bytes and cryptographically verified attestation digest/repository/commit/workflow/signer against independent expected values in those records. It MUST validate the full registry dependency graph and installed non-linked tree before `npm audit signatures`, then run clean source-isolated consumers, local-only browser smoke, and production-host compatibility where applicable to the selection and declared dependency baseline. Dependency and Chromium provisioning SHALL be separate network-capable prerequisites; offline archive installation and browser smoke MUST neither fetch dependencies nor bootstrap a browser. A controlled fixture run MUST NOT claim genuine public-registry success.

#### Scenario: SDK-only registry verification

- **WHEN** a verified SDK-only release record is supplied
- **THEN** the exact SDK registry archive, signatures/provenance, neutral consumer, cross-origin browser, and existing FRED production host compatibility are exercised without requiring a new UI or token publication

#### Scenario: UI-only registry verification

- **WHEN** UI-only publication is verified against a previously approved exact token baseline
- **THEN** UI and the exact token dependency resolve from the public registry with their approved integrities, React peers and assets are checked, and the clean React consumer/browser gates run without workspace or local-tarball fallback

#### Scenario: A local or uninstalled registry graph is offered

- **WHEN** registry resolution contains an unexpected local link, directory, checkout dependency, missing installation, or unmatched transitive FRED version
- **THEN** verification fails before signature/provenance success can be reported

#### Scenario: A signature is valid for the wrong release

- **WHEN** an attestation is cryptographically valid but its artifact digest, repository, actual publishing commit, workflow, or signer policy differs from the independent release outcome
- **THEN** public verification fails rather than deriving intended identity from the downloaded attestation

### Requirement: An additional package can be registered without a three-role schema rewrite

Onboarding another public package SHALL add its private-workspace member, canonical manifest, explicit registration and applicable build/validator/consumer profile without changing a release schema merely because the package count increased. Registration MUST NOT automatically grant publication: maintainers MUST establish scope ownership, package-creation authority, a separately authorized initial creation operation, and then exact per-package Trusted Publisher configuration with direct-publish permission after that versioned package exists. Registered-package selection, record generation, CI input selection, and generic verification SHALL handle the additional member once its specialized validator and applicable compatibility gates are integrated. Existing token/UI/SDK requirements SHALL remain unaffected.

#### Scenario: A fourth package is registered

- **WHEN** a maintainer adds a fourth workspace manifest, registration, build, archive validator, and consumer/CI profile
- **THEN** selection and record validation accept that registered package without adding another hard-coded required role to the release schema

#### Scenario: A new package has no trust relationship yet

- **WHEN** its name does not yet exist on npm or direct Trusted Publishing has not been configured for it
- **THEN** ordinary OIDC publication is blocked; initial package creation and later trust configuration require separate authority and cannot be inferred from inventory registration

### Requirement: Routine release inputs select the existing regressions

CI SHALL select package/release validation for changed registered workspace manifests or lockfiles, changelogs, inventory, policy, release-record schema or helper, candidate/publishing/registry tooling, retained workflow, canonical source and assets, relevant license/notices, dependency baselines, and host compatibility inputs. An SDK-only release MAY skip unrelated UI rendering gates while retaining its SDK archive, browser, neutral-consumer, and host gates; a UI selection MUST retain its token compatibility/asset/browser gates. Every selected job that exercises offline consumers MUST provision its own dedicated dependency cache and Chromium, when needed, in separate steps. Unrelated application changes MAY skip package release validation while normal application checks remain.

#### Scenario: A reviewed release input changes

- **WHEN** a pull request changes a registered manifest/version, peer range, matching changelog, policy, inventory, workflow, or release-record/publisher/verifier code
- **THEN** existing frontend-package CI selects the affected release, archive, and compatibility regressions without exposing publishing authority in a PR job

#### Scenario: A canonical package input changes

- **WHEN** a consumed FRED stylesheet, component, protocol source, asset, notice, React baseline, or host integration input changes
- **THEN** the existing token/UI/SDK and application-host selection guarantees continue to select their applicable regressions

#### Scenario: Provisioning is missing from a selected job

- **WHEN** an offline consumer or browser prerequisite is absent in a job selected for release validation
- **THEN** validation fails actionably rather than downloading dependencies, using another job's cache, or installing a browser during smoke execution

## MODIFIED Requirements

### Requirement: First-release incident operations are retired from the preparation workflow

The existing `.github/workflows/Publish-frontend-packages.yml` SHALL remain `workflow_dispatch`-only and restricted to committed `swift`. Its ordinary operations SHALL be `prepare-only`, `publish`, and read-only `verify`; the candidate preparation/application compatibility path MUST retain exact immutable archive transfer between separately selected release and application toolchains without rebuilding or re-baselining candidate bytes. The completed bootstrap-recovery and registry-verification-continuation JSON configurations MUST remain absent, with no active reader or equivalent incident-control replacement. `publish-bootstrap`, `recover-bootstrap`, and `verify-existing` SHALL remain unavailable. Only the new protected ordinary publishing job may mutate the registry or receive `id-token: write`; preparation and verification MUST NOT receive publishing credentials or use `npm-publish` approval.

#### Scenario: Preparation is dispatched without publication

- **WHEN** a maintainer dispatches the existing workflow on `swift` using its default preparation operation
- **THEN** selected candidate production, immutable transfer, and applicable compatibility validation run under their respective toolchains without publication approval, registry mutation, a bootstrap secret, or OIDC write permission

#### Scenario: An obsolete workflow operation is requested

- **WHEN** a caller requests `publish-bootstrap`, `recover-bootstrap`, or `verify-existing` after retirement
- **THEN** the operation remains unavailable or rejected and cannot schedule incident publication or historical-artifact continuation

#### Scenario: Completed incident configuration is absent

- **WHEN** either obsolete first-release JSON file is absent
- **THEN** preparation, release-policy checking, package selection, and offline validation continue without reading or recreating that file

#### Scenario: Preparation retains exact archive transfer

- **WHEN** the application compatibility job receives the producer's candidate transfer
- **THEN** it verifies approved source, execution identity, record/evidence, and original archive bytes before and after applicable isolated-consumer, browser, and host checks without rebuilding candidates

#### Scenario: Ordinary protected publication is selected

- **WHEN** `publish` is selected for a reviewed release on `swift`
- **THEN** the existing preparation/compatibility path runs first and only its separately approved, OIDC-enabled publishing job may publish exact validated bytes

#### Scenario: Ordinary independent verification is selected

- **WHEN** `verify` is selected with an explicit prior record/artifact identity
- **THEN** only read-only retrieval, provisioning, and selected public-registry verification run without candidate creation or registry mutation
