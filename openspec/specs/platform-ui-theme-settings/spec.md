# platform-ui-theme-settings Specification

## Purpose
Lets platform administrators choose the UI theme users get by default and withdraw themes from the
user's choice, and defines how these settings constrain the theme each user sees.

## Requirements

### Requirement: Platform UI theme settings

The platform SHALL hold two UI theme settings: a default theme id, and a list of hidden theme ids.
Both SHALL be unset on a new deployment. A theme id SHALL be a lowercase identifier of at most 32
characters (`[a-z][a-z0-9-]*`); the hidden list SHALL hold at most 32 distinct ids. The default theme
SHALL NOT be in the hidden list.

The control plane SHALL NOT validate ids against the frontend theme catalog; the frontend SHALL
ignore ids it does not ship.

#### Scenario: Default theme cannot be hidden

- **WHEN** an administrator saves default `cobalt` with hidden `["cobalt", "cloud"]`
- **THEN** the request is rejected with a validation error and the stored settings do not change

#### Scenario: Unknown id from a newer or older frontend

- **WHEN** the stored default theme is `aurora` and the frontend does not ship `aurora`
- **THEN** the frontend behaves as if no default theme were set

### Requirement: Administrators edit the settings

Only a user with the platform management permission SHALL read and replace the settings through the
admin API. The admin interface SHALL offer a "User interface" page where the administrator picks the
default theme among the themes the frontend ships, and marks each theme as offered or hidden.

The page SHALL prevent saving a state where the default theme is hidden or where no shipped theme is
offered.

#### Scenario: Non-administrator

- **WHEN** a user without the platform management permission calls the admin settings API
- **THEN** the call is refused with 403 and nothing changes

#### Scenario: Hiding every theme

- **WHEN** an administrator tries to withdraw the default theme or the last offered theme
- **THEN** the page does not allow it, so at least one theme always stays offered

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

### Requirement: Theme resolution with platform settings

A theme SHALL be offered when the frontend ships it and it is not hidden. When no shipped theme would
be offered, the hidden list SHALL be ignored.

The theme SHALL resolve to the user's stored choice when it is offered, otherwise to the platform
default when it is offered, otherwise to the first offered theme in catalog order. The user's stored
choice SHALL be kept unchanged when it is hidden, so that it applies again if the theme is offered
again.

#### Scenario: User's theme gets hidden

- **WHEN** a user's stored choice is `cloud` and an administrator hides `cloud` with default `cobalt`
- **THEN** the user gets Cobalt at their next load, and gets Cloud again if `cloud` is offered later

#### Scenario: Default unset and Pebble hidden

- **WHEN** no default is set, `pebble` is hidden and the user has no stored choice
- **THEN** the user gets the first offered theme in catalog order

### Requirement: Profile picker shows offered themes only

The profile theme picker SHALL list only offered themes. When exactly one theme is offered, the
picker SHALL NOT be shown; the light / dark / system choice SHALL remain available.

#### Scenario: Single offered theme

- **WHEN** only `cobalt` is offered
- **THEN** the profile shows the light / dark / system choice without a theme picker

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

- **WHEN** the refreshed settings hide all built-in themes and offer only Paris Aéroport
- **THEN** Paris Aéroport remains active and the user has no picker offering hidden built-in themes

#### Scenario: Settings refresh fails

- **WHEN** the public settings refresh fails after a valid configuration has loaded
- **THEN** the last valid visibility and default settings remain in effect

#### Scenario: Selected theme removed from the deployment catalog

- **WHEN** the user's stored theme X is removed from the installed catalog and the application reloads
- **THEN** the active theme is the administrator's default when it is installed and offered
- **AND** X does not appear in the user picker
