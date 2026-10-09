# frontend-ui-themes Specification

## Purpose
Defines shipped and deployment UI themes, their token coverage, and how the active theme and
light/dark mode are resolved and applied before the application paints.

## Requirements

### Requirement: Themes are peers

The frontend SHALL ship a catalog of UI themes, each identified by a stable id (`pebble`, `cobalt`,
`cloud`). No shipped theme SHALL serve as an implicit fallback for another shipped theme: every token
value it displays SHALL come from its own definition or from the theme-independent base.

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

Every shipped theme SHALL define, for both light and dark mode, the same set of theme tokens: the semantic
color roles (surfaces, text, outlines, primary, secondary, tertiary and status roles with their
`on-` and container variants), the font family and the radius scale. The theme-independent base
SHALL NOT define any of these tokens.

The frontend test suite SHALL fail when a shipped theme lacks a token that another shipped theme defines, or defines
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

The theme SHALL resolve to the user's stored choice when that id is offered by the shipped and
deployment catalogs, otherwise to the platform default if offered, otherwise to the first offered
theme (`pebble` when no platform settings hide it). The mode SHALL resolve to the user's stored choice
(`light`, `dark`), or to the operating system preference when the choice is `system` or absent.

#### Scenario: Returning user on Cloud in dark mode

- **WHEN** a user whose stored choice is `cloud` and `dark` reloads the application
- **THEN** the first painted frame already uses Cloud's dark tokens

#### Scenario: Returning user on an added theme

- **WHEN** a user whose stored choice is a valid ZIP theme reloads the application after the catalog has been cached
- **THEN** the first painted application content uses that theme's inherited tokens and ZIP overrides

#### Scenario: Unknown stored theme

- **WHEN** the stored theme id is not in either catalog (for example `corporate`)
- **THEN** the document resolves to the offered platform default or first offered theme before application content paints, without an error

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

### Requirement: Deployment ZIP customizes shipped UI themes and branding

The frontend SHALL read optional CSS, branding properties and English/French UI translation overrides from the deployment theme ZIP downloaded through `FRONTEND_THEME_URL`. CSS overrides and translation labels SHALL be present before application content paints. Missing files SHALL leave stock values in effect.

#### Scenario: SeaweedFS theme ZIP is activated

- **WHEN** a frontend pod starts with a valid ZIP containing a CSS override for Cobalt dark and a `siteDisplayName` branding property
- **THEN** a new browser load sees the CSS override and brand name without any backend configuration or database change

#### Scenario: Translate one UI label

- **WHEN** the ZIP provides `theme-translations/en.json` with a replacement for one existing message
- **THEN** English users see that label while all omitted messages and French labels retain their shipped text

#### Scenario: Existing connected user

- **WHEN** the SeaweedFS ZIP object is replaced while frontend pods and clients remain running
- **THEN** the current theme stays in effect until the pods restart and clients reload

### Requirement: Deployment branding overrides stay within the allowlist

The deployment ZIP SHALL limit branding properties to existing frontend labels and asset names. It SHALL NOT override authentication, feature flags, routing, `index.html` or the application bundle.

#### Scenario: Invalid branding property file

- **WHEN** a ZIP contains `theme-properties.json` with an authentication setting or malformed JSON
- **THEN** the theme installation is refused and the configured stock/fail-closed behavior applies

### Requirement: One deployment ZIP adds multiple selectable UI themes

The frontend SHALL accept an optional `theme-catalog.json` with multiple distinct theme IDs, labels and bases from the three shipped themes. Each added theme SHALL inherit all tokens from its base and MAY override them by light or dark CSS in the same ZIP. Added themes SHALL appear in the user and admin selectors, including platform default and visibility controls. A removed or invalid selected ID SHALL fall back to an offered theme.

#### Scenario: Two custom themes in one ZIP

- **WHEN** the ZIP declares two valid additional themes with different shipped bases
- **THEN** both appear alongside Pebble, Cobalt and Cloud, and each preview inherits its declared base with its own CSS overrides

#### Scenario: Invalid catalog

- **WHEN** the ZIP catalog duplicates an ID or declares an unknown base
- **THEN** theme installation is refused and the configured stock/fail-closed behavior applies
