## ADDED Requirements

### Requirement: Deployment ZIP customizes shipped UI themes and branding

The frontend SHALL read optional `theme-custom.css`, `theme-properties.json` and English/French UI translation overrides from the deployment theme ZIP downloaded through `FRONTEND_THEME_URL`. CSS overrides and translation labels SHALL be present before application content paints. Branding properties SHALL be limited to the existing frontend labels and asset names; the ZIP SHALL NOT override authentication, feature flags, routing, `index.html` or the application bundle. When a theme file is absent, the stock value SHALL remain in effect.

#### Scenario: SeaweedFS theme ZIP is activated

- **WHEN** a frontend pod starts with a valid ZIP containing a CSS override for Cobalt dark and a `siteDisplayName` branding property
- **THEN** a new browser load sees the CSS override and brand name without any backend configuration or database change

#### Scenario: Invalid branding property file

- **WHEN** a ZIP contains `theme-properties.json` with an authentication setting or malformed JSON
- **THEN** the theme installation is refused and the configured stock/fail-closed behavior applies

#### Scenario: Translate one UI label

- **WHEN** the ZIP provides `theme-translations/en.json` with a replacement for one existing message
- **THEN** English users see that label while all omitted messages and French labels retain their shipped text

#### Scenario: Existing connected user

- **WHEN** the SeaweedFS ZIP object is replaced while frontend pods and clients remain running
- **THEN** the current theme stays in effect until the pods restart and clients reload
