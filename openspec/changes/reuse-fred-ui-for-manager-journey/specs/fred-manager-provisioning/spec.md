## MODIFIED Requirements

### Requirement: Manager-authorized provisioning page

The UI SHALL offer provisioning to manager platform administrators using manager authority, independently of control-plane administrative roles. Fred's existing administration navigation SHALL expose the page after personal terms acceptance and manager bootstrap completion. The page SHALL accept a ZIP, prevent duplicate submissions while pending, display completion counts only after success, and present failures with additive-replay guidance without claiming rollback.

#### Scenario: Complete and replay an import
- **GIVEN** an admitted manager platform administrator with sufficient authority for the bundle
- **WHEN** the operator opens Provisioning through Fred's administration navigation and imports the Make-generated demo ZIP
- **THEN** the page shows the completed identity, space and grant counts from the service
- **AND** replay preserves committed identities and space IDs

#### Scenario: Authority unavailable or denied
- **WHEN** manager authority is loading, unavailable or excludes platform admin
- **THEN** the page does not enable provisioning, including on a direct URL visit
- **AND** it distinguishes an unavailable authority service from a confirmed access refusal

#### Scenario: Rejected or interrupted import
- **WHEN** the service rejects a legacy ZIP, returns an import failure, or the connection is lost
- **THEN** the page shows an error and no success report for that attempt
- **AND** it explains that effects can remain and replay requires correcting the cause

### Requirement: Imported person enters declared organization

After ZIP import Fred's existing home and space navigation SHALL display the caller's own declared organization and space memberships and roles from manager authority. Changing accounts SHALL clear the prior person's session data. An imported person SHALL accept terms personally before accessing this view. Platform administration alone SHALL NOT expose organization content or create membership. The journey SHALL make no control-plane, knowledge-flow or agent-runtime calls and SHALL expose only its implemented destinations.

#### Scenario: Root imports and switches to a member
- **WHEN** root imports the Make-generated ZIP, signs out through Fred's account menu, and a declared member signs in
- **THEN** root sees the real import report and no automatic organization membership
- **AND** the member accepts terms and sees their declared organization, teams, projects and roles in Fred's existing home and navigation
- **AND** the member cannot open provisioning without the required platform role

#### Scenario: Select a declared space
- **WHEN** an admitted person selects a declared organization, team or project in the home navigation
- **THEN** the home view shows that membership's name, hierarchy and roles
- **AND** no agent or document page is opened and no membership is created

### Requirement: Repeatable browser acceptance

An automated browser journey SHALL exercise Fred's existing application layout, navigation, OIDC login, manager HTTP API, PostgreSQL and OpenFGA starting without root grants or consent. It SHALL accept terms, bootstrap root through the screen, import the Make-generated ZIP, verify persisted hierarchy and roles, replay without duplicates, sign out and sign in as an imported person, and exercise access refusal and unsupported bundle feedback. No manager or Python shell response SHALL be mocked. Test setup SHALL leave unrelated development data untouched.

#### Scenario: Run browser acceptance repeatedly
- **WHEN** the developer runs the documented browser test command on a machine with its prerequisites
- **THEN** it creates isolated test state, exercises onboarding and import without manual curl or UI actions, and cleans up its services
- **AND** its assertions fail if consent, bootstrap, import, replay, account isolation or authorization behavior regresses
- **AND** it verifies Fred's sidebar, home, administration and logout navigation and fails on calls to services outside this journey

## ADDED Requirements

### Requirement: One Fred UI for the bounded first-user journey

This branch SHALL provide its first-user journey through Fred's existing application, layout, navigation, theme and shared screen components. It SHALL NOT expose a separate manager application or substitute a parallel navigation. CGU SHALL precede bootstrap, and admitted routes SHALL remain unavailable while admission state is loading or cannot be verified. Manager roles SHALL NOT be converted into control-plane permissions to enable unsupported features.

#### Scenario: Switch account before admission
- **WHEN** a signed-in person is shown CGU, bootstrap or an admission-service error
- **THEN** the existing account control still exposes their identity and logout without querying protected business data
- **AND** signing in as another person clears the prior person's state and reevaluates their own admission

#### Scenario: Fresh platform and returning user
- **WHEN** a person enters Fred on a fresh platform
- **THEN** the existing CGU and bootstrap screens use manager state in that order
- **AND** completion leads into Fred's existing layout with home, account menu and authorized provisioning navigation
- **AND** reload preserves completed consent/bootstrap without repeating them

#### Scenario: Unsupported routes and background work
- **WHEN** an admitted person browses the implemented journey or opens a document, agent, marketplace or unsupported administration URL directly
- **THEN** unsupported navigation is absent and unsupported URLs return to home without mounting those features
- **AND** the application makes no control-plane, knowledge-flow or agent-runtime requests, including task polling, announcements and profile enrichment

#### Scenario: Admission becomes required or unavailable
- **WHEN** refreshed manager state requires a new consent version or cannot verify admission
- **THEN** admitted pages are gated until current admission is confirmed
- **AND** the UI does not fall back to Python consent, cached Python permissions or an alternative application
