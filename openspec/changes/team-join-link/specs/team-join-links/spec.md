## ADDED Requirements

### Requirement: Team admins manage join links for their own team

A person holding `can_administer_members` on a non-personal team SHALL be able to create, list, copy, revoke and bulk-delete obsolete join links for that team, and list the people who joined through each link. Each link SHALL have an optional note and an optional future expiry, and SHALL follow the lifecycle of Free-team links (independent links, irreversible individual revocation, authenticated opening count, recoverable URL for an own human credential only). Join links SHALL NOT depend on the team's Free flag, joining mode or visibility, SHALL have no use cap, and SHALL remain valid when their creator loses the team admin role or leaves the team. Join links and Free-team links SHALL be listed, copied, revoked and cleaned up only through their own administration surface; platform administrators' Free-link history SHALL NOT show join links. A person without `can_administer_members` on the team SHALL NOT manage its join links.

#### Scenario: Team admin creates a link

- **GIVEN** a team admin of an `invite_only` private team
- **WHEN** they create a join link with a note and no expiry
- **THEN** a usable `/join/:token` URL SHALL be returned with no-store headers
- **AND** the link SHALL appear in the team's join-link list and not in the platform administrators' Free-link history

#### Scenario: Member without admin role tries to manage links

- **GIVEN** a team member who is not team admin
- **WHEN** they call any join-link administration route for that team
- **THEN** the request SHALL be refused and no link, token or history SHALL be returned

#### Scenario: Personal team

- **WHEN** a join link is requested for a personal team
- **THEN** creation SHALL be refused

### Requirement: Team join links never admit a person to the platform

Preview, opening, terms acceptance and enrollment through a join link SHALL check that the caller is admitted by platform access before any other effect, and before the membership is written. A non-admitted caller SHALL receive `403 team_link_requires_platform_access` without the team name, and SHALL NOT gain membership, admission, or an opening count. The join page SHALL then send them to the existing platform-access refusal screen. An admitted caller SHALL be granted `team_member` only, for themselves only, with existing CGU and suspension checks. A caller already holding a role on the team SHALL succeed without change or join event. A successful new join SHALL be recorded in the link's joiners and emit one audit event without the token.

#### Scenario: Admitted person joins

- **GIVEN** a valid join link and an admitted person who is not a member
- **WHEN** they open the link and join
- **THEN** they SHALL become `team_member` of that team and appear in the link's joiners

#### Scenario: Person without platform access opens the link

- **GIVEN** platform filtering is on and the person is not admitted
- **WHEN** they open the link
- **THEN** they SHALL be sent to the existing platform-access refusal screen without seeing the invitation page
- **AND** no team name, membership, admission or opening count SHALL be produced

#### Scenario: Link to an authorized or Free team does not admit

- **GIVEN** a join link for a team that is authorized or Free in platform access
- **WHEN** a non-admitted person tries to enroll through it
- **THEN** enrollment SHALL be refused and the team SHALL NOT become their admission source

#### Scenario: Already a member

- **WHEN** an existing member joins through a valid join link
- **THEN** the request SHALL succeed, their roles SHALL be unchanged and no join event SHALL be emitted

#### Scenario: Revoked or expired link

- **WHEN** an admitted person opens a revoked or expired join link
- **THEN** it SHALL be reported as no longer valid and no membership SHALL be granted

#### Scenario: Creator is no longer team admin

- **GIVEN** a join link created by a team admin who has since lost the role
- **WHEN** an admitted person joins through it
- **THEN** the join SHALL succeed and the remaining team admins SHALL still manage the link
