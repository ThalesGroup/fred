## ADDED Requirements

### Requirement: Team admins control one invite link for their team

A person holding `can_administer_members` on a non-personal team SHALL be able to read, enable, pause and regenerate that team's single invite link, using their own human credential. The first enabling SHALL create the link. Pausing and resuming SHALL keep the same URL. Regenerating SHALL make the previous URL permanently invalid and return a new, enabled URL. The link SHALL have no expiry or use cap, SHALL NOT depend on the team's Free flag, joining mode or visibility, and SHALL remain valid when its creator loses the team admin role. Team links SHALL NOT appear in, or be managed through, platform administrators' Free-link administration. A person without `can_administer_members` on the team SHALL NOT read or change its invite link.

#### Scenario: Enable, pause and resume

- **GIVEN** a team admin of a private `invite_only` team without an invite link
- **WHEN** they enable the invitation, pause it, then enable it again
- **THEN** the first enabling SHALL return a `/join/:token` URL
- **AND** pausing and resuming SHALL return that same URL, reported as disabled then enabled

#### Scenario: Regenerate

- **WHEN** a team admin generates a new link
- **THEN** a different URL SHALL be returned, enabled
- **AND** the previous URL SHALL be refused as no longer valid

#### Scenario: Member without admin role

- **WHEN** a team member who is not team admin reads or changes the invite link
- **THEN** the request SHALL be refused without returning a URL

#### Scenario: Free-link administration

- **WHEN** a platform administrator lists, reveals, revokes or cleans up the team's Free links
- **THEN** the team invite link SHALL NOT be listed or affected

### Requirement: Team invite links never admit a person to the platform

On a valid team invite link, preview, opening, terms acceptance and enrollment SHALL check that the caller is admitted by platform access before any membership, opening count, terms acceptance or team-name disclosure. A non-admitted caller SHALL receive `403 team_link_requires_platform_access` without the team name, and the join page SHALL send them to the existing platform-access refusal screen. A paused or replaced link SHALL be answered as an invalid link, shown by the join page's existing "no longer valid" state, without the team name or any count. An admitted caller SHALL be granted `team_member` only, for themselves only, with existing terms and suspension checks. A caller already holding a role SHALL succeed without change or join event.

#### Scenario: Admitted person joins

- **GIVEN** an enabled invite link and an admitted person who is not a member
- **WHEN** they open the link and join
- **THEN** they SHALL become `team_member` of that team

#### Scenario: Person without platform access

- **GIVEN** platform filtering is on and the person is not admitted
- **WHEN** they open an enabled invite link
- **THEN** they SHALL be sent to the platform-access refusal screen
- **AND** no team name, membership, admission or opening count SHALL be produced

#### Scenario: Authorized or Free team does not admit

- **GIVEN** an invite link for a team that is authorized or Free in platform access
- **WHEN** a non-admitted person tries to join through it
- **THEN** the join SHALL be refused and the team SHALL NOT become their admission source

#### Scenario: Paused link

- **WHEN** someone opens an invite link whose invitation is paused
- **THEN** the join page SHALL show that the invitation link is no longer valid, without the team name

#### Scenario: Already a member

- **WHEN** an existing member joins through the invite link
- **THEN** the request SHALL succeed, their roles SHALL be unchanged and no join event SHALL be emitted
