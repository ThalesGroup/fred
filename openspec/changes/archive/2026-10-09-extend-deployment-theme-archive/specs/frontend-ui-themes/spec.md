## ADDED Requirements

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

## MODIFIED Requirements

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
