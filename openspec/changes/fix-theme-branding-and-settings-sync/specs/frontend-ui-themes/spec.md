## ADDED Requirements

### Requirement: Custom themes carry isolated browser tab branding

Custom catalog entries SHALL support optional `tabTitle`, `faviconName` and `faviconNameDark`. The active theme SHALL determine the browser title and mode-appropriate SVG favicon. Omitted values SHALL use global branding; an omitted dark icon SHALL reuse a supplied light icon. Switching to another theme SHALL remove the previous theme's tab overrides.

#### Scenario: Paris theme selected

- **WHEN** the user selects a theme declaring a tab title and light/dark favicon names
- **THEN** the tab shows that title and the favicon matching the current mode

#### Scenario: Return to a built-in theme

- **WHEN** the user switches from Paris Aéroport to Pebble
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
