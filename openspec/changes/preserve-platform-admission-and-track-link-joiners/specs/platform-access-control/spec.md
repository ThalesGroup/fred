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

Each Free-team link SHALL retain a bounded, paginated history of distinct people who successfully became members by enrolling through that link. Only platform administrators SHALL read the history. Each entry SHALL expose that person's current first name, last name and username and the time of the successful join. This history SHALL remain visible if the person later leaves the team or the link is suspended, revoked or expired. An explicit deletion of the link history SHALL delete its joiner entries; deletion of a user identity SHALL remove that user's entry. Opening, previewing, accepting terms, unsuccessful enrollment and a repeated enrollment while already a member SHALL NOT create a joiner entry or change the page-opening aggregate.

#### Scenario: Two links have different joiners

- **GIVEN** a team has links A and B
- **WHEN** one person successfully joins through A and another through B
- **THEN** each link's joiner list SHALL contain only the person who joined through that link

#### Scenario: Member leaves and link is revoked

- **WHEN** a person joins through a link, later leaves the team and the link is revoked or expires
- **THEN** that person's join entry SHALL remain visible on that link until the link history is deleted

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
