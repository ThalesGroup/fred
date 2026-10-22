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

### Requirement: Local Vite startup loads the deployment theme ZIP

The local Vite frontend SHALL load an optional ZIP from `FRONTEND_THEME_URL` before serving application content. It SHALL honor the existing S3 credential, region and required-theme settings, apply the same archive validation and served-file allowlist as Docker, and fall back to stock files for omitted assets. Environment values SHALL override local configuration file values.

#### Scenario: Local task activates a SeaweedFS ZIP

- **WHEN** the frontend task starts with a valid SeaweedFS theme URL in `apps/frontend/config/.env`
- **THEN** its CSS, catalog, branding, images, fonts and translations are served before the application loads

#### Scenario: Private archive

- **WHEN** both S3 credentials are configured
- **THEN** the ZIP request is signed and credentials are absent from browser assets and logs

#### Scenario: Explicit environment wins

- **WHEN** the shell supplies a theme URL different from the local configuration file
- **THEN** Vite loads the shell-supplied URL

#### Scenario: Optional unavailable or invalid archive

- **WHEN** an optional ZIP cannot be fetched or fails the existing validation
- **THEN** Vite warns and serves stock files without a partial or stale overlay

#### Scenario: Required invalid archive

- **WHEN** theme loading fails with `FRONTEND_THEME_REQUIRED=true`
- **THEN** Vite refuses to start

### Requirement: Local theme overlays preserve the checkout

Local theme loading SHALL preserve tracked public files, limit requests to the existing supported theme surfaces, and fetch replacement ZIPs only on server restart. Unsetting the theme URL SHALL restore stock behavior on the next startup.

#### Scenario: Replace and restart

- **WHEN** the storage ZIP is replaced and Vite is restarted
- **THEN** a refreshed browser receives the replacement theme without changes to tracked public files

#### Scenario: Protected bundle and paths

- **WHEN** the archive includes `index.html`, `config.json`, bundle files, escaping paths or symlinks
- **THEN** the existing validation rejects escaping archives and unsupported files are not served as theme overrides

#### Scenario: Disable local overlay

- **WHEN** Vite starts without a theme URL after a previously themed run
- **THEN** it serves stock assets without the previous overlay

### Requirement: Theme archives separate custom and shared content

The theme archive SHALL accept `theme-catalog.json` at its root, custom theme CSS and images under `themes/<id>/`, and global branding, translations, legal content and images under `shared/`. Each theme directory SHALL correspond to a declared catalog id. The installed files SHALL retain the frontend's existing public URLs. Existing flat archives SHALL remain installable. The archive builder SHALL produce the same structured format from the example source.

#### Scenario: Install two custom themes

- **WHEN** an archive declares two themes and supplies a directory for each, plus optional shared content
- **THEN** both themes and their CSS and images are available through the existing frontend URLs
- **AND** shared content applies to all themes

#### Scenario: Existing flat archive

- **WHEN** an existing flat archive is installed
- **THEN** its supported content remains available at the same URLs

#### Scenario: Conflicting or undeclared theme content

- **WHEN** theme directories contain conflicting image names or a directory has no matching catalog entry
- **THEN** installation fails with a useful error instead of selecting content by archive order

### Requirement: Custom themes carry isolated browser tab branding

Custom catalog entries SHALL support optional `tabTitle`, `faviconName` and `faviconNameDark`. The active theme SHALL determine the browser title and mode-appropriate SVG favicon. Omitted values SHALL use global branding; an omitted dark icon SHALL reuse a supplied light icon. Switching to another theme SHALL remove the previous theme's tab overrides.

#### Scenario: Custom theme selected

- **WHEN** the user selects a theme declaring a tab title and light/dark favicon names
- **THEN** the tab shows that title and the favicon matching the current mode

#### Scenario: Return to a built-in theme

- **WHEN** the user switches from the `acme` custom theme to Pebble
- **THEN** the tab restores the global Fred title and mode-appropriate icon

#### Scenario: Existing ZIP and single icon

- **WHEN** a catalog omits tab metadata
- **THEN** the existing global branding remains in effect
- **AND WHEN** a theme supplies only a light favicon name
- **THEN** both modes use that icon

### Requirement: Browser tab metadata is validated before activation

The theme installer SHALL reject blank or overlong tab titles and favicon names that are not bounded SVG basenames. Titles SHALL have at most 200 characters; names SHALL have at most 128 characters and contain only letters, digits, underscores and hyphens, starting with a letter or digit. Existing id, label and base constraints SHALL remain in effect.

#### Scenario: Escaping favicon name

- **WHEN** a ZIP catalog contains a favicon name with a slash, traversal or URL
- **THEN** activation is rejected through the existing optional/required failure behavior

### Requirement: Mermaid previews follow the active UI theme

Completed Mermaid blocks SHALL use the active UI theme's semantic roles for renderer-supplied background, text, connectors, accents, node surfaces and borders, and SHALL use the application's font family. Inline and enlarged views SHALL have the same appearance. Changing the shipped or deployment theme or light/dark mode SHALL update mounted previews without requiring a page reload or a diagram-specific theme choice.

#### Scenario: Shipped theme and mode change

- **GIVEN** a completed Mermaid diagram is visible
- **WHEN** the user switches between Pebble, Cobalt and Cloud, or changes light/dark mode
- **THEN** its colors and font follow the newly active theme
- **AND** the enlarged view uses the same palette as the inline diagram

#### Scenario: Deployment theme overrides

- **WHEN** a deployment theme overrides Fred's primary, surface, text and outline tokens
- **THEN** Mermaid previews use those effective token values rather than a stock diagram palette

### Requirement: Themed Mermaid previews preserve shared rendering behavior

The themed preview SHALL render supported diagrams without losing their nodes, relationships or labels. Previously renderable Mermaid syntax outside the preferred renderer's supported subset SHALL retain a compatibility rendering path. Raw source SHALL be attempted before syntax repair. Source copying, enlarged viewing, readable error reporting and the existing transition from streaming source to a completed diagram SHALL remain available.

#### Scenario: Common diagram types

- **WHEN** a user views a supported flowchart, state, sequence, class, entity-relationship or XY diagram
- **THEN** the diagram's nodes, relationships and labels are visible in the themed preview

#### Scenario: Compatibility diagram

- **WHEN** a valid Mermaid pie or Gantt diagram, or syntax unsupported by the preferred renderer, is displayed
- **THEN** the compatibility path renders it with the active UI theme's default palette
- **AND** a source rewrite is attempted only if the original source cannot render

#### Scenario: Existing interactions and invalid source

- **WHEN** a rendered diagram is copied or enlarged
- **THEN** copying returns the original source and enlargement preserves the diagram
- **AND WHEN** neither the original nor repaired source can render
- **THEN** the preview shows a readable error without breaking surrounding Markdown

### Requirement: Diagram previews are isolated and use local assets

Diagram content SHALL NOT execute scripts, load remote fonts or leak styles into surrounding UI. SVG references SHALL remain local to each diagram view, including simultaneously mounted diagrams and enlarged copies.

#### Scenario: Multiple diagrams and an enlarged copy

- **WHEN** multiple Mermaid blocks and an enlarged view are mounted together
- **THEN** every SVG reference resolves within its own view
- **AND** other diagrams and surrounding application text retain their own styles

#### Scenario: Untrusted content and offline fonts

- **WHEN** diagram source contains script-bearing markup or the browser cannot access external font services
- **THEN** the content cannot execute code and rendering uses the application's locally supplied fonts
