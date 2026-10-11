## MODIFIED Requirements

### Requirement: Free-team links admit only their authenticated caller

A platform administrator SHALL be able to enable Free enrollment and generate multiple independent opaque revocable links for one existing non-personal team. Each link SHALL have an optional note and optional timezone-aware expiry; omitted expiry SHALL mean no time limit. Generating a link SHALL NOT invalidate earlier links. Revocation SHALL be individual and irreversible; expired or revoked links SHALL fail preview, legal acceptance and enrollment. Only generation and an explicit own-human platform-administrator recovery action SHALL return the plaintext token, with no-store response headers. A signed-in person otherwise denied by admission filtering SHALL be able to use that link to join that team. A successful enrollment SHALL grant only the existing member relation to the caller, retain CGU and suspension checks, and expose the Free-team admission source in administration. The enrollment surface SHALL not reveal directories, normal product bootstrap or arbitrary private-team data.

#### Scenario: Denied external person joins a Free team

- **WHEN** a non-matching person signs in through a valid Free-team link and meets suspension and CGU requirements
- **THEN** they SHALL become a member of that team and gain admission through that Free-team source

#### Scenario: Link cannot select another person or stronger role

- **WHEN** enrollment requests name another person, another team or an administrative role
- **THEN** the request SHALL not grant that identity, team or role

#### Scenario: Ordinary authorized team stays closed

- **WHEN** an administrator authorizes a team without enabling Free enrollment
- **THEN** its existing joining policy SHALL remain unchanged and denied people SHALL not use its ordinary join endpoint to bypass admission

#### Scenario: Old or disabled link is refused

- **WHEN** a link is invalid, revoked, expired, or belongs to a team whose Free flag is disabled or whose registry entry was deleted
- **THEN** enrollment SHALL be refused without granting membership or admission

### Requirement: Team-derived admission follows current state

Admission derived from a team SHALL require both a current authorization or Free flag and current membership. Removing Free SHALL suspend its usable enrollment links and remove its derived admission source, while keeping existing membership and independent admission sources intact. Re-enabling Free SHALL resume links that have not expired or been revoked. Revoking a link SHALL prevent future enrollment without removing existing membership; admission withdrawal SHALL continue to follow current membership and team flags. Revoking team authorization, leaving the team or deleting the team SHALL withdraw the corresponding source on subsequent requests.

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

## ADDED Requirements

### Requirement: Administrators manage independent Free-link history

Only platform administrators SHALL create, list and revoke Free-team links. The bounded paginated history SHALL expose the link identifier, note, creation and expiry dates, revocation state, suspension state and authenticated opening count/last-opening time, without reusable tokens or visitor identity. Administrators SHALL be able to inspect and revoke links while Free is disabled. The UI SHALL identify manual sharing and explicit URL recovery; it SHALL NOT claim message delivery.

#### Scenario: Generate a second invitation

- **WHEN** an administrator creates another link with a note and optional future expiry
- **THEN** both invitations SHALL remain independently usable until their own revocation or expiry
- **AND** their purposes, lifecycle and opening counts SHALL appear in history

#### Scenario: Ordinary team manager attempts link administration

- **WHEN** a person without platform-management authority calls link administration
- **THEN** no link history, reusable token or mutation SHALL be granted

#### Scenario: Copy a previously generated invitation

- **WHEN** an own-human platform administrator requests a usable invitation URL from history
- **THEN** the original token SHALL be returned without changing its validity or opening count
- **AND** ordinary listing and workload/delegated requests SHALL NOT expose that token

#### Scenario: Revoke one invitation

- **WHEN** one invitation is revoked
- **THEN** other valid invitations SHALL remain usable and existing team membership SHALL remain intact

### Requirement: Authenticated enrollment-page openings use link aggregates

The frontend SHALL record each authenticated enrollment-page opening using its own credential. Aggregate opening count and last-opening time SHALL be stored on the link row without a separate visit table. The frontend SHALL submit one signal per page opening, including under duplicate React effects; every accepted opening POST SHALL increment the count. A subsequent new page opening SHALL count again. Preview, terms acceptance and enrollment SHALL NOT increment the opening count themselves. Invalid, expired, revoked or suspended links SHALL NOT record openings. Visitor identities, IP addresses and account payloads SHALL NOT be stored as analytics.

#### Scenario: Duplicate frontend effect

- **WHEN** React repeats the authenticated page effect for the same mounted link
- **THEN** the frontend SHALL submit exactly one opening POST

#### Scenario: New opening without enrollment

- **WHEN** the authenticated person opens the invitation again on a new page
- **THEN** the count SHALL increase once regardless of whether they join

#### Scenario: Revocation races with enrollment

- **WHEN** revocation commits before a concurrent enrollment mutation checks the link
- **THEN** no membership SHALL be granted through that invitation
