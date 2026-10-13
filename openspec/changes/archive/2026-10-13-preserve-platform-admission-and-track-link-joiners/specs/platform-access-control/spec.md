## ADDED Requirements

### Requirement: Filtering can be paused without losing admission configuration

A platform administrator SHALL be able to turn filtering off from the existing administration action. While filtering is off, every authenticated, active person SHALL pass platform admission, including people who do not match a saved rule or exception. The saved rule, revision, individual exceptions, team authorization, Free flags and links SHALL remain unchanged and available for a later explicit activation. Authentication, account suspension, required terms acceptance and resource permissions SHALL continue to apply.

#### Scenario: Pause and resume configured filtering

- **GIVEN** filtering is active with a saved rule, individual exceptions and Free-team links
- **WHEN** an administrator disables filtering
- **THEN** a person outside every admission source SHALL pass platform admission on their next request
- **AND** the saved configuration SHALL remain visible and unchanged
- **WHEN** the administrator re-enables filtering through the existing review and confirmation
- **THEN** the retained configuration SHALL govern the next request without rebuilding it

#### Scenario: Other gates continue while filtering is off

- **WHEN** filtering is off and a person is suspended, has not accepted required terms, or lacks a resource permission
- **THEN** the corresponding existing refusal SHALL remain effective

### Requirement: Platform administrators cannot be denied by admission filtering

An active person holding the current platform-management permission SHALL pass platform admission when filtering is active, independently of rule results and individual or team exceptions. This admission SHALL use the authoritative current role on direct and delegated requests; it SHALL not grant a role, team membership or resource permission. A removed role SHALL stop providing this admission source on the next request. An unavailable authorization authority SHALL remain an availability failure, not a definitive admission denial.

#### Scenario: Administrator is outside every configured source

- **GIVEN** filtering is active and a platform administrator matches no saved rule or exception
- **WHEN** that administrator makes a direct or delegated human request
- **THEN** platform admission SHALL pass while ordinary authorization remains enforced

#### Scenario: Platform role is removed

- **GIVEN** an administrator was admitted only through the platform role
- **WHEN** that role is removed
- **THEN** the next direct or delegated human request SHALL no longer use the administrator admission source

#### Scenario: Unavailable role authority

- **WHEN** the current platform-management permission cannot be checked reliably
- **THEN** admission SHALL fail with the existing availability error rather than inventing an administrator role or returning a policy denial

### Requirement: Administrators can inspect successful Free-link joiners

Each Free-team link SHALL retain a bounded, paginated history of distinct people who successfully became members by enrolling through that link. Only platform administrators SHALL read the history. Each entry SHALL expose that person's current first name, last name and username while the account is active, or the last recorded values with a deleted marker after account deletion, plus the time of the successful join. This history SHALL remain visible if the person later leaves the team, the account is deleted, or the link is suspended, revoked or expired. An explicit deletion of the link history SHALL delete its joiner entries. Opening, previewing, accepting terms, unsuccessful enrollment and a repeated enrollment while already a member SHALL NOT create a joiner entry or change the page-opening aggregate.

#### Scenario: Two links have different joiners

- **GIVEN** a team has links A and B
- **WHEN** one person successfully joins through A and another through B
- **THEN** each link's joiner list SHALL contain only the person who joined through that link

#### Scenario: Member leaves and link is revoked

- **WHEN** a person joins through a link, later leaves the team and the link is revoked or expires
- **THEN** that person's join entry SHALL remain visible on that link until the link history is deleted

#### Scenario: Joiner account is deleted

- **WHEN** a person joins through a link and their account is later deleted
- **THEN** the join entry SHALL remain visible with their last recorded username and names, join time, and a deleted marker
- **AND** a missing local user row SHALL NOT erase or hide the entry

#### Scenario: Opening or repeat enrollment

- **WHEN** a person opens a link without joining, enrollment fails, or an existing member enrolls again
- **THEN** no new joiner entry SHALL be created
- **AND** the existing page-opening aggregate SHALL retain its established meaning

#### Scenario: Joiner history is restricted and paginated

- **WHEN** an ordinary team manager or person requests a link's joiner history
- **THEN** no joiner identity SHALL be returned
- **WHEN** a platform administrator opens a link with more joiners than one page
- **THEN** the complete history SHALL be reachable through bounded pages for that link only

#### Scenario: Explicit link-history cleanup

- **WHEN** an administrator deletes a revoked or expired link's history through the existing cleanup action
- **THEN** its joiner entries SHALL be deleted with the link, without changing team membership

## MODIFIED Requirements

### Requirement: Admission sources are independent of resource permissions

When filtering is active, the system SHALL admit a non-suspended person if their verified claim evaluation permits admission under the current allow/block mode, they have a current individual exception, they are a current member of an authorized team (including a Free team), or they hold the current platform-management permission. Ordinary public-team visibility SHALL not count as membership. Admission SHALL neither grant a platform role nor extend team or resource permissions. Account suspension and required CGU acceptance SHALL still apply.

#### Scenario: New non-matching person is refused

- **WHEN** a new person is not admitted by the current rule mode and has no individual exception, eligible membership or platform-management permission
- **THEN** normal platform access SHALL return HTTP 403 with `detail="platform_access_denied"`

#### Scenario: One source is removed while another remains

- **WHEN** a person's individual exception is removed but another valid admission source remains
- **THEN** admission SHALL remain available through that other source

#### Scenario: Visibility and admission are different

- **WHEN** a person can view a public authorized team but is not its member
- **THEN** that visibility SHALL not grant platform admission

#### Scenario: Admitted person is suspended or lacks resource permission

- **WHEN** an otherwise eligible person is suspended or requests a resource they cannot access
- **THEN** the existing suspension or resource refusal SHALL remain effective

### Requirement: Activation and migration are explicit

An absent admission authority SHALL initialize with filtering inactive until explicit administrator activation. Activation SHALL require a saved valid rule or at least one independent individual/team source and SHALL be refused if the acting administrator would lose their last admission source. Saving a policy or changing access exceptions while filtering is active SHALL apply the same actor safeguard atomically. Existing root bootstrap safeguards SHALL remain intact. The retired file-based whitelist SHALL NOT affect direct or delegated admission or activation. The administrator-managed SQL filter SHALL be the only platform admission filter. Policy, imported entries and membership SHALL survive restarts and temporary filtering disablement.

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

- **WHEN** an obsolete `users.txt` file remains on disk after upgrading
- **THEN** it SHALL NOT restrict a direct or delegated person or block activation of the administrator-managed filter

The page SHALL offer a top-right filtering action in the page header across every tab with explicit confirmation. Before activation, a read-only population review SHALL show identifiable users in counted Allowed and Blocked lists under the saved rule and current independent sources, with observation time. Stale/missing/conflicted evidence SHALL appear in a separate expandable Verification unavailable section rather than be declared allowed or blocked. A missing field in an available verified token SHALL be evaluated normally. The initial view SHALL show Blocked when that group is nonempty, otherwise Allowed; empty groups SHALL show a short message without table pagination. An Update action SHALL reread the database snapshot, reference policy and import status without changing admission state; stale rows SHALL be hidden and confirmation disabled during loading, failure or revision conflict. A preview SHALL NOT grant access or save drafts. Activation confirmation SHALL reject a changed policy revision and retain the actor safeguard.

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
- **THEN** the preview SHALL include that person under Verification unavailable without inventing token values or granting access

Before enabling through the UI, the initial-import status SHALL be known. If existing-user import has not completed, the activation confirmation SHALL explicitly warn that existing users have not been imported and offer Continue without importing or Go to whitelist. Continuing SHALL remain subject to the saved-policy population review and existing activation safeguards. Choosing Go to whitelist SHALL send no activation mutation and open Whitelist > Users. A completed import SHALL use normal activation confirmation. Loading or failed import status SHALL prevent enabling confirmation until retried successfully; disabling SHALL NOT depend on import completion.

#### Scenario: Continue without initial import

- **WHEN** an administrator reviews activation with an incomplete initial import
- **THEN** the modal SHALL explicitly present the missing-import warning and both choices
- **WHEN** they choose Continue without importing with valid fresh preview and admission sources
- **THEN** the UI SHALL request activation using the reviewed revision without importing users

#### Scenario: Navigate to import instead of activating

- **WHEN** an administrator chooses Go to whitelist in the missing-import confirmation
- **THEN** filtering SHALL remain unchanged, no activation mutation SHALL be sent and Whitelist > Users SHALL open

#### Scenario: Import already completed

- **WHEN** the initial import has completed and an administrator requests activation
- **THEN** normal population-review confirmation SHALL appear without the missing-import warning
- **AND** Whitelist > Users SHALL present completed import as a discreet status without a repeat-import action

#### Scenario: Import status unavailable

- **WHEN** initial-import status is loading or fails while enabling is being reviewed
- **THEN** activation confirmation SHALL remain unavailable with loading or retry feedback
- **AND** unavailable import status SHALL NOT prevent disabling filtering
