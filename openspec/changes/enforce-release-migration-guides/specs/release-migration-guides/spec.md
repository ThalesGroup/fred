## Purpose

Ensure every Fred release provides operators with a traceable migration guide and
an operationally appropriate version, based on reviewed declarations from its PRs.

## ADDED Requirements

### Requirement: Every PR declares migration impact

Every PR SHALL add an English migration note with a unique identity, schema
version, title and impact of none, minor or major. The note MUST state applicability,
prerequisites, configuration, upgrade steps, validation, rollback and limitations.
A no-operation declaration MUST explain why normal deployment is sufficient.

#### Scenario: Missing or incomplete note
- **WHEN** a PR has no new note, an unknown impact, duplicate metadata keys, empty required content or template placeholders
- **THEN** the migration check fails with an actionable error, including for docs-only PRs

#### Scenario: Conditional activation
- **WHEN** deploying with a switch off needs no action but activation needs IAM, configuration or data operations
- **THEN** the declaration is at least minor and separates ordinary upgrade from activation

#### Scenario: Known database migration
- **WHEN** a PR adds an Alembic revision but declares only none impact
- **THEN** validation rejects the insufficient impact

### Requirement: Production configuration ownership stays explicit

Configuration-changing PRs MUST maintain Fred chart values and generated schemas,
or explain why a change is exclusively local and has no production configuration
impact. Migration instructions MUST be usable without private customer values.
Local configuration_prod.yaml files SHALL NOT be presented as production references.

#### Scenario: New optional switch
- **WHEN** a developer adds an optional feature switch
- **THEN** the chart reference and schemas describe it and the note states its default, omission behavior and activation requirements

### Requirement: Required status covers all PRs

The migration check SHALL run without path-based exemptions and without secrets
or write credentials for PR code. It SHALL validate the PR contribution against
its merge base. Enforcement SHALL be activated only after its status is available
on the target branch, preserving unrelated protection settings.

#### Scenario: Base branch contains another note
- **WHEN** the base advances with a migration note while a PR adds none
- **THEN** that base note does not satisfy the PR requirement

#### Scenario: Protection activation
- **WHEN** the check has landed and successfully run on the target branch
- **THEN** its exact status is added to the effective required checks without replacing existing checks or changing bypass policy

### Requirement: Release guides cover the actual release range

Release preparation SHALL aggregate the notes introduced since an identified
ancestor release of the target branch, including merged PRs and corrections.
It MUST reject missing or ambiguous history and uncoverable changes after policy
activation. Legacy changes before activation MUST receive an explicit bounded audit
before the first policy-governed release. Published notes MUST remain immutable.

#### Scenario: Unrelated newer tag
- **WHEN** another branch has a numerically higher release tag
- **THEN** that tag is not selected as this branch's baseline

#### Scenario: Delegation bootstrap
- **WHEN** the first guide is prepared after adoption
- **THEN** PR #2808's note is included if in range and legacy changes are not treated as covered by that note alone

#### Scenario: Published note modified
- **WHEN** a note present in the baseline release is rewritten or deleted
- **THEN** validation rejects the mutation and requires a new correction note

#### Scenario: Uncovered post-policy change
- **WHEN** a direct commit or merged contribution after activation has no migration declaration
- **THEN** release preparation fails instead of treating the absent declaration as none

### Requirement: Version reflects maximum operational impact

The release SHALL use a minimum patch increment for none, minor increment for
operational changes and major increment for substantial incompatible changes.
The maximum impact in the complete range SHALL control the minimum. Code and
chart tags MUST carry the same version and point to the same commit.

#### Scenario: Insufficient version
- **WHEN** any in-range note declares minor and a patch-only version is proposed
- **THEN** validation rejects that version and reports the required minimum

#### Scenario: Major dominates
- **WHEN** the range contains none, minor and major notes
- **THEN** a minor-only target is rejected

#### Scenario: Release candidate promotion
- **WHEN** a candidate core version satisfies the impact relative to the preceding stable release
- **THEN** promotion to that stable core version does not require an extra increment solely because the candidate exists

### Requirement: Guides are reproducible operator artifacts

The guide SHALL identify baseline and target version, summarize impact, preserve
conditional steps, validation and rollback, and link its sources. Generation MUST
be deterministic and links MUST remain usable in the exported document. The guide
SHALL be committed outside frontend assets and attached to both release publications.

#### Scenario: Repeat generation
- **WHEN** the same notes, baseline and target version are used twice
- **THEN** generated guide bytes are identical

#### Scenario: Stale or absent guide
- **WHEN** a code or chart release tag lacks the expected guide or its content differs from regeneration
- **THEN** publication fails before pushing images or charts

### Requirement: Release review includes operator instructions

The shared release workflow SHALL present the operator guide and minimum-version
result alongside user-facing release notes before explicit approval of release tags.
Human reviewers MUST assess operational completeness and cross-note ordering;
structural checks SHALL NOT be described as proof of migration safety.

#### Scenario: Routine release preparation
- **WHEN** the release skill prepares the next release
- **THEN** it uses migration impact rather than defaulting to a patch and shows both documents before tagging
