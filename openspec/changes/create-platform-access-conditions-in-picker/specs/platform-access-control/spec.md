## ADDED Requirements

### Requirement: Access administration has readable section navigation

The page SHALL provide localized Rules, Users, Teams and links, and Activation tabs using the shared Fred navigation presentation. Only the active panel SHALL be exposed visually or to keyboard and assistive navigation. The rule draft, user selection and paging SHALL survive tab changes without implicit saving or admission mutations. T0 import SHALL be grouped with users and the filtering control SHALL appear in the last Activation view. Ordinary content, secondary explanations and section headings SHALL use a consistent readable typography scale across the page and its dialogs. Repeated explanations SHALL be removed while authorization exceptions, revocation consequences, validation and errors remain understandable.

#### Scenario: Return to an unsaved rule or selected users

- **WHEN** an administrator changes a draft or selects users, navigates to another tab and returns
- **THEN** those local changes SHALL remain and no save or authorization mutation SHALL have been sent by navigation

#### Scenario: Navigate sections using the keyboard

- **WHEN** an administrator uses arrow keys on the section strip
- **THEN** focus and selection SHALL move using the shared tab behavior and only the associated panel SHALL be exposed

#### Scenario: Read page and modal content

- **WHEN** an administrator reads conditions, selection dialogs or invitation history
- **THEN** ordinary text and secondary help SHALL use consistent readable sizes, with errors and revocation guidance retained

## MODIFIED Requirements

### Requirement: Administrators compose understandable bounded predicates

Saved rules SHALL contain one to sixteen conditions; the editor SHALL support an empty local draft when no policy exists or all draft conditions have been removed. Testing, saving and activation SHALL require a valid nonempty rule. Existing saved conditions SHALL be loaded without fabrication or omission. The editor SHALL support these conditions combined by either all (AND) or any (OR), with localized labels. Each condition SHALL select an unambiguous claim path, operator, operand and explicit case handling. Operators SHALL include literal equals/not-equals, contains/not-contains, and advanced whole-value regex. Literal metacharacters SHALL NOT be interpreted as regex. Literal comparison SHALL default to ignoring case; administrators SHALL be able to select case-sensitive comparison. For nonempty string arrays, positive predicates SHALL match any element and negative predicates SHALL require all elements to satisfy the negation. Missing, empty, incompatible and oversized values SHALL fail every predicate. Invalid input SHALL be rejected before saving; bounded regex timeouts SHALL NOT establish rule-derived admission.

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

Adding a condition or editing its field SHALL open the verified-session JSON picker directly. Its localized title SHALL ask which account field to filter. The picker SHALL default to a flat JSON presentation of selectable root text attributes from the connected administrator's own verified access-token claims, with blue selectable keys and visible selection feedback; token protocol metadata SHALL remain hidden. Observed field names SHALL remain available through the existing alternate source inside that modal. The observed-name catalog SHALL use the same root-text and metadata restrictions by default. An explicit advanced-fields action SHALL expose the complete bounded searchable JSON tree and catalog, including nested paths and string arrays. Changing display mode SHALL clear pending field selection and copied values without modifying the rule draft. Only compatible bounded string/string-array paths SHALL be selectable. In advanced mode, unsupported values SHALL be visible with an explanation; omitted oversized values SHALL be indicated. Selected keys SHALL preserve their exact nested path without interpreting literal dots. After confirming a field, administrators SHALL explicitly choose in a separate popup whether to reuse a current string or array element from their own verified account or retain the entered operand. Field selection SHALL modify only the draft; existing AND/OR, preview, save and concurrent-revision safeguards SHALL remain in effect. Observed names/types SHALL remain available; exact paths SHALL be selected through the explorer rather than manual entry. The view SHALL be restricted to own human credentials and platform administration, SHALL NOT expose bearer tokens, signatures or other users' values, SHALL NOT persist or log payload values, and SHALL NOT retain the response after dismissal.

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

### Requirement: Claim discovery exposes names without a personal-data inventory

The system SHALL discover bounded nested string/string-array claim paths from verified human access tokens and expose observed names and supported types only to platform administrators. The catalog SHALL NOT expose other users' claim values, JWTs or workload claims, and SHALL NOT claim to enumerate the IdP schema. The editor SHALL distinguish observed names from universal availability and permit selection of an unambiguous path present in the own verified session but not yet in the observed catalog. Traversal, catalog growth and retained token facts SHALL be bounded; exceeding these bounds SHALL NOT produce a positive match for unavailable facts.

#### Scenario: Another human reveals a custom path

- **WHEN** a verified human token contains a supported custom nested claim
- **THEN** its path SHALL become selectable without Helm changes and without exposing that person's value

#### Scenario: Workload or unverified token supplies names

- **WHEN** a workload token or unverified input contains additional claims
- **THEN** it SHALL NOT populate the human claim catalog or establish human admission

#### Scenario: Desired claim has not been observed

- **WHEN** an administrator selects a supported own-session path absent from the observed catalog
- **THEN** it SHALL be usable in a draft and a saved rule, while tokens lacking it SHALL fail that condition
