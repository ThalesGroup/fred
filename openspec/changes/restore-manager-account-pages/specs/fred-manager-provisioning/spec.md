## MODIFIED Requirements

### Requirement: One Fred UI for the bounded first-user journey

This branch SHALL provide its first-user journey through Fred's existing application, layout, navigation, theme and shared screen components, including the admitted person's profile, preferences, legal pages and static release notes. It SHALL NOT expose a separate manager application or substitute a parallel navigation. CGU SHALL precede bootstrap, and admitted routes SHALL remain unavailable while admission state is loading or cannot be verified. Manager roles SHALL NOT be converted into control-plane permissions to enable unsupported features.

#### Scenario: Switch account before admission
- **WHEN** a signed-in person is shown CGU, bootstrap or an admission-service error
- **THEN** the existing account control still exposes their identity and logout without querying protected business data
- **AND** signing in as another person clears the prior person's state and reevaluates their own admission
- **AND** the admitted Profile action is absent until personal consent and platform bootstrap permit the protected journey

#### Scenario: Fresh platform and returning user
- **WHEN** a person enters Fred on a fresh platform
- **THEN** the existing CGU and bootstrap screens use manager state in that order
- **AND** completion leads into Fred's existing layout with home, account menu, own profile and authorized provisioning navigation
- **AND** reload preserves completed consent/bootstrap without repeating them

#### Scenario: Unsupported routes and background work
- **WHEN** an admitted person browses the implemented journey or opens an unsupported document, agent, marketplace or administration URL directly
- **THEN** unsupported navigation is absent and unsupported URLs return to home without mounting those features
- **AND** the application makes no control-plane, knowledge-flow or agent-runtime requests, including task polling, announcements and profile enrichment

#### Scenario: Admission becomes required or unavailable
- **WHEN** refreshed manager state requires a new consent version or cannot verify admission
- **THEN** admitted pages, including profile and its linked pages, are gated until current admission is confirmed
- **AND** the UI does not fall back to Python consent, cached Python permissions or an alternative application

## ADDED Requirements

### Requirement: Shared account pages require no organization membership

An admitted person SHALL open Fred's existing Profile entry and `/settings` page independently of organization or space membership. The page SHALL show the current authenticated identity and the platform roles reported by manager, retaining the existing interface-theme, light/dark/system, language and logout controls and the existing links to `/gcu`, `/gdpr` and `/release-notes`. Existing shared presentation and preference persistence SHALL be preserved. A configured contact-support link SHALL use the existing account-menu entry. This lot SHALL NOT expose photo upload/delete or the backend-published patch-note dialog.

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
