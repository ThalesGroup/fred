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

A release SHALL accept a nonempty, duplicate-free selection of registered packages and reject unknown names or IDs before any archive is built. Only selected members SHALL be candidate archives or publication commands; producer-wide regression testing is distinct from this selected candidate set. Compatibility validation SHALL resolve registered dependencies separately from the publication selection, using selected candidate bytes when that dependency is also selected, or an explicitly approved exact prior registry version and self-contained, source-reviewed prior-release baseline otherwise. The baseline MUST retain exact name/version/registry/SHA-512, independent expected attested digest/repository/publication commit/workflow/signer issuer, and verification traceability. After one-time verified import, later UI-only validation MUST download and verify exact registry bytes and cryptographic provenance against the baseline without requiring the historical candidate CI ZIP. A selected UI archive MUST be tested against a token version satisfying its declared peer range. When both tokens and UI are selected, tokens MUST be published and verified before UI. The iframe SDK SHALL remain independently releasable without selecting or publishing tokens or UI. Applicable token/UI/SDK archive, declaration/runtime-reference, license, asset, isolated-consumer, browser, and host contracts MUST NOT be weakened by selection.

#### Scenario: SDK-only release

- **WHEN** a maintainer selects only the registered iframe SDK
- **THEN** the SDK alone is packed and eligible for publication, its neutral consumer and production-host compatibility are tested, and no token/UI publication or UI consumer prerequisite is imposed

#### Scenario: A future SDK-only version leaves the other packages unchanged

- **WHEN** a reviewed SDK manifest/changelog selects a future exact SDK version while UI and tokens retain their published alpha.1 versions
- **THEN** only that SDK version is a release candidate and eligible for publication; token/UI producer-wide regressions may still run, but neither alpha.1 package requires a new candidate, publication command, or changed manifest

#### Scenario: UI-only release with existing tokens

- **WHEN** UI is selected and a reviewed exact, previously verified token version satisfies UI's committed peer range
- **THEN** UI alone is a publication candidate while both packages are installed for React/browser compatibility checks from its approved archive and the exact approved registry token baseline, with independent token byte/provenance verification and no local fallback

#### Scenario: The historical token CI artifact has expired

- **WHEN** a UI-only release uses an already imported self-contained token baseline but the original token candidate CI ZIP is no longer available
- **THEN** validation retrieves the exact token version from the approved registry and verifies SHA-512 and cryptographic provenance against the durable baseline without requiring or reconstructing that ZIP

#### Scenario: Combined tokens and UI release

- **WHEN** tokens and UI are selected together and UI's peer range accepts the selected token version
- **THEN** both exact candidates are validated together, then the token version is published and verified before the UI version

#### Scenario: Unknown or duplicate package selection

- **WHEN** selection contains an unregistered member, duplicate, empty item, or the private workspace root
- **THEN** the selection is rejected before packing or publication

#### Scenario: An incompatible dependency baseline is proposed

- **WHEN** UI's selected or existing token version is outside its committed peer range or lacks approved prior-release integrity/provenance evidence
- **THEN** UI candidate approval fails instead of installing an arbitrary registry tag, workspace member, or checkout copy

#### Scenario: Durable baseline expectations are missing or altered

- **WHEN** the token baseline lacks or changes its exact coordinate, SHA-512, independently expected provenance identity, or verification trace
- **THEN** UI-only validation fails before compatibility installation and does not invent expectations from current npm metadata or substitute a workspace copy

### Requirement: A generated release record binds policy, source, archives, and identities

Before publication, the release process SHALL generate a release record from the reviewed committed source and selected manifests. It MUST identify selected and compatibility-only packages; exact coordinates and dependency/peer ranges; the approved policy and its digest; source commit; observed producer and application Node/npm versions; actual archive filenames, byte lengths, and SHA-512 integrities; self-contained prior-release baseline digests; and expected registry, issuer, repository, workflow, and publication artifact digest. The record and exact selected candidate archives SHALL be retained together and independently rechecked before every downstream gate and publish command. Original candidate fields MUST remain immutable. Before any publication command, a separate approved publishing-attempt record MUST bind original candidate identity/digest, exact selected coordinates and archive integrities, and the independently expected *actual* current publishing commit/run/attempt, repository, authorized workflow, signer identity/issuer; it MUST be durably retained and read back with verified artifact identity/digest. Its ordered package-specific intents MUST be read back again before each corresponding command; failure to retain or verify that intent MUST prevent that command. Retained intent means publication may have been attempted, not that a command ran or succeeded. Actual verified per-package publication outcomes and a later verifier's distinct commit/run/attempt SHALL be recorded truthfully in bound records, without replacing the original candidate or attempt or deriving expected identity from a downloaded attestation. A retained attempt alone MUST NOT be reported as a successful publication.

For an ordinary release attributed to a retained attempt, the verifier MUST extract the cryptographically covered SLSA invocation identity and compare its source repository, run ID, and run attempt with that attempt, in addition to archive digest, workflow, source commit, and signer policy. Missing, malformed, mismatched, or multiply attributable invocation evidence MUST NOT establish a verified publication outcome. Historical compatibility baselines without a retained ordinary attempt remain governed by their separately reviewed historical expectations.

#### Scenario: A selected candidate passes all applicable gates

- **WHEN** a clean reviewed source builds and validates selected archives under the separate pinned producer/application toolchains
- **THEN** the generated record names only those archive files and records their observed sizes/SHA-512, policy, source, compatibility evidence, and successful applicable gates

#### Scenario: Candidate archive changes after validation

- **WHEN** a retained tarball, transfer metadata, or release record differs from the original approved bytes or identity
- **THEN** downstream approval and publication fail; no new digest or rebuilt archive is silently substituted

#### Scenario: Publication and verifier executions differ

- **WHEN** an approved continuation or independent verification executes at a commit/run/attempt different from candidate preparation
- **THEN** original candidate source/bytes remain unchanged, each package's actual publishing execution is recorded separately, and the verifier's actual execution is recorded separately without spoofing GitHub values

#### Scenario: A pre-publication attempt cannot be retained

- **WHEN** the approved publishing execution cannot upload and independently read back a valid attempt record binding candidate digest, exact selected bytes, and actual execution/provenance identity
- **THEN** no `npm publish` command starts and the failure is reported as missing durable prerequisite evidence

#### Scenario: A package-specific intent readback fails

- **WHEN** the selected member's retained command intent cannot be read back or differs from the candidate, archive, policy, or actual execution at its command boundary
- **THEN** that member's `npm publish` command is never invoked and later members do not progress

#### Scenario: Fixture evidence is presented as a release record

- **WHEN** a fixture, proposed-policy, incomplete, or stale record is supplied to publication or genuine public-registry verification
- **THEN** it is rejected even if its archive metadata is internally consistent

### Requirement: Ordinary publication uses one protected direct OIDC boundary

The retained workflow SHALL expose only `prepare-only`, `publish`, and `verify` ordinary operations on committed `swift`, with no push-triggered publication or retired incident mode. `publish` SHALL validate selected archives and release records, require one protected `npm-publish` environment approval for its publishing job, and use direct npm Trusted Publishing on GitHub-hosted runners. Protected publishing jobs MUST serialize across dispatches without cancelling an in-progress job; read-only verification need not share that concurrency boundary. Only that job SHALL have `id-token: write`; preparation, compatibility, and verification jobs MUST NOT receive a publishing token, environment secret, publishing environment, or OIDC write permission. Maintainers MUST review each selected existing package's exact npm Trusted Publisher configuration for GitHub organization/repository, existing workflow filename, environment, and direct `npm publish` permission before approving publication. Credential-free CI MUST validate repository-controlled policy and actual execution context but MUST NOT claim to have inspected private npm settings. npm SHALL enforce actual OIDC authorization during the approved publish; authentication or direct-publish permission failure MUST stop without token, interactive-login, or custom-authentication fallback. Configuration review or an `npm whoami`/dry-run result MUST NOT be represented as successful OIDC authentication; only a real published version with matching provenance and archive bytes establishes it.

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
- **THEN** maintainer review withholds approval when the problem is known; if an unobserved mismatch reaches npm, its OIDC authorization error stops the operation without token fallback or a claim that `npm whoami` proved OIDC

#### Scenario: Incorrect Trusted Publisher authorization reaches npm

- **WHEN** an approved direct publish encounters an npm OIDC authorization or direct-publish-permission rejection despite repository-controlled checks passing
- **THEN** the command fails cleanly, no later package is published, and the workflow neither requests npm credentials nor falls back to a token or interactive login

#### Scenario: Verification-only dispatch

- **WHEN** `verify` is dispatched with a selected retained release record and archive identity
- **THEN** it schedules evidence retrieval/provisioning and generic read-only registry/consumer/browser/host gates only, without candidate rebuilding, publication, OIDC write permission, or `npm-publish` approval

### Requirement: Partial publication and verification retries are evidence-bound

An ordinary retry SHALL explicitly select the original release record and exact retained candidate and pre-publication attempt artifact identities, including originating runs/attempts, artifact IDs, and independently checked ZIP/record/archive digests. Neither a failed-job rerun nor a new dispatch may infer the source artifact from the verifier's current `run_attempt`. The retry MUST check supplied prior attempts against the retained attempt history available from GitHub and reject omitted, expired, mismatched, or incomplete histories. A retained aborted terminal MAY identify a serialized untouched suffix only when its candidate/attempt/execution/digest binding, exact completed failed workflow run/attempt, failed sole publishing step, and successful later terminal-upload step are independently checked; the publisher MUST stop after writing it and MUST have no later publication path. Missing terminal artifacts, omitted references, absent outcomes, local flags, 404s, and unresolved running/cancelled executions alone MUST NOT establish non-execution. For each selected exact version, read-only reconciliation MUST distinguish absent, matching-published, and ambiguous/mismatched states. A matching published version MUST have the original recorded coordinate, archive SHA-512, cryptographically verified provenance, and truthful authorized publishing execution established by a verified outcome **or its durable pre-command attempt**. If npm accepted a version but no final outcome was saved, reconciliation MUST use that attempt's independent expectations plus registry evidence to establish success or fail closed; an attempt alone is never success. Only demonstrably absent versions MAY proceed after fresh approval and successful retention of a new actual-execution attempt record. Publication commands MUST NOT be retried automatically. Visibility retries MAY repeat bounded exact-version/package-wide reads only for temporary 404s; authentication, malformed metadata, unexpected provenance, or integrity drift MUST fail immediately. Missing, expired, unsafe, or ambiguous candidate/attempt/terminal evidence MUST produce an actionable failure rather than a rebuild, local fallback, overwrite, or false success. Expiry of an already imported historical dependency CI artifact MUST NOT invalidate a durable compatibility baseline.

#### Scenario: A verify-only retry uses a prior artifact

- **WHEN** a verifier runs again from a different commit/run/attempt with an explicitly selected intact prior release record and archives
- **THEN** it checks their original source/artifact identity and all published-package gates, records its own execution separately, and performs no publication

#### Scenario: A failed-job rerun has a new attempt number

- **WHEN** a publication or verification job is rerun after an earlier producer attempt
- **THEN** it retrieves the specifically recorded producer artifact and validates its API identity/ZIP digest instead of looking for an artifact named with the new attempt

#### Scenario: A new dispatch continues a partial release

- **WHEN** some selected exact versions already exist with approved archive bytes and verified publishing identities bound to outcomes or durable attempts, and others are absent
- **THEN** the continuation records its current GitHub execution truthfully in a new retained attempt, obtains a new protected approval, skips matching versions, and may publish only missing validated archives without relabeling candidate source or spoofing GitHub variables

#### Scenario: Tokens published but UI was demonstrably untouched

- **WHEN** tokens match their retained intent and cryptographic registry evidence, UI is absent, and every relevant prior completed publishing attempt has an independently verified retained terminal placing UI in its untouched suffix
- **THEN** a newly approved serialized continuation skips tokens and may invoke UI once from the original validated archive

#### Scenario: A prior attempt may have invoked UI

- **WHEN** UI remains invisible after bounded reads but a relevant attempt has no complete verified terminal proving UI untouched, or its job is pending/cancelled, or a prior attempt reference was omitted
- **THEN** continuation stops without another UI publication command

#### Scenario: A fresh candidate repeats an earlier attempted coordinate

- **WHEN** a new candidate names a coordinate already present in an ordinary retained publishing attempt for another candidate, regardless of an exact-version 404 or a missing final outcome
- **THEN** fresh publication stops and cannot bypass original-candidate evidence-bound continuation

#### Scenario: Publishing history is incomplete

- **WHEN** an attempt-specific workflow job crossed its durable-upload or execution step but its retained attempt artifact is deleted or unavailable, or the GitHub run search hits its result cap
- **THEN** continuation and fresh publication stop rather than treating an empty artifact list as proof of no earlier attempt

#### Scenario: A skewed source clock cannot shorten the history window

- **WHEN** the first exact selected-version changelog introduction has an author or committer timestamp later than its independently observed merged `swift` pull-request time
- **THEN** publication history inspection begins no later than the observed merge time and checks prior attempts before a command can run

#### Scenario: Historical published identity remains reserved during registry lag

- **WHEN** a selected coordinate is in the source-reviewed first-release known-published ledger but an exact-version registry read temporarily returns 404
- **THEN** it is not treated as an absent new publication candidate or sent to `npm publish`; historical appendix identity is checked independently of that read

#### Scenario: npm accepted publication before the outcome was saved

- **WHEN** npm accepts an exact version but the process or job ends before its verified final outcome is uploaded, while the pre-command attempt artifact remains intact
- **THEN** a later read-only reconciliation compares that attempt's independent expected bytes and actual publishing identity with exact registry metadata and cryptographically verified provenance; only a complete match may classify the version as published and skip it before continuing with demonstrably missing versions

#### Scenario: An existing exact version has different bytes or provenance

- **WHEN** registry reconciliation finds a selected version with unexpected name/version, SHA-512, repository, commit, workflow, or signer identity
- **THEN** the entire continuation stops before another publish command and does not overwrite or accept that version

#### Scenario: Registry evidence conflicts with a retained attempt

- **WHEN** a version appearing after a lost outcome has wrong SHA-512, attested artifact digest, repository, publishing commit, workflow, signer, or issuer compared with the durable pre-command attempt
- **THEN** reconciliation fails before publishing another package and never derives a new expected identity from the downloaded attestation

#### Scenario: Multiple attempts share the same publishing commit

- **WHEN** two retained attempts name the same source commit but different GitHub run IDs or attempts, and a signed SLSA invocation identifies one exact execution
- **THEN** publisher reconciliation skips a matching published version only for that uniquely identified execution; missing, conflicting, or ambiguous invocation attribution stops continuation

#### Scenario: Temporary registry visibility lags

- **WHEN** a successful publish initially yields exact-version or package-wide 404 followed by matching metadata within the bounded read window
- **THEN** only reads are retried and publication progresses only after full exact identity/integrity/provenance checks

#### Scenario: Evidence is missing or expired

- **WHEN** the selected original candidate or attempt artifact, release record, durable required baseline fields, or selected archive bytes are unavailable or fail identity/digest checks
- **THEN** retry/verification fails with the missing prerequisite identified and never silently rebuilds or resolves local FRED files

### Requirement: Selected registry verification preserves every applicable public gate

Generic registry verification SHALL accept the exact selected release record and verified publication outcomes or durable pre-command attempts, resolve only approved exact registry versions plus self-contained exact prior-dependency baselines, and compare downloaded archive bytes and cryptographically verified attestation digest/repository/actual publishing commit/workflow/signer against independent expected values in those records. A pre-command attempt MUST yield success only after full registry reconciliation; it cannot be treated as a publication outcome by itself. It MUST validate the full registry dependency graph and installed non-linked tree before `npm audit signatures`, then run clean source-isolated consumers, local-only browser smoke, and production-host compatibility where applicable to the selection and declared dependency baseline. Dependency and Chromium provisioning SHALL be separate network-capable prerequisites; offline archive installation and browser smoke MUST neither fetch dependencies nor bootstrap a browser. A controlled fixture run MUST NOT claim genuine public-registry success.

For selected ordinary packages, final verification MUST bind the signed invocation repository, run ID, and run attempt to exactly one retained authorized attempt. A valid signature and matching source commit alone MUST NOT choose among multiple attempts at that commit.

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

#### Scenario: Final verification encounters ambiguous same-commit attempts

- **WHEN** retained attempts share a publishing commit but the cryptographically covered invocation is missing, names another run or attempt, or matches multiple retained records
- **THEN** genuine public-registry verification fails before clean consumers or successful final evidence

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

### Requirement: Release coordinates and metadata are explicit

The release-readiness process SHALL consume an explicitly selected contract for the
independently versioned design-token, UI, and iframe SDK packages. For the completed first
release, that contract recorded the three alpha.1 coordinates and their metadata. For later
releases, each registered member's reviewed committed manifest SHALL supply its expected
name, exact version, dependency and peer ranges, exports, and member metadata; independent
reviewed repository policy SHALL constrain registry, scope, source, publishing identity,
access, and intended dist-tag. The generated selected release record MUST bind both sources
before packing, and validation MUST compare candidate contents with them rather than accept
metadata declared by an archive as its own expectation. A nonselected published member
MUST NOT be forced into the selected candidate set merely because it participated in the
first release or remains covered by producer-wide regression tests.

The producer workspace root MUST remain `private: true`, MUST NOT be a release
candidate, and MUST be distinguished from the publication eligibility and configuration
of each member package. Published member manifests MUST agree with their reviewed manifest
and independent policy, MUST contain no `workspace:`, `file:`, `link:`, `git+file:`, directory,
source-checkout, or other local dependency reference, and MUST preserve the existing exports,
asset, license, notice, CSS, React-peer, and protocol contracts.

The private producer lockfile MAY contain npm-generated `link: true` entries only for the
exact members declared by the root workspace manifest. Each such entry MUST resolve to
its declared member directory within the producer workspace. The lockfile MUST reject an
undeclared linked package, a member-name mismatch, an escaping target, or any other link
that is not npm's representation of an explicitly declared producer member.

The completed initial coordinates were `@fred-oss/design-tokens@0.1.0-alpha.1`,
`@fred-oss/ui@0.1.0-alpha.1`, and `@fred-oss/iframe-sdk@0.1.0-alpha.1` on
`https://registry.npmjs.org/` with public access and initial `next` dist-tag. These are
historical first-release facts, not mandatory future versions or an all-three selection.
Bootstrap account `marc.fawaz` SHALL remain recorded separately from the future Trusted
Publishing workflow identity, together with the maintainer-supplied confirmation that it
has the `fred-oss` organization-owner role. Package API, SDK protocol, release, and
enduring npm publishing ownership SHALL each be explicitly assigned to `marc.fawaz`, and
subsequent releases SHALL use the selected direct Trusted Publishing policy with GitHub
environment approval. The distinct GitHub reviewer identity `marcfawaz` SHALL be documented
operationally without extending the release-policy schema. Selected coordinates or
npm-organization ownership alone MUST NOT imply product-contract ownership. Repository
tooling MAY use explicit non-authoritative fixtures, but MUST NOT represent fixture results
or a merely selected incomplete contract as approved release evidence.

#### Scenario: A confirmed coordinate set is selected

- **WHEN** maintainers select confirmed names, independent exact versions, dependency
  ranges, release metadata, and an intended dist-tag
- **THEN** synchronized member manifests, peer requirements, and the producer lockfile
  match the reviewed manifest-derived selected record and independent policy exactly

#### Scenario: The workspace root is inspected for release

- **WHEN** release readiness enumerates packable members
- **THEN** it excludes the private producer workspace root and evaluates each registered
  member independently; selection need not include all three initial packages

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
  repository field, or other required value that differs from the reviewed manifest
  and independent policy bound in its selected record
- **THEN** validation fails even if the archive is internally self-consistent

#### Scenario: Required release ownership is incomplete

- **WHEN** a command attempts to create approved release evidence while a required owner or
  later publication-policy field remains unresolved
- **THEN** it fails actionably and does not label the archives release candidates

#### Scenario: npm organization ownership is recorded

- **WHEN** the selected policy records the confirmed `fred-oss` organization and bootstrap
  account owner role
- **THEN** tooling accepts the selected scope and bootstrap authority only when all selected
  package names belong to `@fred-oss/`, without inferring package API, SDK protocol, release, or
  enduring publishing ownership

#### Scenario: The complete maintainer contract is confirmed

- **WHEN** the selected policy records `marc.fawaz` for all four ownership roles and `direct`
  for the subsequent Trusted Publishing policy
- **THEN** policy validation reports no unresolved maintainer decisions while candidate
  execution and publication remain subject to their separate source, validation, manual-choice,
  and protected-environment gates

#### Scenario: A fixture contract is relabelled without maintainer decisions

- **WHEN** a fixture contract's state is changed while it retains fixture approval
  identities, development versions or tag, or non-authoritative provenance identities
- **THEN** validation rejects it before packing and it cannot produce approved candidate
  evidence

#### Scenario: A later SDK coordinate is reviewed alone

- **WHEN** a reviewed SDK manifest/changelog selects a future exact SDK version while UI
  and design tokens remain at their published first-release versions
- **THEN** expected SDK metadata comes from its reviewed manifest and policy, and the
  unchanged UI/token coordinates remain compatibility or regression inputs rather than
  mandatory new release candidates

### Requirement: Candidate archives and evidence are immutable

Release-candidate validation SHALL operate on the actual packed bytes for the selected
package set, while producer-wide regression testing SHALL remain distinct from candidate
selection. Each selected archive MUST preserve its applicable existing design-token, UI,
iframe SDK, isolated-consumer, browser, and production-host compatibility guarantees; a
nonselected package need not produce a new release candidate. A successful candidate
record MUST bind the source commit, exact Node and npm versions, selected package
coordinates, archive filenames, and SHA-512 integrity values to those bytes. It MUST also
bind independently expected provenance source repository, candidate source commit,
authorized publishing workflow identity, and artifact digest. If publication runs in a
different execution, a durably retained pre-publication attempt MUST independently bind
the *actual* publishing commit/run/attempt and authorized signer identity before any
publish command. These expected values MUST come from reviewed source, independent policy,
candidate and attempt records, not from a downloaded provenance statement.

Any selected archive that is rebuilt, renamed in a way that changes its recorded identity,
modified, or replaced after validation MUST receive fresh archive, consumer, browser,
host-compatibility, and integrity evidence. A later publication step MUST use the exact
validated selected bytes; it MUST NOT rebuild packages and treat prior evidence as valid.

#### Scenario: Three candidate archives pass validation

- **WHEN** the historical or a later combined selection produces token, UI, and SDK tarballs
  whose metadata and contents satisfy the reviewed manifest/policy contract and all
  applicable archive gates
- **THEN** evidence records exact toolchain, coordinates, filenames, and SHA-512 integrity
  for each selected tarball together with expected repository, candidate source commit,
  authorized publishing workflow identity, and artifact digest

#### Scenario: Candidate bytes change after validation

- **WHEN** any selected candidate tarball is rebuilt or its bytes no longer match the recorded
  SHA-512 integrity
- **THEN** prior candidate evidence is rejected and the complete applicable validation
  sequence must run again

#### Scenario: Publication input differs from candidate evidence

- **WHEN** a future publication operation receives archive bytes other than the bytes
  identified by the reviewed selected evidence
- **THEN** it must stop before registry mutation rather than publishing a rebuild

#### Scenario: SDK-only candidate does not create token or UI candidates

- **WHEN** only a future SDK version is selected while token and UI versions remain unchanged
- **THEN** immutable candidate evidence binds only the SDK tarball, even if producer-wide
  token/UI quality or unit regressions also run

### Requirement: Release validation uses an exact producer toolchain

Candidate generation and release-evidence production SHALL require exact, non-floating
Node and npm versions recorded in independent reviewed release policy and the selected
record. The first-release pin was Node `24.21.0` with npm `11.19.0`, which satisfies
the documented minimums for npm Trusted Publishing and staged publishing; changing
either pin MUST be a reviewed policy change with renewed validation of selected archives.

FRED application tests that participate in compatibility validation MUST remain under
their separately controlled application toolchain. Release evidence MUST record exact
Node and npm versions for that application-test environment. Release orchestration MUST
identify which toolchain produced each item of evidence and MUST pass immutable selected
candidate archives between producer and application-test environments rather than resolving
the producer's installed dependencies from the application environment.

#### Scenario: Candidate production uses the pinned versions

- **WHEN** a release-candidate command starts with Node or npm different from the exact
  selected versions
- **THEN** it fails actionably before packing or recording candidate evidence

#### Scenario: Application compatibility runs on its own tooling

- **WHEN** CI executes FRED application regression or production-host compatibility
  checks against selected candidate archives
- **THEN** the application uses its independently pinned tooling and receives the exact
  candidate bytes without using the producer dependency tree

#### Scenario: The toolchain pin changes

- **WHEN** maintainers select a different exact Node or npm version
- **THEN** selected archives and their release evidence are regenerated and revalidated;
  producer-wide regression coverage remains a separate applicable gate

### Requirement: Fixture transfer preserves exact producer archives across CI jobs

CI MAY continue exercising the release-to-application toolchain boundary with a
non-authoritative development fixture contract. For the initial three-member fixture, the
release-toolchain producer SHALL create one strictly fixture-labelled transfer containing
exactly the three validated npm tarballs and producer metadata. A future routine release
transfer SHALL instead contain the exact *selected* candidate set and generated record;
an SDK-only release MUST NOT require token/UI candidate tarballs. Both kinds of metadata
MUST bind checked-out source commit, independently expected policy/fixture digest, observed
producer Node/npm, selected roles/coordinates, actual filenames/byte lengths/SHA-512, and
repository/workflow/run/attempt identity. A fixture MUST state that downstream consumer,
browser, and host gates have not run and MUST NOT be classified as approved candidate or
public-registry evidence. A retained transfer artifact MUST exclude credentials, installed
dependencies, consumer caches, and checkout content and MUST use explicit retention and
source/run-specific identity.

The application-toolchain receiver MUST obtain the exact transfer from its producer
dependency in the same workflow execution, MUST independently select expected checkout
commit and fixture policy or selected release record, and MUST validate metadata plus exact
recorded archive file set before extraction, installation, or execution. It MUST reject
missing, additional, non-regular, substituted, truncated, or modified files; wrong commits,
policy/record digests, package identities, versions, or run associations; and missing,
malformed, or inconsistent integrity metadata. It MUST pass only verified explicit archive
paths and expected integrities to applicable isolated consumers, browser harness, and
production-host SDK integration. It MUST NOT rebuild/repack received archives, use mutable
latest-run selection or `target/` archive defaults, fall back to package sources/workspace
dependencies, or transfer installed dependency trees between jobs.

Final fixture validation evidence MUST be written only after all required receiver gates
succeed. It MUST retain the `fixture-candidate-evidence` classification, bind original
transfer metadata digest/artifact identity to exact archive records, record the receiver's
actually observed application Node/npm separately from producer versions, and include
consumer, browser, and host results. An incomplete receiver run MUST NOT leave successful
final evidence. Fixture transfer/validation evidence MUST NOT satisfy approved-candidate
retention, exact-toolchain candidate execution, or genuine registry-verification requirements.
For routine selected releases, final candidate evidence likewise MUST be retained only after
every *applicable selected* receiver gate passes; producer-wide regression results remain
distinct from the selected transfer's file set.

#### Scenario: A valid fixture set crosses the toolchain boundary

- **WHEN** the release-toolchain job uploads its source/run-specific three-archive fixture and the
  dependent application-toolchain job receives it in the same workflow attempt
- **THEN** the receiver verifies metadata and exact bytes before reusing those paths without
  invoking any package build or pack operation

#### Scenario: Transfer contents are incomplete or substituted

- **WHEN** an archive or metadata file is missing or additional, non-regular, truncated, modified,
  or inconsistent with its recorded length or SHA-512
- **THEN** transfer validation fails before installation or package execution and does not search
  local generated archives for a replacement

#### Scenario: Transfer identity differs from receiver expectations

- **WHEN** source commit, policy/fixture/record digest, package coordinate, repository,
  workflow, run, or attempt differs from the receiver's independently selected expectation
- **THEN** transfer validation rejects the complete set before any downstream gate runs

#### Scenario: A downstream fixture gate fails

- **WHEN** any isolated consumer, browser smoke, or production-host integration gate fails after
  transfer verification
- **THEN** no successful final fixture-candidate evidence record is written

#### Scenario: A downstream gate changes a transferred archive

- **WHEN** a downstream gate mutates an archive after initial transfer verification but otherwise
  reports success
- **THEN** the receiver's post-gate byte-length and SHA-512 verification fails and no final
  fixture-candidate evidence record re-baselines the changed bytes

#### Scenario: A fixture record is presented as approved evidence

- **WHEN** intermediate transfer metadata or final fixture validation evidence is supplied to an
  approved candidate, publication, or public-registry verification path
- **THEN** the operation rejects fixture classification regardless of otherwise matching
  archive hashes

#### Scenario: A selected SDK-only candidate crosses the toolchain boundary

- **WHEN** a reviewed SDK-only release candidate is transferred to application compatibility
- **THEN** the receiver requires exactly its recorded SDK archive/metadata and runs SDK-specific
  neutral-consumer/browser/host gates without token/UI candidate files; missing or extra files fail

### Requirement: Candidate versions work in isolated consumers

The existing neutral token, React UI, and framework-independent iframe SDK consumers
SHALL accept exact selected candidate coordinates and install their actual candidate
archives in fresh locations outside the FRED checkout. Each selected package MUST pass
its applicable consumer, production-build, browser, and SDK production-host gates; an
SDK-only selection MUST NOT require new token/UI candidate archives. A UI-only selection
MUST use the exact approved token version whose registry SHA-512/provenance expectations
are retained in a self-contained reviewed compatibility baseline. Provisioning MAY
populate only lockfile-pinned caches and browser prerequisites declared for the selected
candidates and exact compatibility-only versions. Offline validation MUST retain source
isolation, builds, browser checks, and applicable host compatibility without network
access, directory dependencies, workspace links, local source fallback, or resolution
from FRED's installed dependency tree. Expiry of the token's historical candidate CI ZIP
MUST NOT invalidate its already imported baseline; a missing selected candidate archive
MUST still fail.

Disposable offline consumer manifests and lockfiles MAY contain npm-generated `file:`
references to exact staged selected candidate `.tgz` files. Each permitted reference MUST
map by package identity to approved selected candidate evidence, identify a regular
non-symlink tarball file whose real path remains inside the disposable consumer, and match
recorded archive filename/bytes. Every permitted declaration MUST use exactly
`file:<approved-record-filename>`; alternative spellings MUST be rejected rather than
normalized. A dependency declaration legitimately has no integrity field, but every
direct or nested local package-resolution entry MUST contain a valid SRI SHA-512 integrity
value matching the approved record. Validation MUST inspect all applicable root and
nested manifest/lock dependency fields and local lock resolutions before dependency
installation; a matching basename alone MUST NOT authorize a reference. Noncanonical
tilde, whitespace/control-character, dot-segment, percent-encoded, query, fragment,
backslash, absolute, or escaping forms MUST be rejected so validation and npm cannot
resolve different targets. Local Git checkout references such as `git+file:` MUST be
rejected case-insensitively, including leading whitespace that npm may normalize. No
directory target, unexpected/additional local file, checkout path, unmatched nested
dependency, symlinked package, or reused FRED dependency tree is permitted. An approved
compatibility-only registry dependency MUST resolve to its exact coordinate and SRI
integrity from the prepared cache during offline installation, not a `file:` workspace
or checkout substitute. Production-host integration MUST run the host with dependencies
installed from the FRED application's own lockfile while loading the SDK under test only
from its verified selected archive or exact registry installation.

#### Scenario: Candidate archives replace development versions

- **WHEN** isolated consumers are configured with a historical combined or later selected
  token, UI, and SDK candidate set and matching lockfiles
- **THEN** offline installation, type checking, production builds, browser smoke, and
  host compatibility pass with the actual selected candidate tarballs

#### Scenario: npm records a verified candidate tarball

- **WHEN** disposable offline installation records a `file:` dependency or lockfile
  resolution for a staged selected candidate `.tgz` whose bytes match recorded SHA-512
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

- **WHEN** a local tarball reference uses encoded traversal or separators, a query, a
  fragment, or a backslash that npm could interpret differently from a literal check
- **THEN** isolated-consumer validation rejects the ambiguous reference before dependency use

#### Scenario: npm would normalize a noncanonical local reference

- **WHEN** a local declaration or resolution uses a tilde, an actual tab, a dot segment,
  or any spelling other than `file:<approved-record-filename>`
- **THEN** isolated-consumer validation rejects it before dependency installation even if a
  literal filesystem lookup would find matching candidate bytes

#### Scenario: A local Git checkout is declared

- **WHEN** an offline or published-package dependency uses `git+file:` with any casing or
  leading whitespace
- **THEN** validation rejects the local checkout reference before dependency installation
  or archive acceptance

#### Scenario: A local package resolution omits integrity

- **WHEN** a direct or nested local package-resolution entry has missing, null, empty,
  malformed, or mismatched integrity
- **THEN** isolated-consumer validation rejects the graph before dependency installation
  while continuing to permit declarations without their own integrity field

#### Scenario: A consumer resolves a development or workspace package

- **WHEN** a candidate consumer graph contains `0.0.0-development`, a workspace link, a
  directory dependency, an unverified local file dependency, or a package resolved from
  the FRED checkout or its installed dependency tree
- **THEN** release-candidate validation fails

#### Scenario: Production host compatibility uses the packed SDK

- **WHEN** the production-host integration gate exercises an SDK candidate
- **THEN** the host runner and application modules resolve from the FRED application's
  own lockfile installation while the SDK entry resolves from the integrity-verified
  candidate archive, not the producer workspace

#### Scenario: Candidate provisioning is incomplete

- **WHEN** an exact selected or compatibility-only dependency or browser prerequisite
  is absent from the prepared cache
- **THEN** offline validation fails actionably without fetching or installing it

#### Scenario: An SDK-only candidate is installed without new UI or tokens

- **WHEN** only a future SDK version is selected and its exact tarball is staged
- **THEN** its neutral consumer and host/browser compatibility use that archive outside FRED
  without requiring new token/UI tarballs or publication

#### Scenario: A UI-only consumer uses a durable token baseline

- **WHEN** the historical token CI ZIP has expired but the source-reviewed baseline and exact
  registry token archive are verified and provisioned into the dedicated pinned cache
- **THEN** offline UI consumer installation uses the selected UI tarball and exact cached
  compatible token version, with no source/workspace or network fallback during validation

### Requirement: Registry verification is exact and cannot fall back locally

The repository SHALL provide a registry-verification command that accepts exact selected
package coordinates and previously recorded archive SHA-512 integrities from the reviewed
manifest/policy-bound release record, plus any exact compatibility-only coordinate and
self-contained approved baseline. The completed first release verified all three alpha.1
coordinates; later SDK-only verification MUST NOT require newly published token/UI
coordinates. Against a real public registry, the command MUST resolve those exact selected
and compatibility-only versions, verify registry-reported and downloaded-byte integrity,
cryptographically verify provenance for every FRED package it resolves, and exercise fresh
clean consumers applicable to the selected release and compatibility baseline.

Before installing each resolved package, the verifier MUST compare its exact identity,
version, registry, and downloaded SHA-512 with selected candidate evidence or an approved
durable prior-dependency baseline. It MUST generate and validate the disposable registry
lock graph against those same independent expectations, including every FRED package
resolution present. Only an accepted graph may be installed with lifecycle scripts
disabled. Before running `npm audit signatures`, the verifier MUST prove through npm's
actual installed-tree behavior and the installed package's filesystem identity that each
exact package is a non-linked installed dependency contained in the fresh disposable root.
A package-lock without corresponding installation MUST NOT satisfy this gate.
Installation or audit MUST NOT use a local tarball, workspace, checkout, application
`node_modules`, or other fallback.

Cryptographic signature validity alone MUST NOT establish a matching release. Verification
MUST require the signing certificate identity to equal the independently authorized GitHub
workflow URI and its issuer to equal the independently expected GitHub Actions OIDC issuer.
For every package, it MUST compare attested artifact digest, source repository, *actual
publishing commit*, and workflow identity with explicit expected values from the selected
candidate record plus a verified publication outcome or its durable pre-command attempt,
or from a previously imported self-contained compatibility baseline. An attempt alone
MUST NOT be treated as proof of successful publication. It MUST NOT accept values merely
because they appear in a validly signed downloaded attestation. Expected historical
bootstrap and later Trusted Publishing identities MUST remain distinct; an unconfirmed
identity MUST fail closed as a maintainer decision. The publishing source commit MUST be
selected from exactly one resolved dependency whose normalized URI identifies the expected
source repository; an unrelated dependency's commit MUST NOT satisfy the comparison, and
a missing/ambiguous matching dependency MUST fail closed. A current verifier's commit,
run, and attempt MUST remain separate from those actual package publication identities.

For an ordinary release whose expected actual publishing execution comes from a retained attempt, the command MUST compare the signed SLSA invocation repository, run ID, and run attempt with exactly one retained attempt. The signed in-toto statement type and SLSA predicate type MUST identify the approved GitHub/npm provenance format and agree with registry metadata; an outer SLSA label cannot substitute for a signed SLSA predicate. A matching source commit or workflow without a unique matching invocation MUST NOT establish success. Multiple SLSA provenance entries or malformed invocation identifiers MUST fail rather than choosing one opportunistically. This extra ordinary-attempt check does not rewrite the separately verified historical first-release baseline.

The command MUST reject tags, ranges, unexpected registries, missing provenance,
integrity mismatches, local tarballs, workspace packages, source-checkout resolution,
and silent fallback. Its local automated tests MUST use controlled fixtures or equivalent
deterministic responses and label their result as tooling validation, not as proof of
genuine publication.

The command MUST discover the attestation document from npm's raw
`dist.attestations.url` version-metadata field, validate that it is an allowed npm
attestation endpoint for the exact expected coordinate, and re-root its pathname onto
the explicitly approved registry before fetching. It MUST reject missing, malformed,
credential-bearing, non-HTTP(S), fragment-bearing, endpoint-mismatched, or
coordinate-mismatched URLs. Sibling provenance predicate metadata MUST NOT be treated
as the endpoint location.

Browser verification MUST use an explicit pre-provisioned Playwright browser directory
shared by provisioning and verification. Before registry verification begins, the command
MUST confirm that Playwright resolves Chromium from that directory and its executable
exists. Missing, default-cache, or differently resolved Chromium MUST fail actionably;
registry verification MUST NOT install/download a browser.

After exact-version metadata establishes expected name, version, and SHA-512, the verifier
MAY perform bounded read-only package-wide metadata readiness checks required by npm
transport. It MUST retry only an actual package-wide HTTP 404 and fail immediately on
authentication/authorization errors, redirects, malformed metadata, or identity/integrity
mismatches. It MUST NOT interpret readiness as release identity, repeat publication, or
use a local archive when npm transport remains unavailable.

#### Scenario: Published candidates match recorded evidence

- **WHEN** the completed first release or a later combined selection supplies exact
  published token, UI, and SDK coordinates with approved integrities and the public
  registry serves matching packages with provenance
- **THEN** clean registry-only consumers pass their applicable build, browser, and
  compatibility checks without local fallback

#### Scenario: npm metadata provides the attestation endpoint

- **WHEN** exact-version metadata supplies a valid `dist.attestations.url` for the selected
  coordinate
- **THEN** the verifier fetches that endpoint only through the approved registry and
  performs cryptographic and independent expected-release identity checks

#### Scenario: An approved registry graph is installed before signature audit

- **WHEN** exact registry metadata and archive bytes match selected evidence or durable
  baseline and the generated lock graph contains only approved registry resolutions
- **THEN** the verifier validates that graph, installs it with lifecycle scripts disabled,
  proves each exact package exists in npm's installed tree, and only then runs signature audit

#### Scenario: A lockfile exists without an installed dependency tree

- **WHEN** registry resolution produced a package-lock but the exact dependency has not been
  installed in the disposable root
- **THEN** verification fails before npm signature audit rather than treating the lockfile
  as an installed tree

#### Scenario: The disposable registry graph has an unapproved resolution

- **WHEN** the generated graph contains a FRED package with mismatched version/integrity,
  unexpected registry, link, or local/workspace/checkout fallback
- **THEN** verification fails before dependency installation and provenance acceptance

#### Scenario: The provisioned browser is reused during registry verification

- **WHEN** the post-publication job provisions Chromium in its explicit Playwright directory
  and invokes registry verification with the same directory
- **THEN** the verifier confirms the selected executable is present there and browser
  smoke performs no browser installation/download

#### Scenario: Registry Chromium prerequisites are absent or inconsistent

- **WHEN** the explicit Playwright directory is missing, Chromium is absent, or Playwright
  resolves its executable from another directory
- **THEN** registry verification fails with an actionable provisioning error before registry
  resolution rather than bootstrapping a browser

#### Scenario: The attestation endpoint metadata is invalid

- **WHEN** `dist.attestations.url` is absent, malformed, disallowed, or names a different
  package coordinate or endpoint
- **THEN** registry verification fails before accepting or fetching provenance

#### Scenario: Valid provenance names an unexpected repository

- **WHEN** a provenance statement is cryptographically valid but its source repository
  differs from the repository independently expected by selected evidence/attempt/baseline
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected commit

- **WHEN** a provenance statement is cryptographically valid but its source commit differs
  from the actual publishing commit independently expected by the bound attempt/outcome or
  durable compatibility baseline
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected workflow

- **WHEN** a provenance statement is cryptographically valid but its publishing workflow
  identity differs from the independently authorized identity
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Signed non-SLSA statement is relabeled by unsigned registry metadata

- **WHEN** registry metadata labels a validly signed attestation as SLSA but its signed statement type or predicate type is not the approved in-toto SLSA format
- **THEN** registry verification rejects the attestation despite its valid signature

#### Scenario: A valid Sigstore bundle has an unauthorized signer identity

- **WHEN** a provenance bundle is cryptographically valid but signing certificate URI
  or issuer differs from independently expected certificate policy
- **THEN** registry verification fails before accepting statement identity claims

#### Scenario: Valid provenance names an unexpected artifact digest

- **WHEN** a provenance statement is cryptographically valid but its attested artifact
  digest differs from expected digest of the selected candidate or durable baseline tarball
- **THEN** registry verification fails even if registry metadata reports another internally
  consistent integrity value

#### Scenario: Registry content does not match the candidate

- **WHEN** registry metadata, downloaded bytes, or provenance is missing or differs from
  selected candidate evidence or approved durable baseline coordinate/integrity
- **THEN** verification fails and does not substitute a local archive or source tree

#### Scenario: Package-wide metadata becomes visible after the exact version

- **WHEN** exact-version metadata already matches approved identity and SHA-512 while
  npm's package-wide metadata initially returns 404 and then returns the same version
- **THEN** the verifier performs bounded read-only readiness retries and continues once
  without changing release identity or invoking publication

#### Scenario: Package-wide readiness cannot establish matching metadata

- **WHEN** package-wide 404 retries are exhausted or a read is unauthorized, redirected,
  malformed, or inconsistent with expected exact version/integrity
- **THEN** verification fails before npm transport, consumers, or evidence completion and
  does not fall back to local bytes

#### Scenario: A registry consumer attempts local fallback

- **WHEN** a registry-installed consumer resolves a FRED package from a tag, range, local
  tarball, directory, workspace, checkout source, or reused FRED dependency tree instead
  of expected exact registry version
- **THEN** verification fails rather than accepting consumer result

#### Scenario: Only verifier tooling was tested locally

- **WHEN** the verifier passes against controlled local fixtures without genuinely
  published package coordinates
- **THEN** evidence reports only verifier behavior, not a successful public-registry
  release verification

#### Scenario: SDK-only registry release leaves the first UI and tokens untouched

- **WHEN** a future selected SDK version is verified while token/UI remain at their
  published alpha.1 versions and are not compatibility dependencies of the SDK
- **THEN** exact SDK integrity/provenance and its neutral consumer/browser/host gates run
  without demanding new token/UI release records or candidate archives

#### Scenario: UI-only registry verification after old token artifact expiry

- **WHEN** the token's historical candidate CI ZIP expired after its exact coordinate,
  SHA-512, independent provenance expectations, and verification trace were imported
  into the reviewed baseline
- **THEN** verifier downloads the exact token registry package, checks bytes and
  cryptographic provenance against that baseline, then exercises UI/React/browser gates

#### Scenario: Registry evidence differs from a lost-outcome attempt

- **WHEN** a selected exact version appears after an outcome was lost but its bytes or
  actual publishing identity differ from the durably retained pre-command attempt
- **THEN** verification fails before treating the attempt as success or publishing a
  subsequent selected package

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
