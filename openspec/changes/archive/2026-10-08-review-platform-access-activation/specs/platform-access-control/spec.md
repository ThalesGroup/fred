## MODIFIED Requirements

### Requirement: Platform administrators manage live exceptions

Only people holding the existing platform-management permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using Fred's local users, team authorization and Free-team controls, filtering state, effective admission sources with team identifiers, own-session claim selection, rule editing and draft preview. Team administrators and team managers SHALL NOT obtain this authority through their existing roles. Removing an individual exception SHALL NOT remove an identity or revoke independent team sources. Rule updates SHALL be explicit, atomic and versioned; stale concurrent saves SHALL return a conflict without overwriting another administrator's changes. Preview SHALL NOT change filtering, policy, T0, membership or evidence selected only by the proposed rule.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** an administrator adds an existing Fred user or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Administrator authorizes a selected user list

- **WHEN** a platform administrator selects any nonempty list of existing Fred users and grants admission
- **THEN** the operation SHALL atomically add removable manual exceptions without overwriting existing sources
- **WHEN** the list includes an unknown user or is submitted by a non-platform administrator
- **THEN** no exceptions SHALL be granted

#### Scenario: Leaving an allowed or Free team revokes its global source

- **WHEN** a person leaves or is removed from an allowed or Free team
- **THEN** the next direct, cached-token or delegated request on any participating reader SHALL no longer use that team for platform admission
- **AND** the person SHALL be refused when no independent source remains, while other grants and ordinary membership of other teams remain unchanged

#### Scenario: Unauthorized administrative call

- **WHEN** an ordinary person, team administrator or team manager requests claim discovery, preview, policy updates or exception administration
- **THEN** the call SHALL be refused and admission state SHALL remain unchanged

#### Scenario: Administrator sees provenance

- **WHEN** an administrator lists allowed users
- **THEN** individual entries SHALL identify manual or T0 origin and derived entries SHALL identify each authorized or Free team

#### Scenario: Preview explains an unsaved rule

- **WHEN** an administrator tests a draft against their verified token
- **THEN** the UI SHALL show per-condition results, missing or incompatible claim explanations, the aggregate rule result and whether they would be admitted with filtering active including independent sources, without saving the draft

#### Scenario: Two administrators save concurrently

- **WHEN** a save uses an older revision than the active policy
- **THEN** the system SHALL return HTTP 409 and retain the newer policy, while the UI preserves the unsaved draft and explains the conflict

User rows SHALL show identifier, first name and last name using the team-member table presentation, with email and source information retained. Selection SHALL survive paging without a fixed total cap; SQL batches SHALL remain bounded and grants atomic.

#### Scenario: Grant more than 100 people

- **WHEN** an administrator submits more than 100 known identities
- **THEN** all missing exceptions SHALL be added atomically, duplicate identities ignored and existing origins preserved
- **WHEN** an identity in a later batch is unknown
- **THEN** the complete operation SHALL roll back

### Requirement: Activation and migration are explicit

An absent admission authority SHALL initialize with filtering inactive until explicit administrator activation. Activation SHALL require a saved valid rule or at least one independent individual/team source and SHALL be refused if the acting administrator would lose their last admission source. Saving a policy or changing access exceptions while filtering is active SHALL apply the same actor safeguard atomically. Existing root bootstrap safeguards SHALL remain intact. Activation concurrent with a nonempty legacy-file gate SHALL be rejected; readers SHALL refuse an active conflicting gate. Policy, imported entries and membership SHALL survive restarts and temporary filtering disablement.

#### Scenario: Upgrade does not silently activate filtering

- **WHEN** operators deploy the required migration with empty admission state
- **THEN** filtering SHALL remain inactive until an admission source is prepared and an administrator explicitly activates it

#### Scenario: Administrator would lock themselves out

- **WHEN** activation, a policy save or an exception mutation would withdraw the actor's last admission source
- **THEN** the operation SHALL be refused with an actionable explanation and leave prior state intact

#### Scenario: Rule is not configured

- **WHEN** an administrator attempts activation without any saved rule or independent admission source
- **THEN** activation SHALL be refused without changing the filtering state

#### Scenario: Conflicting whitelist modes

- **WHEN** an administrator attempts activation while a nonempty legacy file gate is active
- **THEN** activation SHALL be refused without changing state, and readers SHALL fail closed if conflicting active state exists

The page SHALL offer a bottom-right filtering action across every tab with explicit confirmation. Before activation, a read-only population review SHALL show identifiable allowed, blocked and uncertain users under the saved rule and current independent sources, with counts and observation time. Stale/missing/conflicted evidence SHALL be uncertain rather than declared blocked. A preview SHALL NOT grant access or save drafts. Activation confirmation SHALL reject a changed policy revision and retain the actor safeguard.

#### Scenario: Review before activating

- **WHEN** an administrator requests activation with prepared saved admission sources
- **THEN** a confirmation dialog SHALL display the population dry run before any activation mutation
- **WHEN** they cancel
- **THEN** filtering SHALL remain unchanged

#### Scenario: Whitelist-only activation

- **WHEN** no rule is saved but the actor has an independent current exception
- **THEN** activation SHALL be allowed and other people without independent sources SHALL be refused

#### Scenario: Evidence cannot establish an outcome

- **WHEN** selected claim evidence is missing, expired or conflicted and no independent source applies
- **THEN** the preview SHALL mark that person uncertain without inventing token values or granting access

