## MODIFIED Requirements

### Requirement: Administrators select claims using their own verified session

The rule editor SHALL default to selectable text attributes at the root of the connected administrator's own verified access-token claims, excluding token protocol metadata. The observed-name catalog SHALL use the same root-text and metadata restrictions by default. An explicit advanced-fields action SHALL expose the complete bounded searchable JSON tree and catalog, including nested paths and string arrays. Changing display mode SHALL clear pending field selection and copied values without modifying the rule draft. Only compatible bounded string/string-array paths SHALL be selectable. In advanced mode, unsupported values SHALL be visible with an explanation; omitted oversized values SHALL be indicated. Selected keys SHALL preserve their exact nested path without interpreting literal dots. Administrators SHALL explicitly choose whether to reuse a current string or array element. Field selection SHALL modify only the draft; existing AND/OR, preview, save and concurrent-revision safeguards SHALL remain in effect. Observed names/types and advanced manual path entry SHALL remain available. The view SHALL be restricted to own human credentials and platform administration, SHALL NOT expose bearer tokens, signatures or other users' values, SHALL NOT persist or log payload values, and SHALL NOT retain the response after dismissal.

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
