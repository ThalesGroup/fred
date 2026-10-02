## ADDED Requirements

### Requirement: Consumers control row activation and outcome presentation

The shared UI SHALL let consumers activate a typed table row by pointer or keyboard without also activating its embedded controls. Consumer-owned drawer close labels SHALL determine the accessible close action name. KPI values SHALL support the shared semantic outcome tones, preserving neutral defaults and visible labels/counts.

#### Scenario: Row activation is isolated
- **WHEN** a consumer activates a row cell or focuses the row and presses Enter or Space
- **THEN** the row callback receives that row, while button/link/input/label/select/textarea actions do not additionally activate the row

#### Scenario: Existing selection stays usable
- **WHEN** a selectable table also exposes row activation
- **THEN** background activation calls the row callback and the checkbox remains responsible for selecting that row

#### Scenario: Localized dismissal and outcome colors
- **WHEN** a consumer supplies a localized close label and a supported KPI tone
- **THEN** the drawer close action uses that accessible label and the KPI value uses the corresponding light/dark design tokens

#### Scenario: Existing callers remain compatible
- **WHEN** consumers omit all new optional props
- **THEN** existing table selection, English drawer close name and neutral KPI rendering remain unchanged
