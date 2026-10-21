## ADDED Requirements

### Requirement: Explicit personal terms acceptance
The manager SHALL expose the active terms version and the caller's persisted acceptance. When enabled, business operations SHALL require acceptance of that version on the server, including bootstrap and import. Acceptance SHALL bind the authenticated person's own subject, submitted active version and server timestamp. It SHALL create no role, organization, team or personal space. Import SHALL NOT accept terms for another person. Repeated acceptance of the same version SHALL preserve the recorded timestamp. Service credentials and delegated assertions SHALL NOT accept terms or bootstrap a root.

#### Scenario: First acceptance and a later version
- **WHEN** a signed-in person has never accepted terms or accepted an older version
- **THEN** the UI requires explicit acceptance and protected API operations fail before side effects
- **AND** accepting the displayed active version survives reload and login
- **AND** a stale submitted version returns 409 without changing acceptance

#### Scenario: Consent has no membership side effects
- **WHEN** a person accepts the active terms
- **THEN** only their acceptance is recorded, without any role or space creation
- **AND** another person's acceptance remains unchanged

### Requirement: Platform-only root onboarding
The first-person UI SHALL present terms before the existing secret-gated root bootstrap. It SHALL use manager state and generated manager calls only. Bootstrap SHALL grant only platform administration, preserving exclusive claimant recovery and permanent completion. It SHALL NOT create an organization or enroll the root in one. Errors and retries SHALL remain explicit, and an unavailable status service SHALL NOT admit the UI.

#### Scenario: Fresh platform root
- **WHEN** a person accepts terms and supplies the valid deployment secret on a fresh platform
- **THEN** they become platform root and can open provisioning
- **AND** the platform contains no spaces and that person has no implicit organization membership
- **AND** reloading does not reopen bootstrap

#### Scenario: Wrong secret or completed bootstrap
- **WHEN** the secret is invalid or bootstrap has already completed
- **THEN** the existing 403 or 409 feedback is shown without granting a new root

### Requirement: Imported person enters declared organization
After ZIP import the frontend SHALL display the caller's own declared organization and space memberships from manager authority. Changing accounts SHALL clear the prior person's session data. An imported person SHALL accept terms personally before accessing this view. Platform administration alone SHALL NOT expose organization content or create membership. The experimental entry SHALL make no control-plane or knowledge-flow calls and SHALL expose only this implemented journey.

#### Scenario: Root imports and switches to a member
- **WHEN** root imports the Make-generated ZIP, signs out, and a declared member signs in
- **THEN** root sees the real import report and no automatic organization membership
- **AND** the member accepts terms and sees their declared organization and spaces
- **AND** the member cannot open provisioning without the required platform role

## MODIFIED Requirements

### Requirement: Manager-authorized provisioning page

The UI SHALL offer provisioning to manager platform administrators using manager authority, independently of control-plane administrative roles. The experimental manager entry SHALL require personal terms acceptance and manager bootstrap completion before mounting the page; it SHALL not mount the legacy control-plane shell. The page SHALL accept a ZIP, prevent duplicate submissions while pending, display completion counts only after success, and present failures with additive-replay guidance without claiming rollback.

#### Scenario: Complete and replay an import
- **GIVEN** an admitted manager platform administrator with sufficient authority for the bundle
- **WHEN** the operator selects and imports the Make-generated demo ZIP
- **THEN** the page shows the completed identity, space and grant counts from the service
- **AND** replay preserves committed identities and space IDs

#### Scenario: Authority unavailable or denied
- **WHEN** manager authority is loading, unavailable or excludes platform admin
- **THEN** the page does not enable provisioning
- **AND** it distinguishes an unavailable authority service from a confirmed access refusal

#### Scenario: Rejected or interrupted import
- **WHEN** the service rejects a legacy ZIP, returns an import failure, or the connection is lost
- **THEN** the page shows an error and no success report for that attempt
- **AND** it explains that effects can remain and replay requires correcting the cause



### Requirement: Repeatable browser acceptance
An automated browser journey SHALL exercise the real UI, OIDC login, manager HTTP API, PostgreSQL and OpenFGA starting without root grants or consent. It SHALL accept terms, bootstrap root through the screen, import the Make-generated ZIP, verify persisted hierarchy and roles, replay without duplicates, sign out and sign in as an imported person, and exercise access refusal and unsupported bundle feedback. No manager or Python shell response SHALL be mocked. Test setup SHALL leave unrelated development data untouched.

#### Scenario: Run browser acceptance repeatedly
- **WHEN** the developer runs the documented browser test command on a machine with its prerequisites
- **THEN** it creates isolated test state, exercises onboarding and import without manual curl or UI actions, and cleans up its services
- **AND** its assertions fail if consent, bootstrap, import, replay, account isolation or authorization behavior regresses
