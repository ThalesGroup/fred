## ADDED Requirements

### Requirement: One surface rule for both themes

The frontend SHALL define the neutral surface tokens so that, in both the light and the dark theme, each `surface-container-*` level is further in lightness from `surface-main` than the level below it, in the order `surface-container-lowest`, `surface-container-low`, `surface-container`, `surface-container-high`, `surface-container-highest`. In the light theme the levels SHALL get darker than `surface-main`; in the dark theme they SHALL get lighter.

#### Scenario: Light theme ordering
- **WHEN** the light theme is active
- **THEN** `surface-main` is the lightest neutral surface and each successive container level, from `surface-container-lowest` to `surface-container-highest`, has a strictly lower tone

#### Scenario: Dark theme ordering
- **WHEN** the dark theme is active
- **THEN** `surface-main` is the darkest neutral surface and each successive container level, from `surface-container-lowest` to `surface-container-highest`, has a strictly higher tone

#### Scenario: Same role after a theme switch
- **WHEN** a component styled with a given `surface-container-*` level is shown in light and then in dark
- **THEN** it stands out from the page background in both themes, by the same rank in the scale

### Requirement: Surface tones

The surface tokens SHALL resolve to the following tones of the neutral ramp.

| Token | Light | Dark |
|---|---|---|
| `surface-main` | 100 | 6 |
| `surface-container-lowest` | 99 | 8 |
| `surface-container-low` | 97.5 | 10 |
| `surface-container` | 96 | 12 |
| `surface-container-high` | 94.5 | 15 |
| `surface-container-highest` | 93 | 18 |
| `surface-floating` | 100 | 15 |

#### Scenario: Token values match the table
- **WHEN** the computed value of each token is read in each theme
- **THEN** it equals the neutral ramp step listed for that token and theme

### Requirement: Floating surface

Elements that float above the page (menus, popovers, tooltips, modal dialogs, editor popups) SHALL use `surface-floating` for their background and SHALL NOT use a `surface-container-*` level for it.

#### Scenario: Menu in light theme
- **WHEN** a menu opens over a page in the light theme
- **THEN** its background is white and it is separated from the page by its shadow

#### Scenario: Menu in dark theme
- **WHEN** a menu opens over a page in the dark theme
- **THEN** its background is lighter than `surface-container`, and it is separated from the page by its shadow

### Requirement: Neutral ramp tint

The neutral ramp SHALL be a single low-chroma blue-tinted grey (CIE LCh chroma 1.5, hue 280°), with tone equal to CIE L\*. Every neutral token (surfaces, on-surface text, outlines) SHALL be drawn from this ramp.

#### Scenario: No lavender cast
- **WHEN** any neutral ramp step is converted to CIE LCh
- **THEN** its chroma is at most 2 and, for chromatic steps, its hue is within 10° of 280°
