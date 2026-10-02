## ADDED Requirements

### Requirement: Text tones

The neutral text tokens SHALL resolve to these tones of the neutral ramp, and `on-surface-retreat` SHALL meet WCAG AA (4.5:1) on `surface-main` and on every `surface-container-*` level in both themes.

| Token | Light | Dark |
|---|---|---|
| `on-surface` | 10 | 95 |
| `on-surface-retreat` | 40 | 75 |
| `on-surface-muted` | 45 | 60 |

#### Scenario: Secondary text contrast
- **WHEN** `on-surface-retreat` text is drawn on any surface container level
- **THEN** its contrast ratio is at least 4.5:1 in both themes

#### Scenario: Muted text on the page
- **WHEN** `on-surface-muted` text is drawn on `surface-main`
- **THEN** its contrast ratio is at least 4.5:1 in both themes

### Requirement: Three outline levels

The frontend SHALL define exactly three outline tokens, ordered from strongest to faintest: `outline` (light 50, dark 60), `outline-variant` (light 80, dark 40) and `outline-muted` (light 88, dark 30). Borders and dividers SHALL use an outline token, not a surface token.

#### Scenario: No fourth outline token
- **WHEN** the semantic token files are read
- **THEN** no `--outline-retreat` token is defined and no stylesheet or component references it

#### Scenario: Table borders
- **WHEN** a data table renders cell and footer borders
- **THEN** they use `outline-muted`

### Requirement: Every color token used is defined

Every `--` color custom property referenced by the frontend SHALL be defined in the token files or locally by the component that uses it.

#### Scenario: No undefined token
- **WHEN** the frontend sources are scanned for `var(--…)` color references
- **THEN** each one resolves to a token file definition or a local definition
