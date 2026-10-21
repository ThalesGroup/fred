## ADDED Requirements

### Requirement: Platform organization console

An admitted platform owner SHALL enter an Organizations page within Fred's existing administration area, beside Provisioning. It SHALL reuse the existing team-administration visual components and styles to list organizations and create one by name with an existing owner account and an existing administrator account. Account/profile preferences, legal text and release notes SHALL remain available. Personal spaces, agents, prompts, resources and business navigation SHALL be absent from the platform area, including for owners also holding organization/team roles. Entry into that person's organization is a separate deferred journey.

#### Scenario: Platform landing and direct business URL
- **WHEN** a platform owner enters Fred, opens Home or directly requests a business route
- **THEN** Fred opens Organizations without mounting business data consumers
- **AND** Organizations, Provisioning and shared account pages remain reachable
- **AND** an ordinary organization user retains the original business UI unchanged

#### Scenario: Authority unavailable or revoked
- **WHEN** current manager authority cannot be verified or platform ownership is revoked
- **THEN** organization data and creation controls are not exposed using stale authority
- **AND** an unavailable service exposes retry without a business-interface fallback

### Requirement: Platform organization registry and creation

Manager SHALL expose an admitted platform-owner-only organization registry and creation operation independently of content membership. The registry SHALL return active organizations in bounded cursor pages without personal spaces or retired rows. Creation SHALL resolve the requested existing identities exactly, preserve unique names and one organization per person, and publish only the explicitly selected owner and administrator roles. The same person MAY hold both roles. The caller SHALL receive no automatic membership, personal space or content authority. Existing operator-command behavior SHALL remain unchanged.

#### Scenario: Create with distinct owner and administrator
- **WHEN** an admitted platform owner supplies a valid unique name and two known unattached accounts
- **THEN** one organization is committed with the selected Owner and Admin direct grants
- **AND** neither assignment nor platform ownership alone grants content access
- **AND** the UI reports success only after the response and refreshes the registry

#### Scenario: Invalid or conflicting creation
- **WHEN** a target is unknown, attached to another organization, the name is invalid or already reserved, or current platform authority is absent
- **THEN** creation fails explicitly without a committed organization or new effective roles
- **AND** a caller revoked while waiting for the mutation lock cannot finish creation
- **AND** double submission while pending sends at most one request; errors never trigger automatic replay

#### Scenario: Bounded registry and errors
- **WHEN** an owner pages through more than 100 active organizations
- **THEN** cursor pages contain no duplicates or omissions for unchanged data and no retired organizations
- **AND** a failed read hides stale rows and offers retry, distinct from a successful empty registry
- **AND** non-owners cannot read this registry even if they administer an organization

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
