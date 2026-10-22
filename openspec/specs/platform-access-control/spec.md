# Platform Access Control Specification

## Purpose

Control platform admission using administrator-managed verified IdP claim rules and administrator-managed user and team exceptions, including bounded demonstration-team enrollment.

## Requirements

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

### Requirement: Platform access mutations remain attributable in the security audit stream

Successful administrator changes to filtering, saved rules, manual exceptions, team access and Free links SHALL emit structured security audit events with the acting administrator and relevant non-secret state or target identifiers, independently of the ordinary application log level. Link creation SHALL identify the new link without exposing its token. Bulk manual grants and T0 imports SHALL emit one summary with counts, without one event per user. A successful new Free-link team join SHALL identify the joining user, team and link. Failed or unauthorized changes SHALL NOT emit success events. Audit events SHALL NOT contain link tokens or rule claim values.

#### Scenario: Bulk grants have a bounded audit summary

- **WHEN** an administrator grants admission to a selected user list
- **THEN** the security audit stream SHALL identify the acting administrator, the number of distinct selected users and the number of newly granted users in one event
- **WHEN** the operation fails or is unauthorized
- **THEN** no successful grant audit event SHALL be emitted

#### Scenario: New Free-link membership is audited

- **WHEN** a valid Free link adds a person to a team
- **THEN** one success event SHALL identify the joining user, team and link without the token
- **WHEN** a person only opens the link or repeats enrollment while already a member
- **THEN** no new join success event SHALL be emitted

#### Scenario: T0 import is recorded once

- **WHEN** the initial T0 import completes
- **THEN** one audit summary SHALL include the acting administrator and number of exceptions actually added
- **WHEN** T0 has already completed and an administrator repeats the request
- **THEN** no new import success event SHALL be emitted

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

### Requirement: Admission policy is managed and activated by administrators

Admission administration SHALL be available in authenticated Fred deployments with enforced ReBAC after the required shared SQL migration. Its policy and activation SHALL be controlled exclusively by versioned durable administrator state. There SHALL be no admission-specific YAML, Helm, SDK environment or Pydantic configuration model, and no deployment seed. An absent authority SHALL initialize with no policy, revision zero and filtering inactive. Restarts SHALL preserve administrator state. Authentication-disabled development SHALL retain its existing behavior. Support destinations SHALL reuse frontend `contactSupportLink`.

#### Scenario: Configured nested attribute matches

- **WHEN** an administrator saves a nested claim condition in allow mode and explicitly activates filtering
- **THEN** a verified human token satisfying the condition SHALL establish rule-derived admission

#### Scenario: Attribute does not establish eligibility

- **WHEN** a selected claim is absent, empty, incompatible or fails its predicate
- **THEN** that predicate SHALL NOT match, including for negative operators; effective admission SHALL follow the combined rule, policy mode and independent sources

#### Scenario: Configuration omitted or invalid

- **WHEN** an authenticated deployment starts without any admission configuration
- **THEN** administration SHALL be available and an absent SQL authority SHALL begin with filtering inactive
- **WHEN** an administrator submits an invalid rule
- **THEN** the API SHALL reject it without changing policy or filtering

#### Scenario: UI policy survives restart

- **WHEN** services restart after an administrator saves policy or filtering state
- **THEN** all participating services SHALL continue using the saved SQL authority

#### Scenario: Keycloak directory remains authoritative

- **WHEN** admission is used with `user_directory: keycloak` or `local`
- **THEN** the directory SHALL retain profile/provisioning authority and verified human observations SHALL supply Fred admission evidence

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

### Requirement: T0 grandfathering is an explicit fixed snapshot

The system SHALL provide an administrator-triggered preview and one atomic import of existing human identities in the configured directory before filtering activation. Keycloak mode SHALL include identities known to Keycloak through federation or direct creation; local mode SHALL use Fred's `users` table. Known current matches from Fred's verified claim observations SHALL not require individual entries; unknown classifications SHALL be included conservatively without inferring token claims from directory profile fields. T0 entries SHALL be individually removable. Import completion SHALL fix the population; later registrations SHALL not be grandfathered by a retry, restart or upgrade. Activation's population review SHALL use the same configured directory population rather than an unrelated local-user subset.

#### Scenario: Existing user without a stored attribute

- **WHEN** an administrator imports T0 and an existing human in the configured directory has no reliable verified-claim classification
- **THEN** that identity SHALL receive a removable T0 exception

#### Scenario: Keycloak population differs from Fred profiles

- **GIVEN** `user_directory: keycloak` and Keycloak contains a human identity absent from Fred's `users` table
- **WHEN** an administrator previews and commits the initial import
- **THEN** the preview SHALL count that identity and the import SHALL create its T0 exception if the rule cannot reliably accept it
- **AND** a Fred-only row without a current Keycloak human identity SHALL NOT be newly imported

#### Scenario: Removed entry and later registration stay excluded

- **WHEN** T0 has completed, one imported exception is removed, and another person registers afterward
- **THEN** neither a repeated import request nor restart SHALL restore the removed entry or admit the later registration
- **AND** the completed status SHALL remain readable without scanning the directory again

#### Scenario: Concurrent imports

- **WHEN** two administrators attempt T0 import concurrently
- **THEN** only one fixed snapshot SHALL commit and the other request SHALL report the completed state

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

### Requirement: Admission is enforced at backend boundaries

The same authoritative live policy and exception state SHALL govern normal direct and delegated human requests across participating backends and replicas. A workload acting for a person SHALL use that person's complete, unconflicted and unexpired selected human evidence interpreted under the current policy mode, or independent exceptions, never the workload's claims or service role. Pure service operations SHALL retain existing authentication and authorization. JWT decoding caches SHALL NOT cache admission decisions or prevent selection of a newly configured claim for direct human requests. Only active-policy selected human evidence SHALL be persisted; whole JWTs and unrelated claim values SHALL NOT be persisted or exposed in principal responses/logs. Shared-state failures SHALL fail closed with HTTP 503 rather than be presented as definitive policy denial.

#### Scenario: Direct API or cached token cannot bypass removal

- **WHEN** a person's last exception is removed and they call another backend or replica with an already decoded JWT
- **THEN** the next request SHALL use current admission state and be refused

#### Scenario: Policy changes with a cached human token

- **WHEN** an administrator changes a selected claim, predicate, allow/block mode or all/any combination
- **THEN** subsequent direct human requests SHALL evaluate the new policy against verified token facts without restart or token renewal

#### Scenario: Delegated person loses admission

- **WHEN** a person's last admission source is withdrawn
- **THEN** delegated calls SHALL be refused even if the workload remains authorized as a service

#### Scenario: Claim-derived delegated eligibility is stale

- **WHEN** selected evidence is expired, contradictory or incompatible with the current selected paths
- **THEN** it SHALL NOT establish claim-derived eligibility

#### Scenario: A newly selected delegated claim has no observation

- **WHEN** a changed rule references a claim not present in the person's stored verified evidence
- **THEN** rule-derived admission SHALL be refused until fresh human evidence covers all selected paths, in both allow and block modes, while independent exceptions remain effective

#### Scenario: Admission authority unavailable

- **WHEN** authoritative policy, exceptions or required membership cannot be read reliably
- **THEN** normal human platform requests SHALL fail closed with HTTP 503

### Requirement: Refusal and enrollment routes keep distinct support actions

The frontend SHALL display a standalone localized refusal page for `platform_access_denied`, with contact-support wording and the existing `contactSupportLink` when configured. Refusal and other support consumers SHALL use that frontend property, available before protected bootstrap; the Free enrollment route SHALL NOT present a contact-support action. The removed backend/public `supportLink` SHALL NOT override it. Other authentication, CGU, resource-permission and transient errors SHALL retain their handling. The valid Free route and narrow own-credential status/legal/enrollment operations SHALL remain reachable to authenticated denied people without admitting normal product access.

#### Scenario: Denied bootstrap displays support

- **WHEN** a protected request returns `platform_access_denied`
- **THEN** refusal SHALL render without successful protected bootstrap or a redirect loop and its request-access destination SHALL equal configured `contactSupportLink`

#### Scenario: Free enrollment omits support

- **WHEN** an otherwise denied person opens a Free enrollment route with `contactSupportLink` configured
- **THEN** the route SHALL show no contact-support action while preserving its invitation, legal, join and retry actions as applicable

#### Scenario: Different error remains distinct

- **WHEN** a request returns 401, a CGU refusal, another resource 403 or an admission-authority 503
- **THEN** the frontend SHALL NOT convert it into platform refusal

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

### Requirement: Administrators compose understandable bounded predicates

Saved rules SHALL contain one to sixteen conditions; the editor SHALL support an empty local draft when no policy exists or all draft conditions have been removed. Testing and saving SHALL require a valid nonempty rule. Activation SHALL require a saved rule or an independent configured admission source. Existing saved conditions SHALL be loaded without fabrication or omission. The editor SHALL support these conditions combined by either all (AND) or any (OR), with localized labels. Each condition SHALL select an unambiguous claim path, operator, operand and explicit case handling. Operators SHALL include literal equals/not-equals, contains/not-contains, and advanced whole-value regex. Literal metacharacters SHALL NOT be interpreted as regex. Literal comparison SHALL default to ignoring case; administrators SHALL be able to select case-sensitive comparison. For nonempty string arrays, positive predicates SHALL match any element and negative predicates SHALL require all elements to satisfy the negation. Missing, empty, incompatible and oversized values SHALL fail every predicate. Invalid input SHALL be rejected before saving; bounded regex timeouts SHALL NOT establish rule-derived admission.

The policy SHALL expose allow/block mode above the conditions and persist it in the shared authority; absent mode SHALL retain allow behavior. Allow mode SHALL derive admission from matching rules. Block mode SHALL derive admission from nonmatching rules, including verified missing, empty or incompatible claims. Independent user/team admission sources SHALL remain sufficient in either mode. A timeout SHALL NOT derive admission. Delegated rule-derived admission SHALL require fresh, unconflicted evidence covering all selected claim paths. Preview SHALL show effective admission with readable green/red accents and a larger heading while separately explaining condition matching.

Condition controls SHALL share a compact row when space permits and reflow without horizontal overflow on narrow screens. An add-condition action SHALL open the verified-session JSON picker directly; confirming a field SHALL append one condition, while cancellation SHALL append nothing. Each existing condition SHALL show its exact selected path as text with an accessible edit action opening the same picker; an account-field dropdown SHALL NOT be shown. After field confirmation a separate popup SHALL offer explicit reuse of the current verified account value or retention of the existing operand; copying SHALL respect operand bounds and regex literal escaping. A small case toggle SHALL remain directly visible, and manual path entry SHALL NOT be shown. Validation feedback SHALL remain visible and associated with its input. Operand counters SHALL appear at 90% of the existing limit without relaxing that limit. Condition removal SHALL identify the affected condition; removing the last draft condition SHALL show the local empty state without deleting or saving the stored policy. Adding a condition SHALL be separate from testing/saving the whole draft.

#### Scenario: Literal input contains regex punctuation

- **WHEN** a contains condition uses `a.b` and a claim contains `aXb` but not `a.b`
- **THEN** that condition SHALL fail without interpreting the period as a wildcard

#### Scenario: Missing negative claim

- **WHEN** a not-contains or not-equals condition references a missing, empty or incompatible claim
- **THEN** it SHALL fail rather than grant access through absence

#### Scenario: Array contains an excluded element

- **WHEN** one array member contains the operand of a not-contains condition
- **THEN** that condition SHALL fail even when another member does not contain it

#### Scenario: Administrator chooses all or any

- **WHEN** exactly one of two valid conditions matches
- **THEN** all SHALL fail and any SHALL match

#### Scenario: Regex is invalid or exceeds its budget

- **WHEN** a draft has an invalid regex
- **THEN** save SHALL fail with field feedback and retain the current policy
- **WHEN** evaluating a saved rule exhausts its regex budget
- **THEN** the rule SHALL NOT grant access, while independent admission sources remain available

#### Scenario: Compact editing preserves draft behavior

- **WHEN** an administrator selects a field, changes a comparison or value, or selects a nested path in the explorer
- **THEN** selection and editing SHALL affect only the draft, and exact paths and explicit case handling SHALL be retained
- **AND** preview/save and concurrent-revision safeguards SHALL remain available

#### Scenario: Narrow screen or long path

- **WHEN** the editor has a narrow viewport or a long selected path
- **THEN** controls SHALL remain operable without horizontal overflow and the full selected path SHALL remain accessible

#### Scenario: Hidden counter and validation feedback

- **WHEN** a short operand has invalid input feedback
- **THEN** the counter SHALL remain hidden while feedback remains visible and associated with the input
- **WHEN** the operand reaches 90% of its limit
- **THEN** its counter SHALL become visible and native input limits SHALL remain enforced

#### Scenario: Administrator declines current value reuse

- **WHEN** a selected field has a current text value and the administrator declines copying it
- **THEN** only the draft claim path SHALL change and the existing operand SHALL remain intact
- **AND** neither choice SHALL save the policy automatically

#### Scenario: Block mode with independent exception

- **WHEN** a person matches a block rule and has a current user exception or authorized/Free membership
- **THEN** the independent source SHALL admit them

#### Scenario: Block mode with absent claim

- **WHEN** the verified token lacks the selected claim and the combined block rule does not match
- **THEN** the rule SHALL permit admission

#### Scenario: Block mode with unobserved delegated path

- **WHEN** delegated evidence does not cover a newly selected claim path
- **THEN** that evidence SHALL NOT establish rule-derived admission until a fresh direct observation

The editor SHALL present a prominent save-rule action near its title and explain that rule edits affect admission only after a successful explicit save, when filtering is active. Unsaved, saving and successful-save states SHALL be distinguishable; errors and conflicts SHALL retain the draft and SHALL NOT display successful-save feedback. The save action SHALL retain validity, busy, permission, revision and actor-lockout safeguards. Preview and field/value choices SHALL NOT save automatically.

#### Scenario: First condition starts with a field question

- **WHEN** no policy is saved and an administrator opens the editor
- **THEN** no fabricated condition SHALL be displayed and an add-condition invitation SHALL be visible
- **WHEN** the administrator chooses to add a condition
- **THEN** the own-account JSON picker SHALL open before any condition is appended

#### Scenario: Cancel condition creation

- **WHEN** an administrator dismisses the add-condition picker without confirmation
- **THEN** the draft, its condition count and its dirty state SHALL remain unchanged

#### Scenario: Confirm a new field

- **WHEN** an administrator confirms a supported field in the add-condition picker
- **THEN** exactly one draft condition SHALL be appended with that exact path
- **AND** the separate optional value prompt SHALL follow without a save or preview request

#### Scenario: Remove the last local condition

- **WHEN** an administrator removes the final draft condition
- **THEN** the empty-state invitation SHALL appear, testing and saving SHALL be disabled, and the persisted policy SHALL remain intact

#### Scenario: Explicit save makes the draft effective

- **WHEN** an administrator edits a condition or mode
- **THEN** the editor SHALL indicate unsaved changes and send no save automatically
- **WHEN** the administrator saves a valid draft successfully
- **THEN** the returned revision SHALL become the baseline and successful-save feedback SHALL be announced

#### Scenario: Save fails or conflicts

- **WHEN** a save is rejected or fails
- **THEN** unsaved edits SHALL remain available, error feedback SHALL be shown and no saved confirmation SHALL be announced

### Requirement: Administrators select claims using their own verified session

Adding a condition or editing its field SHALL open the verified-session JSON picker directly. Its localized title SHALL ask which account field to filter. The picker SHALL default to a flat JSON presentation of selectable root text attributes from the connected administrator's own verified access-token claims, with blue selectable keys and visible selection feedback; token protocol metadata SHALL remain hidden. The picker SHALL offer only the connected administrator's own fields; shared observed names/types SHALL NOT be collected or exposed. An explicit advanced-fields action SHALL expose the complete bounded searchable own JSON tree, including nested paths and string arrays. Changing display mode SHALL clear pending field selection and copied values without modifying the rule draft. Only compatible bounded string/string-array paths SHALL be selectable. In advanced mode, unsupported values SHALL be visible with an explanation; omitted oversized values SHALL be indicated. Selected keys SHALL preserve their exact nested path without interpreting literal dots. After confirming a field, administrators SHALL explicitly choose in a separate popup whether to reuse a current string or array element from their own verified account or retain the entered operand. Field selection SHALL modify only the draft; existing AND/OR, preview, save and concurrent-revision safeguards SHALL remain in effect. Exact paths SHALL be selected through the explorer rather than manual entry. The view SHALL be restricted to own human credentials and platform administration, SHALL NOT expose bearer tokens, signatures or other users' values, SHALL NOT persist or log payload values, and SHALL NOT retain the response after dismissal.

#### Scenario: Select a nested claim from the real session

- **WHEN** the administrator opens the picker and selects a nested string key in their verified payload
- **THEN** its exact path SHALL populate the draft and its real value SHALL be reusable only through an explicit action

#### Scenario: Select an array or literal dotted key

- **WHEN** the administrator selects a string array or a key containing a period
- **THEN** the condition SHALL target the whole array or literal key respectively, and copying an array value SHALL select one element

#### Scenario: Unsupported value or bounded projection

- **WHEN** a token contains a numeric/boolean claim or exceeds projection bounds
- **THEN** incompatible or unavailable fields SHALL NOT be selectable and the limitation SHALL be explained

#### Scenario: Another principal requests token values

- **WHEN** a non-administrator, workload or delegated principal requests the own-claims view
- **THEN** no token payload values SHALL be returned

#### Scenario: Choose a root account attribute without token metadata

- **WHEN** an administrator opens the own-claims picker in the default mode
- **THEN** root text account attributes SHALL be shown, while token metadata, nested paths, arrays and non-text values SHALL remain hidden

#### Scenario: Return from advanced fields

- **WHEN** an administrator selects an advanced field and switches back to simple fields
- **THEN** the hidden selection and copied operand SHALL be cleared, while saved rules and the existing draft SHALL remain unchanged

The modal SHALL scroll only its JSON region, keeping the field search, display toggle, selection and action bar stationary. The scroll region SHALL be keyboard reachable with a localized accessible name.

#### Scenario: Browse a long own payload

- **WHEN** the administrator scrolls a long JSON payload with a pointer or keyboard
- **THEN** only that region SHALL scroll and selection/confirmation controls SHALL remain reachable

#### Scenario: Open the selector on a populated platform

- **WHEN** an administrator opens the picker regardless of the number of users
- **THEN** only their own verified claims SHALL be requested and no directory/catalog scan SHALL occur

### Requirement: Admission feedback uses one welcoming card family

Admission denial, every state of the Free enrollment route and transient admission-verification failures SHALL be presented in one compact card showing the deployment's configured site display name, a single page heading that labels the card, a body and an optional footer. These states SHALL NOT use the generic error page or an error icon. The platform name SHALL always come from the configured site display name. These screens SHALL remain reachable without protected bootstrap or team/resource loading; ordinary error pages SHALL retain their existing action.

The denial screen SHALL greet the signed-in person by first name, falling back to a greeting without a name, SHALL show the signed-in account (name and email, whichever is known) and SHALL list two numbered steps: request access from support, then come back and check access. It SHALL offer sign-out, an access re-check, and a request-access action that opens `contactSupportLink` in a new tab. When `contactSupportLink` is not configured the request-access action SHALL be hidden and no alternative contact SHALL be invented. When no email is known, the steps SHALL NOT refer to a displayed address, and an account block with neither name nor email SHALL NOT be rendered.

The enrollment screen SHALL announce an invitation, show the team in its own surface and offer a single join action; it SHALL NOT display a contact-support action in any state. A preview refused as `404 free_enrollment_link_invalid` SHALL be reported as a link that is no longer valid, with guidance to ask the inviter for a new link, without a retry action and without a team name. A terms acceptance or a join refused with that same answer (a link revoked or expired while the page was open) SHALL be reported the same way. Any other failure of the preview, of the terms acceptance or of the join SHALL be reported as a temporary problem with a retry action and SHALL NOT be reported as an invalid link. Sign-out SHALL NOT appear on the enrollment route in any state.

#### Scenario: Denied or invalid enrollment route

- **WHEN** a denied person opens the refusal route or an invalid Free link
- **THEN** the screen SHALL use the shared card without normal protected product loading; the refusal SHALL offer configured support while the invalid-link card SHALL offer none

#### Scenario: Denied person is greeted and guided

- **WHEN** a denied person whose session carries a first name, a full name and an email opens the refusal route with `contactSupportLink` configured
- **THEN** the card SHALL greet them by first name, show their name and email, list the two steps, and offer sign-out, an access re-check and a request-access action targeting `contactSupportLink`

#### Scenario: Denied session lacks identity details

- **WHEN** the session carries no first name or no email
- **THEN** the greeting SHALL omit the name, the first step SHALL NOT mention a displayed address, and no empty account block SHALL be rendered

#### Scenario: Support link is not configured

- **WHEN** a denied person opens the refusal route and `contactSupportLink` is empty
- **THEN** the request-access action SHALL be absent while sign-out and the access re-check remain

#### Scenario: Invitation link is no longer valid

- **WHEN** the enrollment preview is refused with `404 free_enrollment_link_invalid`
- **THEN** the card SHALL say the link is no longer valid and to ask the inviter for a new one
- **AND** it SHALL offer no retry, join, sign-out or support action and SHALL have no footer

#### Scenario: Invitation link stops being valid while the page is open

- **WHEN** the invitation was shown and accepting the terms or joining is then refused as `404 free_enrollment_link_invalid`
- **THEN** the card SHALL say the link is no longer valid, as for a preview refused that way, without a retry, join or support action

#### Scenario: Invitation cannot be checked or joined right now

- **WHEN** the enrollment preview, the terms acceptance or the join fails for any reason other than `404 free_enrollment_link_invalid`
- **THEN** the card SHALL report a temporary problem with a retry action, no support action, and SHALL NOT state that the link is invalid

#### Scenario: Transient verification failure

- **WHEN** admission verification fails transiently
- **THEN** the same card SHALL offer a retry and configured support without falsely reporting definitive denial

#### Scenario: Invitation checking and valid states omit support

- **WHEN** a person opens a Free invitation that is still checking or is valid
- **THEN** the card SHALL show no contact-support action while retaining the join action for a valid invitation

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

### Requirement: Access administration has readable section navigation

The page SHALL provide localized Rules and Whitelist tabs using the shared Fred navigation presentation. Only the active panel SHALL be exposed visually or to keyboard and assistive navigation. The rule draft, user selection and paging SHALL survive tab changes without implicit saving or admission mutations. Whitelist SHALL retain its heading and provide localized Users and Teams sub-tabs. Import existing users and individual exceptions SHALL appear in Users; independent team authorization SHALL appear in Teams, without a separate top-level Teams tab. A top-right filtering action in the page header SHALL remain available across all tabs, without a separate Activation tab. Ordinary content, secondary explanations and section headings SHALL use a consistent readable typography scale across the page and its dialogs. Repeated explanations SHALL be removed while authorization exceptions, revocation consequences, validation and errors remain understandable.

#### Scenario: Return to an unsaved rule or selected users

- **WHEN** an administrator changes a draft or selects users, navigates to another tab and returns
- **THEN** those local changes SHALL remain and no save or authorization mutation SHALL have been sent by navigation

#### Scenario: Navigate sections using the keyboard

- **WHEN** an administrator uses arrow keys on the section strip
- **THEN** focus and selection SHALL move using the shared tab behavior and only the associated panel SHALL be exposed

#### Scenario: Read page and modal content

- **WHEN** an administrator reads conditions, selection dialogs or invitation history
- **THEN** ordinary text and secondary help SHALL use consistent readable sizes, with errors and revocation guidance retained

#### Scenario: Separate whitelist management

- **WHEN** an administrator opens Whitelist
- **THEN** its heading and Users/Teams sub-tabs SHALL be displayed
- **AND** only the selected sub-panel SHALL be exposed, with import/individual controls in Users and live team authorization in Teams

#### Scenario: Filtering action available in the header

- **WHEN** an administrator changes top-level or whitelist sub-tabs
- **THEN** the filtering action SHALL remain at the top right of the page header with the same activation guards

### Requirement: Optional invitation notes have no placeholder identity

An invitation without a note SHALL have an empty note cell in history and a generic localized joiner-dialog title. An invitation with a note SHALL retain that note in history and use it to identify the joiner dialog.

#### Scenario: Invitation without a note

- **WHEN** an administrator views an invitation whose optional note is absent
- **THEN** its note cell SHALL be empty
- **AND** its joiner dialog SHALL use a generic title without a placeholder note

#### Scenario: Invitation with a note

- **WHEN** an administrator opens the joiner history for an invitation with a note
- **THEN** the note SHALL remain visible in the invitation row and joiner-dialog title

### Requirement: Administrators filter invitation history by lifecycle status

Callers holding `organization#can_manage_platform_access` SHALL be able to filter one team's complete invitation history by All, Active, Revoked or Expired. All SHALL be the default. Results and pagination totals SHALL reflect the selected status across the entire history, not only loaded rows. Revoked SHALL take precedence over Expired, which SHALL take precedence over Suspended; unrevoked, unexpired links SHALL be Active when Link access is enabled and Suspended otherwise. Changing the filter SHALL start at the first page and SHALL NOT display rows from the previous filter as current results. Both invitation and joiner histories SHALL keep the current page visible during a background refresh, including its available actions, and SHALL show loading instead of rows from another page or filter when the selected query has no current data. Filtering SHALL NOT change validity, membership, counters or access settings. The history table SHALL have a bounded fixed height with internal row scrolling, while its header, pagination and surrounding controls remain visible. When Link access is disabled, the invitation manager SHALL state that link sharing is disabled and valid links are suspended until it is enabled again.

Opening the invitation manager SHALL refresh the team setting and first page of invitation history, even if cached. Opening a joiner dialog SHALL refresh its first page, even if cached. The joiner dialog SHALL offer a manual refresh that reloads its current page and the selected invitation-history page, including the page-opening counts. Neither dialog SHALL poll while open.

#### Scenario: Refresh joiners and opening counts on demand

- **WHEN** an administrator refreshes the joiner dialog after another person opens the link or joins the team
- **THEN** the current joiner page SHALL be reloaded
- **AND** the invitation history behind the dialog SHALL show the latest opening count after its page reloads

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

- **GIVEN** another administrator changes Link access while the invitation manager is closed
- **WHEN** an administrator opens the invitation manager
- **THEN** its disabled notice and creation controls SHALL match the current team state

### Requirement: Administrators delete obsolete invitation history explicitly

Only callers holding `organization#can_manage_platform_access` SHALL permanently delete a team's revoked or expired invitation records. The administration surface SHALL offer one bulk cleanup action with an explicit confirmation identifying the team in its title, eligible count and loss of link notes and counters. The team history SHALL remain visible behind cleanup confirmation without accepting interaction or keyboard dismissal until confirmation closes. Eligibility SHALL include the entire selected team's history independently of the displayed filter or page and SHALL be checked using server time at execution. The action SHALL preserve active links, valid suspended links, other teams' links, memberships, admission exceptions and team settings. Deletion SHALL be atomic and return the actual deleted count; repeating it with no eligible records SHALL succeed with zero. Deleted URLs SHALL remain invalid. Cleanup SHALL be available when Link access is disabled. The UI SHALL disable cleanup when no eligible records are known and refresh totals/results after success. Cancellation and failed deletion SHALL NOT announce success. Audit records SHALL identify the actor, team and deleted count without reusable tokens or visitor identities.

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

### Requirement: Team invitations use the join route

The frontend SHALL generate and recover Free-team invitation URLs at `/join/:token`, respecting its configured basename. An authenticated person, including one denied normal platform admission, SHALL reach the standalone enrollment page at that route. The previous `/join-free/:token` route SHALL not be served. Fred access logs SHALL redact the opaque token from the new route.

#### Scenario: Create and open an invitation

- **WHEN** a platform administrator creates or recovers a Free-team invitation
- **THEN** the displayed and copied URL SHALL use `/join/:token`
- **AND** opening that URL SHALL render the standalone enrollment page through the authentication redirect when needed

#### Scenario: Protect the new capability path

- **WHEN** admission denies normal platform access while a person opens `/join/:token`
- **THEN** the person SHALL remain on the enrollment route
- **AND** Fred access logs SHALL not expose the token

#### Scenario: Retired route

- **WHEN** a person requests `/join-free/:token`
- **THEN** the frontend SHALL not route that path to the enrollment page

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
