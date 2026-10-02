## Purpose

Defines the UI themes the frontend ships, what each theme must define, and how the active theme and
light/dark mode are resolved and applied before the application paints.

## ADDED Requirements

### Requirement: Themes are peers

The frontend SHALL ship a catalog of UI themes, each identified by a stable id (`pebble`, `cobalt`,
`cloud`). No theme SHALL serve as an implicit fallback for another: every token value a theme
displays SHALL come from that theme's own definition or from the theme-independent base.

Removing a theme from the catalog SHALL require removing only that theme's definition and its
catalog entry, and SHALL NOT change how any other theme renders.

#### Scenario: Pebble renders from its own definition

- **WHEN** the active theme is `pebble`
- **THEN** every semantic color, the font family and the radius scale come from Pebble's theme
  definition, not from the base stylesheets

#### Scenario: Removing a theme leaves the others unchanged

- **WHEN** the `pebble` definition is removed from the catalog
- **THEN** `cobalt` and `cloud` render exactly as before, in both modes

### Requirement: A theme defines the complete token set

Every theme SHALL define, for both light and dark mode, the same set of theme tokens: the semantic
color roles (surfaces, text, outlines, primary, secondary, tertiary and status roles with their
`on-` and container variants), the font family and the radius scale. The theme-independent base
SHALL NOT define any of these tokens.

The frontend test suite SHALL fail when a theme lacks a token that another theme defines, or defines
a token that the others do not.

#### Scenario: A missing token fails the tests

- **WHEN** a theme's dark definition omits `--tertiary-container`
- **THEN** the theme completeness test fails and names the theme, the mode and the token

#### Scenario: The base carries no theme value

- **WHEN** no theme is applied to the document
- **THEN** no semantic color, font family or radius-scale token has a value

### Requirement: The theme is applied before the first paint

The document SHALL carry the resolved theme id and the resolved light/dark mode before the browser
paints any application content. The application SHALL NOT paint in one theme or mode and then switch
to another unless the user, or a platform setting, changes it.

The theme SHALL resolve to the user's stored choice when that id is in the catalog, otherwise to the
default theme (`pebble`). The mode SHALL resolve to the user's stored choice (`light`, `dark`), or to
the operating system preference when the choice is `system` or absent.

#### Scenario: Returning user on Cloud in dark mode

- **WHEN** a user whose stored choice is `cloud` and `dark` reloads the application
- **THEN** the first painted frame already uses Cloud's dark tokens

#### Scenario: Unknown stored theme

- **WHEN** the stored theme id is not in the catalog (for example `corporate`)
- **THEN** the document resolves to the default theme before the first paint, without an error

#### Scenario: System mode follows the OS

- **WHEN** the stored mode is `system` and the operating system prefers dark
- **THEN** the first painted frame uses the dark mode of the resolved theme

### Requirement: The design tokens package is unchanged

The published `@fred-oss/design-tokens` package SHALL keep exposing Pebble's token values under its
existing `[data-theme="light"]` and `[data-theme="dark"]` selectors, with the same token names and
values as before this change.

#### Scenario: SDK consumer upgrades

- **WHEN** a hosted application rebuilds against the package produced after this change
- **THEN** every token it reads has the same name and value as in the previous package build
