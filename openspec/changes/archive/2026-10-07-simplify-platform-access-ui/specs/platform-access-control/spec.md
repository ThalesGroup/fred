## ADDED Requirements

### Requirement: Administrators select claims using their own verified session

The rule editor SHALL provide a searchable collapsible JSON view of the connected administrator's own verified access-token claims. Only compatible bounded string/string-array paths SHALL be selectable. Unsupported values SHALL be visible with an explanation; omitted oversized values SHALL be indicated. Selected keys SHALL preserve their exact nested path without interpreting literal dots. Administrators SHALL explicitly choose whether to reuse a current string or array element. Field selection SHALL modify only the draft; existing AND/OR, preview, save and concurrent-revision safeguards SHALL remain in effect. Observed names/types and advanced manual path entry SHALL remain available. The view SHALL be restricted to own human credentials and platform administration, SHALL NOT expose bearer tokens, signatures or other users' values, SHALL NOT persist or log payload values, and SHALL NOT retain the response after dismissal.

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

### Requirement: Admission feedback uses the shared Fred error presentation

Admission denial, invalid Free enrollment links and admission verification failures SHALL use the existing Fred error visual language and shared presentation, with localized actionable messages. Support SHALL use contactSupportLink when configured, alongside appropriate retry and sign-out actions. These screens SHALL remain reachable without protected bootstrap or team/resource loading; ordinary error pages SHALL retain their existing action.

#### Scenario: Denied or invalid enrollment route

- **WHEN** a denied person opens the refusal route or an invalid Free link
- **THEN** the screen SHALL use Fred's shared error presentation and its configured support destination without normal protected product loading

#### Scenario: Transient verification failure

- **WHEN** admission verification fails transiently
- **THEN** the shared error presentation SHALL offer a retry without falsely reporting definitive denial
