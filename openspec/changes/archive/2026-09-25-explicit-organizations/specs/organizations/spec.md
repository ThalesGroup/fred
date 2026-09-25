## Purpose
Support isolated organizations within Fred while preserving the behavior and access of existing single-organization deployments.

## ADDED Requirements

### Requirement: Transparent default organization
Fred SHALL provide an organization with stable ID `fred`, display name `Fred` by default, and an optional configured display name. Existing clients SHALL operate in this default scope without an organization selector or new mandatory configuration.
#### Scenario: Existing deployment upgrades
- **WHEN** an existing installation upgrades and restarts, optionally configured with the name `Acme`
- **THEN** its community teams belong to `fred`, existing IDs, memberships, roles, resource associations and authorized operations remain usable, and the configured name changes no identity or authorization reference
#### Scenario: Minimal deployment
- **WHEN** Fred starts without organization-specific configuration
- **THEN** the default organization is available without additional setup or UI changes

### Requirement: Platform and organization administration
Platform administrators SHALL list, create, rename and delete empty non-default organizations and assign their administrators. Organization administrators SHALL administer their organization’s team registry and organization prompt, without acquiring rights over another organization or automatic access to protected team content. Non-empty or default-organization deletion SHALL be rejected.
#### Scenario: Scoped administrator
- **WHEN** an administrator of organization A uses an administrative API
- **THEN** the operation is limited to A, including direct identifier access, and does not grant platform organization-management privileges
#### Scenario: Organization lifecycle
- **WHEN** a platform administrator creates an organization and later deletes it while empty
- **THEN** both operations succeed without granting that administrator implicit access to organization content

### Requirement: Automatic administrator migration
An upgrade SHALL preserve every existing platform administrator as both a platform administrator and an administrator of `fred`, without manual role assignment. This migration SHALL be retryable and SHALL NOT become permanent inheritance of organization privileges from the platform role.
#### Scenario: Production administrator restarts
- **WHEN** an existing platform administrator upgrades and Fred restarts repeatedly
- **THEN** both roles are available without duplicate grants, and explicit subsequent role revocations are not undone by replaying the completed migration

### Requirement: Organization isolation
Each community team SHALL belong to exactly one organization. Backend access and discovery SHALL enforce organization boundaries; this change SHALL support neither cross-organization resource sharing nor team transfers. Existing team roles SHALL retain their content permissions within that boundary.
#### Scenario: Second organization
- **WHEN** an administrator or member authorized only in A requests B's teams or protected resources, directly or through listing/search
- **THEN** the backend withholds those results or denies access, including public-team discovery across organizations

### Requirement: Safe reconciliation
Startup SHALL preserve explicit organization assignments and converge safely after an interrupted migration. Personal and system teams SHALL retain existing behavior without being arbitrarily assigned to a business organization.
#### Scenario: Interrupted initialization
- **WHEN** startup resumes after partial organization or authorization initialization
- **THEN** it completes missing work without resetting existing assignments or silently serving with incomplete isolation

### Requirement: Organization prompt
The existing editable prompt SHALL become organization-scoped. Migration SHALL preserve its text and explicit empty value in `fred`; execution SHALL resolve the prompt from the authoritative team organization. Global model settings and technical instructions remain unchanged.
#### Scenario: Prompt isolation and compatibility
- **WHEN** teams from different organizations execute agents
- **THEN** each receives its own organization prompt, never another organization's text; existing default-organization APIs and runtime bindings remain compatible

### Requirement: Explicit membership and global terms
A user SHALL be able to belong to an organization without belonging to any team. Authenticated onboarding SHALL welcome users with no organization into `fred` and preserve explicit assignments to other organizations. Organization administrators SHALL assign members; no join-request workflow is introduced. Open-team self-joining and default-team enrollment SHALL respect organization membership.
#### Scenario: New user without a team
- **WHEN** a new user enters Fred without any organization assignment
- **THEN** they become an explicit member of `fred` and may join its open teams, but not another organization's teams
#### Scenario: Existing assignment
- **WHEN** a user assigned to another organization enters Fred or accepts the terms
- **THEN** they retain that assignment without being enrolled into default teams in another organization
#### Scenario: Global terms
- **WHEN** a user accepts the configured terms or belongs to multiple organizations
- **THEN** one global configured version and the existing per-user acceptance apply; organizations neither specialize the terms nor trigger separate consent
