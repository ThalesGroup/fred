## MODIFIED Requirements

### Requirement: Platform administrators cannot be denied by admission filtering

An active person holding the current `organization#can_manage_platform_access` permission SHALL pass platform admission when filtering is active, independently of rule results and individual or team exceptions. This admission SHALL use the authoritative current role on direct and delegated requests; it SHALL not grant a role, team membership or resource permission. A removed role SHALL stop providing this admission source on the next request. An unavailable authorization authority SHALL remain an availability failure, not a definitive admission denial.

#### Scenario: Administrator is outside every configured source

- **GIVEN** filtering is active and a platform administrator matches no saved rule or exception
- **WHEN** that administrator makes a direct or delegated human request
- **THEN** platform admission SHALL pass while ordinary authorization remains enforced

#### Scenario: Platform role is removed

- **GIVEN** an administrator was admitted only through the platform role
- **WHEN** that role is removed
- **THEN** the next direct or delegated human request SHALL no longer use the administrator admission source

#### Scenario: Unavailable role authority

- **WHEN** the current `organization#can_manage_platform_access` permission cannot be checked reliably
- **THEN** admission SHALL fail with the existing availability error rather than inventing an administrator role or returning a policy denial

### Requirement: Administrators can inspect successful Free-link joiners

Each Free-team link SHALL retain a bounded, paginated history of distinct people who successfully became members by enrolling through that link. Only callers holding `organization#can_manage_platform_access` SHALL read the history. Each entry SHALL expose that person's current first name, last name and username while the account is active, or the last recorded values with a deleted marker after account deletion, plus the time of the successful join. This history SHALL remain visible if the person later leaves the team, the account is deleted, or the link is suspended, revoked or expired. An explicit deletion of the link history SHALL delete its joiner entries. Opening, previewing, accepting terms, unsuccessful enrollment and a repeated enrollment while already a member SHALL NOT create a joiner entry or change the page-opening aggregate.

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

### Requirement: Admission sources are independent of resource permissions

When filtering is active, the system SHALL admit a non-suspended person if their verified claim evaluation permits admission under the current allow/block mode, they have a current individual exception, they are a current member of an authorized team (including a Free team), or they hold the current `organization#can_manage_platform_access` permission. Ordinary public-team visibility SHALL not count as membership. Admission SHALL neither grant a platform role nor extend team or resource permissions. Account suspension and required CGU acceptance SHALL still apply.

#### Scenario: New non-matching person is refused

- **WHEN** a new person is not admitted by the current rule mode and has no individual exception, eligible membership or platform-access-management permission
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

### Requirement: Platform administrators manage live exceptions

Only people holding the `organization#can_manage_platform_access` permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using the configured user directory for identity lookup and Fred for admission state, team authorization and Free-team controls, filtering state, effective admission sources displayed by type and team name without team UIDs, own-session claim selection, rule editing and draft preview. In `user_directory: keycloak`, both federated identities known to Keycloak and identities created directly there SHALL be selectable before their first Fred request; in `user_directory: local`, identities SHALL come from Fred's `users` table. Team administrators and team managers SHALL NOT obtain this authority through their existing roles. Removing an individual exception SHALL NOT remove an identity or revoke independent team sources. Rule updates SHALL be explicit, atomic and versioned; stale concurrent saves SHALL return a conflict without overwriting another administrator's changes. Preview SHALL NOT change filtering, policy, T0, membership or evidence selected only by the proposed rule.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** an administrator adds an existing identity from the configured directory or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Administrator authorizes a selected user list

- **WHEN** a platform administrator selects any nonempty list of existing directory identities and grants admission
- **THEN** the operation SHALL atomically add removable manual exceptions without overwriting existing sources
- **WHEN** the list includes an unknown identity or is submitted by a non-platform administrator
- **THEN** no exceptions SHALL be granted

#### Scenario: Keycloak identity has not visited Fred

- **GIVEN** `user_directory: keycloak` and a human identity created directly in Keycloak or made known there by federation
- **WHEN** the identity has no Fred profile row and an administrator searches and selects it
- **THEN** the directory profile SHALL be displayed and the administrator SHALL be able to grant it an individual exception

#### Scenario: Local directory remains selectable

- **GIVEN** `user_directory: local`
- **WHEN** an administrator searches, lists, or grants an individual exception
- **THEN** Fred's local identities SHALL supply the profile and unknown local identities SHALL be rejected
- **AND** ID-only rows created as Keycloak exception references SHALL NOT become local identities

#### Scenario: Directory profile changes or disappears

- **WHEN** a directory profile changes after an exception was granted
- **THEN** a later whitelist read SHALL show the current directory profile for the same identity id without changing the exception
- **WHEN** an existing exception's identity cannot be resolved
- **THEN** the entry SHALL remain visible with its identity id and origin, and SHALL remain removable

#### Scenario: Directory lookup fails

- **WHEN** the configured directory is unavailable during a search, grant validation, or initial-import preparation
- **THEN** the operation SHALL report an availability error and SHALL NOT treat an empty fallback as authoritative or partially grant exceptions

#### Scenario: Keycloak search is too broad

- **WHEN** an add-user query matches more than 1000 raw Keycloak records
- **THEN** an exact username or email match SHALL remain selectable
- **AND** otherwise the search SHALL request a narrower query without offering an incomplete result as the full population

#### Scenario: Administrator finds their own sources by identity ID

- **WHEN** an administrator previews their own admission sources from the rule editor
- **THEN** the lookup SHALL use the connected identity ID rather than a potentially broad username search

#### Scenario: Leaving an allowed or Free team revokes its global source

- **WHEN** a person leaves or is removed from an allowed or Free team
- **THEN** the next direct, cached-token or delegated request on any participating reader SHALL no longer use that team for platform admission
- **AND** the person SHALL be refused when no independent source remains, while other grants and ordinary membership of other teams remain unchanged

#### Scenario: Unauthorized administrative call

- **WHEN** an ordinary person, team administrator or team manager requests claim discovery, preview, policy updates or exception administration
- **THEN** the call SHALL be refused and admission state SHALL remain unchanged

#### Scenario: Administrator sees provenance

- **WHEN** an administrator lists allowed users
- **THEN** individual entries SHALL identify manual or T0 origin and derived entries SHALL identify each authorized or Free team

#### Scenario: Preview explains an unsaved rule

- **WHEN** an administrator tests a draft against their verified token
- **THEN** the UI SHALL show per-condition results, missing or incompatible claim explanations, the aggregate rule result and whether they would be admitted with filtering active including independent sources, without saving the draft

#### Scenario: Two administrators save concurrently

- **WHEN** a save uses an older revision than the active policy
- **THEN** the system SHALL return HTTP 409 and retain the newer policy, while the UI preserves the unsaved draft and explains the conflict

User rows SHALL show identifier, first name and last name using the team-member table presentation. The whitelist SHALL list individual exceptions only, and its search and add dialog SHALL use the configured directory's current profiles. Searches and pages SHALL not show stale results from a previous request. Large selections SHALL use bounded work and grants SHALL remain atomic.

#### Scenario: Grant more than 100 people

- **WHEN** an administrator submits more than 100 known identities
- **THEN** all missing exceptions SHALL be added atomically, duplicate identities ignored and existing origins preserved
- **WHEN** an identity in a later batch is unknown
- **THEN** the complete operation SHALL roll back

### Requirement: Free-team links admit only their authenticated caller

A caller holding `organization#can_manage_platform_access` SHALL be able to enable Free enrollment and generate multiple independent opaque revocable links for one existing non-personal team. Each link SHALL have an optional note and optional timezone-aware expiry; omitted expiry SHALL mean no time limit. Generating a link SHALL NOT invalidate earlier links. Revocation SHALL be individual and irreversible; expired or revoked links SHALL fail preview, legal acceptance and enrollment. Only generation and an explicit own-human authorized recovery action SHALL return the plaintext token, with no-store response headers. A signed-in person otherwise denied by admission filtering SHALL be able to use that link to join that team. A successful enrollment SHALL grant only the existing member relation to the caller, retain CGU and suspension checks, and expose the Free-team admission source in administration. The enrollment surface SHALL not reveal directories, normal product bootstrap or arbitrary private-team data.

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

### Requirement: Administrators manage independent Free-link history

Only callers holding `organization#can_manage_platform_access` SHALL create, list and revoke Free-team links. The platform administration Teams registry SHALL expose the Free toggle and Manage links action for each eligible team; ordinary team managers SHALL NOT see these controls or issue admission administration queries. Platform access SHALL group individual exceptions and independent team authorization in its Whitelist panel and SHALL NOT duplicate Free/link controls. The bounded paginated history SHALL expose the link identifier, note, creation and expiry dates, revocation state, suspension state and authenticated opening count, without reusable tokens or visitor identity. Administrators SHALL be able to inspect and revoke links while Free is disabled. Manage links SHALL open on the bounded invitation list with a Create link action; note and expiry inputs SHALL appear only in a separate creation view. That view SHALL place the optional note before optional expiration and reuse the platform KPI selector presentation, with a single future date/time input, future duration shortcuts, a No expiration option and Apply. The date draft SHALL prevent creation until applied or dismissed; Escape SHALL close only the selector and restore trigger focus. Empty expiration SHALL mean no expiry; invalid or past expiration SHALL prevent creation without losing the note. Generation success SHALL show the original URL in the platform's monospace font and an immediately available Copy URL action, and SHALL attempt to copy that URL to the clipboard automatically.

History SHALL use an explicit Copy URL action that recovers the original token and attempts clipboard writing without generating another link. Clipboard success SHALL be announced only after the write succeeds through temporary feedback on the corresponding Copy URL button and a screen-reader status, without changing the dialog layout. If clipboard writing is unavailable or rejected, the UI SHALL retain the usable URL with a clear manual-copy fallback; a copy failure SHALL NOT be presented as generation failure or cause another invitation to be created. Creation/recovery URL state SHALL remain transient and clear on manager dismissal, without logging URLs or retaining reusable mutation payloads.

The opening-count column SHALL use the short localized label Accesses (Accès) without showing the last-access timestamp, and explain that it counts authenticated page openings rather than unique users, anonymous clicks or message delivery. The UI SHALL identify manual sharing and explicit URL recovery; it SHALL NOT claim message delivery.

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

#### Scenario: Open history without a creation form

- **WHEN** an administrator opens Manage links
- **THEN** the invitation list and Create link action SHALL appear without note or expiration inputs
- **WHEN** the administrator chooses Create link
- **THEN** a separate creation form SHALL appear with note followed by expiration

#### Scenario: Cancel creation

- **WHEN** the administrator cancels the creation form
- **THEN** the history SHALL remain available and no invitation SHALL be generated

#### Scenario: Created invitation is ready to copy

- **WHEN** generation succeeds
- **THEN** the usable invitation URL and Copy URL action SHALL be shown with successful creation feedback
- **AND** the displayed URL SHALL use the platform's monospace font
- **AND** the UI SHALL attempt to copy that URL to the clipboard automatically
- **AND** clipboard success SHALL be announced only after the write succeeds; creation SHALL NOT claim message delivery

#### Scenario: Copy from invitation history

- **WHEN** an own-human platform administrator chooses Copy URL on a recoverable row
- **THEN** the existing original URL SHALL be recovered and written to the clipboard
- **AND** successful copy feedback SHALL appear only after clipboard confirmation, without changing link validity or counts

#### Scenario: Clipboard access is refused

- **WHEN** the browser refuses clipboard access after generation or recovery
- **THEN** the usable URL SHALL remain available for manual copying with specific feedback
- **AND** no replacement invitation SHALL be created and the failure SHALL NOT be announced as a failed creation

#### Scenario: Delayed clipboard result after dismissal

- **WHEN** an administrator dismisses the generated URL or begins a newer copy while a clipboard write is pending
- **THEN** a later result from the earlier write SHALL NOT reopen the dismissed dialog or replace the newer copy feedback

#### Scenario: Short counter heading retains its meaning

- **WHEN** the invitation history displays Accesses
- **THEN** the displayed value SHALL remain the authenticated opening aggregate and the counting definition SHALL remain available

#### Scenario: Invalid creation input retains the draft

- **WHEN** expiration is invalid or no longer in the future, or generation fails
- **THEN** the creation form SHALL retain the note and date with actionable feedback, without closing the manager

### Requirement: Administrators filter invitation history by lifecycle status

Callers holding `organization#can_manage_platform_access` SHALL be able to filter one team's complete invitation history by All, Active, Revoked or Expired. All SHALL be the default. Results and pagination totals SHALL reflect the selected status across the entire history, not only loaded rows. Revoked SHALL take precedence over Expired, which SHALL take precedence over Suspended; unrevoked, unexpired links SHALL be Active when Link access is enabled and Suspended otherwise. Changing the filter SHALL start at the first page and SHALL NOT display rows from the previous filter as current results. Filtering SHALL NOT change validity, membership, counters or access settings. The history table SHALL have a bounded fixed height with internal row scrolling, while its header, pagination and surrounding controls remain visible. When Link access is disabled, the invitation manager SHALL state that link sharing is disabled and valid links are suspended until it is enabled again.

#### Scenario: Filter beyond the first page

- **WHEN** an administrator selects Expired and matching links exist beyond the previously loaded page
- **THEN** the result pages and total SHALL include all and only expired links for the selected team

#### Scenario: Revoked link also expires

- **WHEN** an expired link has been revoked
- **THEN** it SHALL appear under Revoked and All, not under Expired

#### Scenario: Link access is disabled

- **WHEN** a team's Link access is disabled
- **THEN** its unrevoked, unexpired links SHALL appear in All with grayscale rows at reduced opacity, rather than appearing under Active
- **AND** those rows SHALL display Suspended in the visible Status column
- **AND** the manager SHALL explain that Link access is disabled and valid invitations cannot be used until it is enabled again
- **AND** no separate Suspended filter SHALL be offered, while copying, revocation and an accessible status remain available

#### Scenario: Another administrator changes Link access

- **WHEN** the Link access setting changes while an administrator keeps the invitation manager open
- **THEN** the manager SHALL refresh the setting so its disabled notice and creation controls match the current team state

### Requirement: Administrators delete obsolete invitation history explicitly

Only callers holding `organization#can_manage_platform_access` SHALL permanently delete a team's revoked or expired invitation records. The administration surface SHALL offer one bulk cleanup action with an explicit confirmation identifying the team in its title, eligible count and loss of link notes and counters. The team history SHALL remain visible behind cleanup confirmation without accepting interaction or keyboard dismissal until confirmation closes. Eligibility SHALL include the entire selected team's history independently of the displayed filter or page and SHALL be checked using server time at execution. The action SHALL preserve active links, valid suspended links, other teams' links, memberships, admission exceptions and team settings. Deletion SHALL be atomic and return the actual deleted count; repeating it with no eligible records SHALL succeed with zero. Deleted URLs SHALL remain invalid. Cleanup SHALL be available when Link access is disabled. The UI SHALL disable cleanup when no eligible records are known, hide stale history during refresh, and refresh totals/results after success. Cancellation and failed deletion SHALL NOT announce success. Audit records SHALL identify the actor, team and deleted count without reusable tokens or visitor identities.

#### Scenario: Confirm cleanup from a filtered page

- **WHEN** an administrator confirms cleanup while displaying Active links or a later history page
- **THEN** all revoked or expired records for that team SHALL be deleted, including records outside the displayed results
- **AND** currently valid links and existing team members SHALL remain unchanged

#### Scenario: Preserve a suspended invitation

- **WHEN** cleanup runs while Link access is disabled and an invitation remains unrevoked and unexpired
- **THEN** that invitation SHALL remain recoverable and resume when Link access is enabled

#### Scenario: A link expires during confirmation

- **WHEN** an invitation reaches its expiry before cleanup executes
- **THEN** server-time eligibility SHALL include it and the response SHALL report the actual deleted count

#### Scenario: Cancel or fail cleanup

- **WHEN** the administrator cancels confirmation or the deletion transaction fails
- **THEN** no records SHALL be removed and no success SHALL be announced

#### Scenario: Ordinary team manager attempts cleanup

- **WHEN** a person without platform-access-management permission requests cleanup
- **THEN** the request SHALL be refused without removing history or changing admission

## ADDED Requirements

### Requirement: Platform access administration is delegable without team management

The `platform_access_manager` role SHALL hold `organization#can_manage_platform_access`, covering all Platform Access administration: filtering, claim rules, user and team whitelist entries, T0, Free enrollment and Free links. It SHALL have read-only team registry access needed to locate Free controls, but SHALL NOT grant unrelated platform administration, user administration, platform role assignment, team registry mutation or team resource permissions. The existing `platform_admin` SHALL retain the complete Platform Access authority. The `team_manager` role alone SHALL NOT grant any Platform Access or Free enrollment authority. A Free enrollment link created by a platform access manager SHALL retain its caller-only membership and Free admission behavior.

#### Scenario: Platform access manager administers all admission controls

- **WHEN** a caller holds only `platform_access_manager`
- **THEN** they SHALL be able to manage filtering, rules, individual and team whitelist entries, T0, Free settings and Free links
- **AND** an unrelated platform reset, user-administration, role-assignment or team-registry mutation SHALL be refused

#### Scenario: Team manager cannot administer admission

- **WHEN** a caller holds only `team_manager` and tries to change Free, create or inspect a Free link, change a team whitelist entry, filtering, policy, an individual exception or T0
- **THEN** the request SHALL be refused without changing admission state or disclosing link history or a reusable token

#### Scenario: Delegated Free enrollment retains its scope

- **WHEN** a person uses a valid Free link created by a platform access manager
- **THEN** only that person SHALL gain team membership and the existing Free admission source
