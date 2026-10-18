## MODIFIED Requirements

### Requirement: One Fred UI for the bounded first-user journey

This branch SHALL provide its first-user journey through Fred's existing application, layout, navigation, theme and shared screen components, including the admitted person's profile, preferences, legal pages and static release notes. It SHALL NOT expose a separate manager application or substitute a parallel business navigation. Platform owners SHALL use the organization governance area described below, including when they hold business roles. CGU SHALL precede bootstrap, and admitted routes SHALL remain unavailable while admission state is loading or cannot be verified. Manager roles SHALL NOT be converted into control-plane permissions to enable unsupported features.

#### Scenario: Switch account before admission
- **WHEN** a signed-in person is shown CGU, bootstrap or an admission-service error
- **THEN** the existing account control still exposes their identity and logout without querying protected business data
- **AND** signing in as another person clears the prior person's state and reevaluates their own admission
- **AND** the admitted Profile action is absent until personal consent and platform bootstrap permit the protected journey

#### Scenario: Fresh platform and returning user
- **WHEN** a person enters Fred on a fresh platform
- **THEN** the existing CGU and bootstrap screens use manager state in that order
- **AND** completion leads the bootstrap owner into Organizations within Fred's existing administration layout, with account/profile and Provisioning access
- **AND** reload preserves completed consent/bootstrap without repeating them

#### Scenario: Unsupported routes and background work
- **WHEN** an admitted ordinary organization user opens Home, a team, marketplace, administration, help or account page
- **THEN** Fred retains the existing swift routes, components, menus, controls and styles, including Agents, Prompts and Resources
- **AND** unimplemented backend calls retain their ordinary loading/error behavior rather than causing navigation removal or a replacement page
- **AND** non-migrated calls remain unchanged until their explicit reconstruction lot; no automatic backend fallback or invented successful data is added
- **AND** organization information is absent from Home and navigation and appears only in the existing profile

#### Scenario: Admission becomes required or unavailable
- **WHEN** refreshed manager state requires a new consent version or cannot verify admission
- **THEN** admitted pages, including profile and its linked pages, are gated until current admission is confirmed
- **AND** the UI does not fall back to Python consent, cached Python permissions or an alternative application

### Requirement: Repeatable browser acceptance

An automated browser journey SHALL exercise Fred's existing application layout, navigation, OIDC login, manager HTTP API, PostgreSQL and OpenFGA starting without root grants or consent. It SHALL accept terms, bootstrap root through the screen, import the Make-generated ZIP, verify persisted hierarchy and roles, replay without duplicates, sign out and sign in as an imported person, and exercise access refusal and unsupported bundle feedback. Manager responses SHALL remain real. Non-migrated services SHALL return explicit unavailable-service responses in this isolated recipe, without fabricated success or permission data. Test setup SHALL leave unrelated development data untouched.

#### Scenario: Run browser acceptance repeatedly
- **WHEN** the developer runs the documented browser test command on a machine with its prerequisites
- **THEN** it creates isolated test state, exercises onboarding and import without manual curl or UI actions, and cleans up its services
- **AND** its assertions fail if consent, bootstrap, import, replay, account isolation or authorization behavior regresses
- **AND** it verifies Fred's original sidebar, home, administration and logout navigation
- **AND** business requests remain absent before admission; ordinary non-migrated requests after admission receive explicit service failures

### Requirement: Imported person enters declared organization

After ZIP import Fred SHALL retain its original Home dashboard and team/personal navigation. The person's authorized teams/projects and displayed roles SHALL come from manager memberships, and their unique organization name SHALL appear only in Profile. No organization selector, navigation row or hierarchy panel SHALL be introduced. Changing accounts SHALL clear the prior person's session data. An imported person SHALL accept terms personally before accessing this view. Platform administration alone SHALL NOT create organization membership or content authority. Non-migrated consumers SHALL keep their existing calls and loading/error behavior.

#### Scenario: Root imports and switches to a member
- **WHEN** root imports the Make-generated ZIP, signs out through Fred's account menu, and a declared member signs in
- **THEN** root sees the real import report and no automatic organization membership
- **AND** the member accepts terms and reaches the usual Home with navigation to declared teams/projects and roles
- **AND** the member cannot open provisioning without the required platform role

#### Scenario: Select a declared space
- **WHEN** an admitted person selects a declared team or project in home navigation
- **THEN** Fred opens the existing Agents route using that space's manager UUID, preserving the usual team menu including Prompts and Resources
- **AND** selection creates no membership and displays no organization summary panel

### Requirement: Personal space opens in the person's organization

For ordinary organization users, Fred SHALL provide its existing personal-space navigation entry using manager authority, with at most one personal space in the person's unique organization. No separate creation button, organization selector or redesigned screen SHALL be introduced. Personal-space identity SHALL come from its returned UUID and personal owner, never a synthesized Python identifier.

#### Scenario: Priya opens her personal space after import
- **WHEN** Priya accepts the active terms after demo provisioning and has explicit personal-space creation eligibility and activates the existing personal-space entry
- **THEN** Fred opens her personal space, creating it if absent, through the existing Agents route and personal navigation presentation using the returned UUID
- **AND** she retains navigation to fredlab with her admin, editor and analyst roles
- **AND** merely logging in, accepting terms or listing spaces creates no space

#### Scenario: Root without organization membership
- **WHEN** a platform-only root opens Home after bootstrap
- **THEN** Fred redirects to Organizations with authorized provisioning and shared account access, and no business navigation
- **AND** no personal space, organization membership or content access is created

### Requirement: Authorized resource browsing in the provisioned space journey

Fred SHALL retain its existing Resources route, full document workspace, navigation, controls and styles. Existing resource consumers SHALL keep their current service contracts until explicitly migrated; failures SHALL retain ordinary UI feedback without a reduced replacement page or fabricated successful data. Manager folder/document listing SHALL continue enforcing its own space and content authority independently of the UI binding.

#### Scenario: Priya browses personal and collective resources
- **WHEN** admitted Priya opens her personal space or fredlab and then Resources
- **THEN** Fred mounts the original resource workspace for the selected identifier with its existing permission conditions and service requests
- **AND** an unavailable non-migrated dependency retains its original error/loading behavior rather than a fabricated empty success

#### Scenario: Document pagination
- **WHEN** a caller pages through manager document metadata for an authorized folder
- **THEN** the manager cursor traverses name/id pages without duplicates or omissions for unchanged data
- **AND** an eventual UI binding SHALL preserve the existing pagination presentation without inventing totals or conflating folder identifiers with another service's identifiers

#### Scenario: Refusal, failure and revalidation
- **WHEN** a caller without current read authority requests a manager folder or document list
- **THEN** manager refuses without returning content
- **AND** a failed service request SHALL NOT become a fabricated successful UI response or grant

### Requirement: Authorized folder creation in Resources

Manager SHALL support folder creation at the root or inside a folder of a personal, team or project space for an admitted caller with current effective write permission. Creation SHALL make no Temporal call; its governance router SHALL require no ingestion client. The server MUST enforce the person's unique organization and current write authority; administration, membership or analyst rights alone SHALL NOT grant content writes. Fred SHALL retain its original folder dialog and existing service binding until that full resource contract is explicitly migrated.

#### Scenario: Create and browse
- **WHEN** an authorized editor creates a folder through manager in an authorized location
- **THEN** the folder is persisted there and appears in the corresponding manager folder listing
- **AND** the original Resources dialog is preserved without claiming that its existing service binding uses this manager operation

#### Scenario: Revocation and isolation
- **WHEN** a caller lacks write permission, loses it before a waiting write is admitted, or targets another person's private space or another organization
- **THEN** manager refuses creation without inserting a folder

#### Scenario: Repeated submission and navigation
- **WHEN** the user submits the original folder dialog or changes resource location
- **THEN** its existing pending and navigation behavior is preserved
- **AND** any later manager binding SHALL prevent concurrent duplicate submissions and prevent a late response from changing a different location

## ADDED Requirements

### Requirement: Shared account pages require no organization membership

An admitted person SHALL open Fred's existing Profile entry and `/settings` page independently of organization or space membership. The page SHALL show the current authenticated identity and the platform roles reported by manager, retaining the existing interface-theme, light/dark/system, language and logout controls and the existing links to `/gcu`, `/gdpr` and `/release-notes`. Existing shared presentation and preference persistence SHALL be preserved. A configured contact-support link SHALL use the existing account-menu entry. The previously agreed photo upload/delete exclusion remains; other existing UI consumers are restored without claiming their backend reconstruction.

#### Scenario: Platform owner without spaces
- **GIVEN** an admitted platform owner has no organization or space roles
- **WHEN** they open Profile from the existing account menu or navigate directly to `/settings`
- **THEN** the usual profile displays their own identity and manager platform roles, including `platform_owner`
- **AND** opening, reloading or changing a preference creates no membership, personal space or grant

#### Scenario: Roles are unavailable or belong to another account
- **WHEN** the manager role response is pending, fails, or the person changes accounts
- **THEN** the profile does not invent roles, substitute identity-provider roles, or display the previous person's identity or roles
- **AND** pending/error state is distinguishable from a successful response containing no platform roles

#### Scenario: Existing preferences and keyboard navigation
- **WHEN** an admitted person opens their profile using the keyboard and changes language, interface theme or display mode
- **THEN** the existing controls apply and persist their choices as usual
- **AND** Escape restores focus to the account-menu trigger, navigation closes the menu, and logout remains reachable before and after admission

#### Scenario: Legal pages and release notes
- **WHEN** the person follows the profile's CGU, privacy or release-notes link, or opens the corresponding URL directly after admission
- **THEN** the existing page reads its existing legal/release assets and provides its existing return navigation
- **AND** viewing accepted CGU does not write another acceptance or reopen bootstrap
- **AND** absent release text uses the existing unavailable-content presentation and never fabricated notes

#### Scenario: Ordinary imported person
- **WHEN** an imported person accepts their own CGU and opens Profile
- **THEN** the same pages are available with their own identity and platform roles, including a valid empty role list
- **AND** profile availability grants no platform-administration or content permission

#### Scenario: Organization in Profile only
- **WHEN** Priya opens her profile after the demo import
- **THEN** the profile displays her organization name from current manager memberships
- **AND** Home and team navigation retain their existing team/personal presentation without organization rows, hierarchy or kind panels
- **AND** pending or failed membership reads do not display stale organization information as current
