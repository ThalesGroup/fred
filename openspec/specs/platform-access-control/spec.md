# Platform Access Control Specification

## Purpose

Control platform admission using administrator-managed verified IdP claim rules and administrator-managed user and team exceptions, including bounded demonstration-team enrollment.

## Requirements

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

When filtering is active, the system SHALL admit a non-suspended person if their verified claim evaluation permits admission under the current allow/block mode, they have a current individual exception, or they are a current member of an authorized team, including a Free team. Ordinary public-team visibility SHALL not count as membership. Admission SHALL neither grant a platform role nor extend team or resource permissions. Account suspension and required CGU acceptance SHALL still apply.

#### Scenario: New non-matching person is refused

- **WHEN** a new person is not admitted by the current rule mode and has no individual exception or eligible membership
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

Only people holding the existing platform-management permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using Fred's local users, team authorization and Free-team controls, filtering state, effective admission sources with team identifiers, observed claim selection, rule editing and draft preview. Team administrators and team managers SHALL NOT obtain this authority through their existing roles. Removing an individual exception SHALL NOT remove an identity or revoke independent team sources. Rule updates SHALL be explicit, atomic and versioned; stale concurrent saves SHALL return a conflict without overwriting another administrator's changes. Preview SHALL NOT change filtering, policy, T0, membership or evidence selected only by the proposed rule.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** an administrator adds an existing Fred user or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Administrator authorizes a selected user list

- **WHEN** a platform administrator selects one to 100 existing Fred users and grants admission
- **THEN** the operation SHALL atomically add removable manual exceptions without overwriting existing sources
- **WHEN** the list includes an unknown user, exceeds the bound or is submitted by a non-platform administrator
- **THEN** no exceptions SHALL be granted

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

### Requirement: T0 grandfathering is an explicit fixed snapshot

The system SHALL provide an administrator-triggered preview and one atomic import of existing human users in Fred's database before filtering activation. Known current claim matches SHALL not require individual entries; unknown classifications SHALL be included conservatively so missing profile data does not lock out existing users. T0 entries SHALL be individually removable. Import completion SHALL fix the population; later registrations SHALL not be grandfathered by a retry, restart or upgrade.

#### Scenario: Existing user without a stored attribute

- **WHEN** an administrator imports T0 and an existing Fred human has no reliable attribute classification
- **THEN** that user SHALL receive a removable T0 exception

#### Scenario: Removed entry and later registration stay excluded

- **WHEN** T0 has completed, one imported exception is removed, and another person registers afterward
- **THEN** neither a repeated import request nor restart SHALL restore the removed entry or admit the later registration

#### Scenario: Concurrent imports

- **WHEN** two administrators attempt T0 import concurrently
- **THEN** only one fixed snapshot SHALL commit and the other request SHALL report the completed state

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

### Requirement: Refusal and enrollment screens remain reachable

The frontend SHALL display a standalone localized refusal page for `platform_access_denied`, with contact-support wording and the existing `contactSupportLink` when configured. Refusal, Free enrollment and other support consumers SHALL use the same frontend property, available before protected bootstrap. The removed backend/public `supportLink` SHALL NOT override it. Other authentication, CGU, resource-permission and transient errors SHALL retain their handling. The valid Free route and narrow own-credential status/legal/enrollment operations SHALL remain reachable to authenticated denied people without admitting normal product access.

#### Scenario: Denied bootstrap displays support

- **WHEN** a protected request returns `platform_access_denied`
- **THEN** refusal SHALL render without successful protected bootstrap or a redirect loop and its support destination SHALL equal configured `contactSupportLink`

#### Scenario: Free enrollment reuses support

- **WHEN** an otherwise denied person opens a Free enrollment route
- **THEN** its support destination SHALL equal the refusal and profile support destinations

#### Scenario: Different error remains distinct

- **WHEN** a request returns 401, a CGU refusal, another resource 403 or an admission-authority 503
- **THEN** the frontend SHALL NOT convert it into platform refusal

### Requirement: Activation and migration are explicit

An absent admission authority SHALL initialize with filtering inactive until explicit administrator activation. Activation SHALL require a valid nonempty rule and SHALL be refused if the acting administrator would lose their last admission source. Saving a policy or changing access exceptions while filtering is active SHALL apply the same actor safeguard atomically. Existing root bootstrap safeguards SHALL remain intact. Activation concurrent with a nonempty legacy-file gate SHALL be rejected; readers SHALL refuse an active conflicting gate. Policy, imported entries and membership SHALL survive restarts and temporary filtering disablement.

#### Scenario: Upgrade does not silently activate filtering

- **WHEN** operators deploy the required migration with empty admission state
- **THEN** filtering SHALL remain inactive until a rule is prepared and an administrator explicitly activates it

#### Scenario: Administrator would lock themselves out

- **WHEN** activation, a policy save or an exception mutation would withdraw the actor's last admission source
- **THEN** the operation SHALL be refused with an actionable explanation and leave prior state intact

#### Scenario: Rule is not configured

- **WHEN** an administrator attempts activation without a valid nonempty rule
- **THEN** activation SHALL be refused without changing the filtering state

#### Scenario: Conflicting whitelist modes

- **WHEN** an administrator attempts activation while a nonempty legacy file gate is active
- **THEN** activation SHALL be refused without changing state, and readers SHALL fail closed if conflicting active state exists

### Requirement: Administrators compose understandable bounded predicates

The editor SHALL support one to sixteen conditions combined by either all (AND) or any (OR), with localized labels. Each condition SHALL select an unambiguous claim path, operator, operand and explicit case handling. Operators SHALL include literal equals/not-equals, contains/not-contains, and advanced whole-value regex. Literal metacharacters SHALL NOT be interpreted as regex. Literal comparison SHALL default to ignoring case; administrators SHALL be able to select case-sensitive comparison. For nonempty string arrays, positive predicates SHALL match any element and negative predicates SHALL require all elements to satisfy the negation. Missing, empty, incompatible and oversized values SHALL fail every predicate. Invalid input SHALL be rejected before saving; bounded regex timeouts SHALL NOT establish rule-derived admission.

The policy SHALL expose allow/block mode above the conditions and persist it in the shared authority; absent mode SHALL retain allow behavior. Allow mode SHALL derive admission from matching rules. Block mode SHALL derive admission from nonmatching rules, including verified missing, empty or incompatible claims. Independent user/team admission sources SHALL remain sufficient in either mode. A timeout SHALL NOT derive admission. Delegated rule-derived admission SHALL require fresh, unconflicted evidence covering all selected claim paths. Preview SHALL show effective admission with readable green/red accents and a larger heading while separately explaining condition matching.

Condition controls SHALL share a compact row when space permits and reflow without horizontal overflow on narrow screens. A labeled left-aligned dropdown SHALL expose root text field names and the exact selected path, with an entry for the detailed session explorer. After field confirmation a separate popup SHALL offer explicit reuse of the current verified account value or retention of the existing operand; copying SHALL respect operand bounds and regex literal escaping. A small case toggle SHALL remain directly visible, and manual path entry SHALL NOT be shown. Validation feedback SHALL remain visible and associated with its input. Operand counters SHALL appear at 90% of the existing limit without relaxing that limit. Condition removal SHALL identify the affected condition and SHALL preserve at least one condition. Adding a condition SHALL be separate from testing/saving the whole draft.

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

### Requirement: Claim discovery exposes names without a personal-data inventory

The system SHALL discover bounded nested string/string-array claim paths from verified human access tokens and expose observed names and supported types only to platform administrators. The catalog SHALL NOT expose other users' claim values, JWTs or workload claims, and SHALL NOT claim to enumerate the IdP schema. The editor SHALL distinguish observed names from universal availability and permit entry of an unambiguous path not yet observed. Traversal, catalog growth and retained token facts SHALL be bounded; exceeding these bounds SHALL NOT produce a positive match for unavailable facts.

#### Scenario: Another human reveals a custom path

- **WHEN** a verified human token contains a supported custom nested claim
- **THEN** its path SHALL become selectable without Helm changes and without exposing that person's value

#### Scenario: Workload or unverified token supplies names

- **WHEN** a workload token or unverified input contains additional claims
- **THEN** it SHALL NOT populate the human claim catalog or establish human admission

#### Scenario: Desired claim has not been observed

- **WHEN** an administrator enters a valid path absent from the observed catalog
- **THEN** it SHALL be usable in a draft and a saved rule, while tokens lacking it SHALL fail that condition

### Requirement: Administrators select claims using their own verified session

The rule editor SHALL offer observed root text attribute names in its dropdown, excluding token protocol metadata; the detailed explorer SHALL default to selectable root text attributes from the connected administrator's own verified access-token claims. The observed-name catalog SHALL use the same root-text and metadata restrictions by default. An explicit advanced-fields action SHALL expose the complete bounded searchable JSON tree and catalog, including nested paths and string arrays. Changing display mode SHALL clear pending field selection and copied values without modifying the rule draft. Only compatible bounded string/string-array paths SHALL be selectable. In advanced mode, unsupported values SHALL be visible with an explanation; omitted oversized values SHALL be indicated. Selected keys SHALL preserve their exact nested path without interpreting literal dots. After confirming a field, administrators SHALL explicitly choose in a separate popup whether to reuse a current string or array element from their own verified account or retain the entered operand. Field selection SHALL modify only the draft; existing AND/OR, preview, save and concurrent-revision safeguards SHALL remain in effect. Observed names/types SHALL remain available; exact paths SHALL be selected through the explorer rather than manual entry. The view SHALL be restricted to own human credentials and platform administration, SHALL NOT expose bearer tokens, signatures or other users' values, SHALL NOT persist or log payload values, and SHALL NOT retain the response after dismissal.

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

- **WHEN** an administrator opens either claim source in the default mode
- **THEN** root text account attributes SHALL be shown, while token metadata, nested paths, arrays and non-text values SHALL remain hidden

#### Scenario: Return from advanced fields

- **WHEN** an administrator selects an advanced field and switches back to simple fields
- **THEN** the hidden selection and copied operand SHALL be cleared, while saved rules and the existing draft SHALL remain unchanged

### Requirement: Admission feedback uses the shared Fred error presentation

Admission denial, invalid Free enrollment links and admission verification failures SHALL use the existing Fred error visual language and shared presentation, with localized actionable messages. Support SHALL use contactSupportLink when configured, alongside appropriate retry and sign-out actions. These screens SHALL remain reachable without protected bootstrap or team/resource loading; ordinary error pages SHALL retain their existing action.

#### Scenario: Denied or invalid enrollment route

- **WHEN** a denied person opens the refusal route or an invalid Free link
- **THEN** the screen SHALL use Fred's shared error presentation and its configured support destination without normal protected product loading

#### Scenario: Transient verification failure

- **WHEN** admission verification fails transiently
- **THEN** the shared error presentation SHALL offer a retry without falsely reporting definitive denial

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
