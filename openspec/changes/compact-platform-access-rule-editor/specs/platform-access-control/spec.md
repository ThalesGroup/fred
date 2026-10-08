## MODIFIED Requirements

### Requirement: Administrators compose understandable bounded predicates

The editor SHALL support one to sixteen conditions combined by either all (AND) or any (OR), with localized labels. Each condition SHALL select an unambiguous claim path, operator, operand and explicit case handling. Operators SHALL include literal equals/not-equals, contains/not-contains, and advanced whole-value regex. Literal metacharacters SHALL NOT be interpreted as regex. Literal comparison SHALL default to ignoring case; administrators SHALL be able to select case-sensitive comparison. For nonempty string arrays, positive predicates SHALL match any element and negative predicates SHALL require all elements to satisfy the negation. Missing, empty, incompatible and oversized values SHALL fail every predicate. Invalid input SHALL be rejected before saving; bounded regex timeouts SHALL NOT establish rule-derived admission.

Preview SHALL show effective admission with readable green/red accents and a larger heading while separately explaining condition matching.

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
