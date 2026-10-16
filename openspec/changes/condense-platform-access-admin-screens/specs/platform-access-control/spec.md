## MODIFIED Requirements

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

The page SHALL offer a top-right filtering action in the page header across every tab with explicit confirmation. Before activation, a read-only population review SHALL show identifiable users in counted Allowed and Blocked lists under the saved rule and current independent sources, with observation time. Stale/missing/conflicted evidence SHALL appear in a separate expandable Not checked section rather than be declared allowed or blocked. A missing field in an available verified token SHALL be evaluated normally. The initial view SHALL show Blocked when that group is nonempty, otherwise Allowed; empty groups SHALL show a short message without table pagination. An Update action SHALL reread the database snapshot, reference policy and import status without changing admission state; stale rows SHALL be hidden and confirmation disabled during loading, failure or revision conflict. A preview SHALL NOT grant access or save drafts. Activation confirmation SHALL reject a changed policy revision and retain the actor safeguard.

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
- **THEN** the preview SHALL include that person under Not checked without inventing token values or granting access

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

The policy SHALL expose allow/block mode above the conditions and persist it in the shared authority; absent mode SHALL retain allow behavior. Allow mode SHALL derive admission from matching rules. Block mode SHALL derive admission from nonmatching rules, including verified missing, empty or incompatible claims. Independent user/team admission sources SHALL remain sufficient in either mode. A timeout SHALL NOT derive admission. Delegated rule-derived admission SHALL require fresh, unconflicted evidence covering all selected claim paths. Preview SHALL present two separate statements, each carrying the success or error presentation of its own outcome: whether the tested rule accepts the account, judged for the selected mode (a match is accepted in allow mode and blocked in block mode, and a rule that could not be checked SHALL NOT be presented as accepting), and whether the account keeps access once filtering is on. When access is kept, the second statement SHALL name the sources known to keep it (the tested rule when it accepts the account, the platform administrator role, the individual exception, each authorized or Free team by name) and SHALL state the outcome alone when no source is known. Per-condition results SHALL stay with their condition.

Conditions SHALL form their own section whose header holds the all/any choice, offered only while the draft has two or more conditions, and the add-condition action, which SHALL keep its place whatever the number of conditions; a newly added condition SHALL be brought into view. Condition controls SHALL share a compact row when space permits, aligned from one condition to the next under column labels shown once, and reflow without horizontal overflow on narrow screens, where each condition shows its own labels. Every control SHALL keep its own accessible name in both layouts. An add-condition action SHALL open the verified-session JSON picker directly; confirming a field SHALL append one condition, while cancellation SHALL append nothing. Each existing condition SHALL show its exact selected path as text with an accessible edit action opening the same picker; an account-field dropdown SHALL NOT be shown. After field confirmation a separate popup SHALL offer explicit reuse of the current verified account value or retention of the existing operand; copying SHALL respect operand bounds and regex literal escaping. A small case toggle SHALL remain directly visible, and manual path entry SHALL NOT be shown. Validation feedback SHALL remain visible and associated with its input. Operand counters SHALL appear at 90% of the existing limit without relaxing that limit. Condition removal SHALL identify the affected condition; removing the last draft condition SHALL show the local empty state without deleting or saving the stored policy. Adding a condition SHALL be separate from testing/saving the whole draft.

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

The editor SHALL present the test, discard and save actions on one row under the conditions, with the unsaved or saved state beside the save action and the test result directly beneath that row. The editor SHALL NOT carry a title repeating its tab. Unsaved, saving and successful-save states SHALL be distinguishable; errors and conflicts SHALL retain the draft and SHALL NOT display successful-save feedback. The save action SHALL retain validity, busy, permission, revision and actor-lockout safeguards. Preview and field/value choices SHALL NOT save automatically.

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

#### Scenario: Combination choice follows the number of conditions

- **WHEN** the draft holds a single condition
- **THEN** no all/any choice SHALL be shown
- **WHEN** a second condition is added
- **THEN** the all/any choice SHALL appear in the conditions header and the add-condition action SHALL stay in that header

#### Scenario: Test result separates the rule from access

- **WHEN** an administrator tests a draft their account does not match in allow mode while an independent source admits them
- **THEN** one statement SHALL say, with the error presentation, that the rule does not accept the account
- **AND** a separate statement SHALL say, with the success presentation, that access is kept with filtering on
- **WHEN** the same account is tested against a matching rule in block mode
- **THEN** the rule statement SHALL say that the rule blocks the account

#### Scenario: Kept access names its sources

- **WHEN** a test concludes that the administrator keeps access and their own admission sources are known
- **THEN** the access statement SHALL name each of them: the tested rule when it accepts the account, the platform administrator role, the individual exception and each authorized or Free team by name
- **AND** the saved rule SHALL NOT be named as a source in place of the tested one
- **WHEN** no source is known
- **THEN** the statement SHALL give the outcome without naming a source

#### Scenario: Rule could not be checked

- **WHEN** a tested condition times out or cannot be inspected
- **THEN** the rule statement SHALL use the error presentation and say that the rule gives no access, in allow and in block mode

### Requirement: Administrators manage independent Free-link history

Only platform administrators SHALL create, list and revoke Free-team links. The platform administration Teams registry SHALL expose the Free toggle and Manage links action for each eligible team; ordinary team managers SHALL NOT see these controls or issue admission administration queries. Platform access SHALL group individual exceptions and independent team authorization in its Whitelist panel and SHALL NOT duplicate Free/link controls. The bounded paginated history SHALL expose the link identifier, note, creation and expiry dates, revocation state, suspension state and authenticated opening count, without reusable tokens or visitor identity. Administrators SHALL be able to inspect and revoke links while Free is disabled. Manage links SHALL open on the bounded invitation list with a Create link action; note and expiry inputs SHALL appear only in a separate creation view. That view SHALL place the optional note before optional expiration and reuse the platform KPI selector presentation, with a single future date/time input, future duration shortcuts, a No expiration option and Apply. The date draft SHALL prevent creation until applied or dismissed; Escape SHALL close only the selector and restore trigger focus. Empty expiration SHALL mean no expiry; invalid or past expiration SHALL prevent creation without losing the note. Generation success SHALL show the original URL in the platform's monospace font and an immediately available Copy link action, and SHALL attempt to copy that URL to the clipboard automatically.

History SHALL use an explicit Copy link action that recovers the original token and attempts clipboard writing without generating another link. Clipboard success SHALL be announced only after the write succeeds through temporary feedback on the corresponding Copy link button and a screen-reader status, without changing the dialog layout. If clipboard writing is unavailable or rejected, the UI SHALL retain the usable URL with a clear manual-copy fallback; a copy failure SHALL NOT be presented as generation failure or cause another invitation to be created. Creation/recovery URL state SHALL remain transient and clear on manager dismissal, without logging URLs or retaining reusable mutation payloads.

The opening-count column SHALL use the short localized label Opens (Ouvertures) without showing the last-access timestamp. Its value SHALL remain the aggregate of authenticated page openings, not unique users, anonymous clicks or message delivery. The UI SHALL identify manual sharing and explicit URL recovery; it SHALL NOT claim message delivery.

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
- **THEN** the usable invitation URL and Copy link action SHALL be shown with successful creation feedback
- **AND** the displayed URL SHALL use the platform's monospace font
- **AND** the UI SHALL attempt to copy that URL to the clipboard automatically
- **AND** clipboard success SHALL be announced only after the write succeeds; creation SHALL NOT claim message delivery

#### Scenario: Copy from invitation history

- **WHEN** an own-human platform administrator chooses Copy link on a recoverable row
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

- **WHEN** the invitation history displays Opens
- **THEN** the displayed value SHALL remain the authenticated opening aggregate

#### Scenario: Invalid creation input retains the draft

- **WHEN** expiration is invalid or no longer in the future, or generation fails
- **THEN** the creation form SHALL retain the note and date with actionable feedback, without closing the manager

### Requirement: Access administration has readable section navigation

The page SHALL provide localized Rules and Whitelist tabs using the shared Fred navigation presentation. Only the active panel SHALL be exposed visually or to keyboard and assistive navigation. The rule draft, user selection and paging SHALL survive tab changes without implicit saving or admission mutations. Whitelist SHALL provide localized Users and Teams sub-tabs. The Whitelist panel and its two sub-panels SHALL be named by their tabs only, without a heading repeating a tab label, and the Whitelist panel SHALL state once, above its sub-tabs, that its entries always have access whatever the rule. Import existing users and individual exceptions SHALL appear in Users; independent team authorization SHALL appear in Teams, without a separate top-level Teams tab. A top-right filtering action in the page header SHALL remain available across all tabs, without a separate Activation tab. Once the filtering state is known, a status indicator beside the page title SHALL state whether filtering is on or off, on every tab. Ordinary content and secondary explanations SHALL use the body text size of the sibling administration pages across the page and its dialogs, secondary explanations being set apart by a subdued colour rather than a different size. No section heading SHALL reuse the page-title size. Repeated explanations SHALL be removed while authorization exceptions, revocation consequences, validation and errors remain understandable.

#### Scenario: Return to an unsaved rule or selected users

- **WHEN** an administrator changes a draft or selects users, navigates to another tab and returns
- **THEN** those local changes SHALL remain and no save or authorization mutation SHALL have been sent by navigation

#### Scenario: Navigate sections using the keyboard

- **WHEN** an administrator uses arrow keys on the section strip
- **THEN** focus and selection SHALL move using the shared tab behavior and only the associated panel SHALL be exposed

#### Scenario: Read page and modal content

- **WHEN** an administrator reads conditions, selection dialogs or invitation history
- **THEN** ordinary text and secondary help SHALL use the body text size of the sibling administration pages, with errors and revocation guidance retained

#### Scenario: Separate whitelist management

- **WHEN** an administrator opens Whitelist
- **THEN** its Users/Teams sub-tabs SHALL be displayed under a single sentence stating that whitelist entries always have access, without a heading repeating a tab label
- **AND** only the selected sub-panel SHALL be exposed, with import/individual controls in Users and live team authorization in Teams

#### Scenario: Filtering action available in the header

- **WHEN** an administrator changes top-level or whitelist sub-tabs
- **THEN** the filtering action SHALL remain at the top right of the page header with the same activation guards

#### Scenario: Filtering status beside the title

- **WHEN** an administrator opens the page while filtering is off, then enables filtering
- **THEN** the indicator beside the page title SHALL read that filtering is off, then that it is on
- **AND** it SHALL remain visible when the administrator changes tabs
