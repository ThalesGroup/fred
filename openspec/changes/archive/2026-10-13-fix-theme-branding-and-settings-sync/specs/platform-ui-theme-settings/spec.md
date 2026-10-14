## MODIFIED Requirements

### Requirement: Settings are known before the first paint

The settings SHALL be exposed in the public frontend configuration, available before authentication.
The frontend SHALL resolve the theme with these settings before it paints any application content,
and SHALL NOT switch theme after that first paint unless the user changes their choice or refreshed
platform settings require a new resolution. A successful administrator save SHALL refresh settings
in the saving session. Other connected sessions SHALL refresh on window focus and at most every
60 seconds while active. A new load SHALL always use the current platform settings.

Before the settings are known, the frontend MAY paint only an empty page in the resolved light or
dark background, never application content.

#### Scenario: First visit on a Cobalt platform

- **WHEN** a user with no stored choice opens the application on a platform whose default is `cobalt`
- **THEN** the first painted application content is already in Cobalt

#### Scenario: Administrator changes the default while users are connected

- **WHEN** an administrator changes the default theme
- **THEN** the saving session refreshes its offered choices and resolves its active theme with the saved settings
- **AND** other connected sessions apply the current settings on focus or their next refresh without losing a stored personal choice

## ADDED Requirements

### Requirement: Default theme is visibly identified in administration

The administration page SHALL show the default theme as a readable status, distinct from the set-default action, in both light and dark modes. Availability controls and light/dark previews SHALL have clear labels. Theme rows SHALL remain usable on narrow screens without a fixed minimum width causing horizontal overflow.

#### Scenario: Default theme selected

- **WHEN** an administrator views the theme settings
- **THEN** exactly the saved default theme has a visible default badge and selected border
- **AND** offered non-default themes expose a set-default action

### Requirement: Refreshed settings constrain the user picker

After receiving platform settings, the frontend SHALL recompute offered themes and the active selection from the same installed catalog. A failed refresh SHALL retain the last successful settings. Custom themes SHALL obey the same hidden/default rules as built-in themes. The existing empty-catalog safeguard SHALL remain unchanged.

#### Scenario: Hide the selected custom theme

- **WHEN** an administrator hides the user's selected custom theme and the client receives the new settings
- **THEN** that theme is absent from the picker and the active theme resolves to the offered default
- **AND** the user's stored preference is retained for possible restoration

#### Scenario: Only one custom theme is offered

- **WHEN** the refreshed settings hide all built-in themes and offer only the `acme` custom theme
- **THEN** `acme` remains active and the user has no picker offering hidden built-in themes

#### Scenario: Settings refresh fails

- **WHEN** the public settings refresh fails after a valid configuration has loaded
- **THEN** the last valid visibility and default settings remain in effect

#### Scenario: Selected theme removed from the deployment catalog

- **WHEN** the user's stored theme X is removed from the installed catalog and the application reloads
- **THEN** the active theme is the administrator's default when it is installed and offered
- **AND** X does not appear in the user picker
