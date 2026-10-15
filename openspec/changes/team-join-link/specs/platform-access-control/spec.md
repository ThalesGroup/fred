## MODIFIED Requirements

### Requirement: Team-derived admission follows current state

Admission derived from a team SHALL require current membership and either a current authorization flag or, for the Free flag, a recorded successful enrollment of that person through one of that team's Free links. An authorization flag SHALL admit every current member. Membership added by a team administrator, by hand or through a team invite link, SHALL NOT be a Free admission source; team administrators SHALL NOT be able to grant platform access. Removing Free SHALL suspend its usable enrollment links and remove its derived admission source, while keeping existing membership and independent admission sources intact. Re-enabling Free SHALL resume links that have not expired or been revoked. Revoking a link SHALL prevent future enrollment without removing existing membership; admission withdrawal SHALL continue to follow current membership and team flags. Revoking team authorization, leaving the team or deleting the team SHALL withdraw the corresponding source on subsequent requests.

#### Scenario: Free is removed

- **WHEN** the administrator removes Free from a person's only eligible team
- **THEN** their next normal platform request SHALL be refused unless another admission source exists

#### Scenario: Membership is removed

- **WHEN** a person leaves or is removed from an authorized or Free team
- **THEN** that team's source SHALL no longer grant admission, including with the same JWT

#### Scenario: Free is restored without resurrecting revoked links

- **WHEN** Free is disabled then restored
- **THEN** previously usable links SHALL resume while expired or individually revoked links SHALL remain unusable

#### Scenario: Membership is removed while links remain reusable

- **WHEN** a person's only Free-team membership is removed
- **THEN** the same JWT SHALL no longer grant global admission
- **AND** a valid reusable invitation SHALL permit a later explicit enrollment, without silently recreating membership

#### Scenario: Member added through a team invite link in a Free team

- **GIVEN** a person admitted only by the admission rule joins a Free team through that team's invite link
- **WHEN** a platform administrator tightens the rule so it no longer matches them
- **THEN** their next platform request SHALL be refused unless another admission source exists

#### Scenario: Member added by hand in a Free team

- **WHEN** a team administrator adds a person who has no other admission source to a Free team
- **THEN** that membership SHALL NOT admit them to the platform

#### Scenario: Free-link joiner keeps access while member and Free on

- **GIVEN** a person enrolled through a Free link of a team
- **WHEN** they remain a member and Free remains enabled
- **THEN** they SHALL be admitted through that team's Free source, also in the activation preview and the whitelist sources
- **WHEN** they leave the team or Free is disabled
- **THEN** that source SHALL no longer admit them

#### Scenario: Authorized team

- **WHEN** a team is authorized
- **THEN** every current member SHALL be admitted through it, however they became a member

### Requirement: Administrators can inspect successful Free-link joiners

Each Free-team link SHALL retain a bounded, paginated history of distinct people who successfully enrolled through that link, including a person who was already a member when enrolling; this history is the evidence of the Free admission source. Only platform administrators SHALL read the history. Each entry SHALL expose that person's current first name, last name and username while the account is active, or the last recorded values with a deleted marker after account deletion, plus the time of the successful join. This history SHALL remain visible if the account is deleted, or the link is suspended, revoked or expired. When the person leaves or is removed from the team, their entries on that team's Free links SHALL be deleted, so that a later re-addition by hand or through a team invite link cannot restore the Free source; only a new Free enrollment can. An explicit deletion of the link history SHALL delete its joiner entries and with them the Free admission source they provided. Opening, previewing, accepting terms, unsuccessful enrollment and a repeated enrollment by a person already recorded on that link SHALL NOT create a joiner entry or change the page-opening aggregate. Team invite links SHALL NOT create joiner entries.

#### Scenario: Two links have different joiners

- **GIVEN** a team has links A and B
- **WHEN** one person successfully joins through A and another through B
- **THEN** each link's joiner list SHALL contain only the person who joined through that link

#### Scenario: Link is revoked while the joiner stays a member

- **WHEN** a person joins through a link and the link is later revoked or expires
- **THEN** that person's join entry SHALL remain visible on that link until the link history is deleted

#### Scenario: Member leaves and link is revoked

- **WHEN** a person joins through a link, later leaves or is removed from the team, and the link is revoked or expires
- **THEN** that person's join entry SHALL be deleted when they leave, and the Free source SHALL NOT return without a new Free enrollment

#### Scenario: Removed joiner is re-added by hand

- **GIVEN** a person joined a Free team through its link, which was later revoked
- **WHEN** they are removed from the team and a team administrator adds them back by hand
- **THEN** their join entry SHALL be gone and the team SHALL NOT admit them
- **WHEN** they instead enroll again through a valid Free link of that team
- **THEN** they SHALL be admitted through that team's Free source

#### Scenario: Joiner account is deleted

- **WHEN** a person joins through a link and their account is later deleted
- **THEN** the join entry SHALL remain visible with their last recorded username and names, join time, and a deleted marker
- **AND** a missing local user row SHALL NOT erase or hide the entry

#### Scenario: Opening or repeat enrollment

- **WHEN** a person opens a link without joining, enrollment fails, or a person already recorded on that link enrolls again
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
- **AND** people admitted only through those entries SHALL lose that Free admission source

#### Scenario: Existing member enrolls through a Free link

- **GIVEN** a person added to a Free team by hand
- **WHEN** they successfully enroll through one of that team's Free links
- **THEN** a joiner entry SHALL be recorded and the team SHALL become their Free admission source
