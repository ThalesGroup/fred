## MODIFIED Requirements

### Requirement: The theme is applied before the first paint

The document SHALL carry the resolved theme id and the resolved light/dark mode before the browser
paints any application content. The application SHALL NOT paint in one theme or mode and then switch
to another unless the user, a platform setting or the applicable System appearance changes it.

The theme SHALL resolve to the user's stored choice when that id is offered by the shipped and
deployment catalogs, otherwise to the platform default if offered, otherwise to the first offered
theme (`pebble` when no platform settings hide it). The mode SHALL resolve to the user's stored choice
(`light`, `dark`), or, for System mode, to the local daylight schedule if declared by the resolved theme and otherwise to the operating system preference. An absent mode defaults to System.

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

- **WHEN** the stored mode is `system` and the resolved theme has no daylight schedule and the operating system prefers dark
- **THEN** the first painted frame uses the dark mode of the resolved theme

## ADDED Requirements

### Requirement: Local daylight for deployment themes

A deployment theme MAY declare `localDaylight` with a local sunrise and sunset in 24-hour HH:MM form, sunrise earlier than sunset. In System mode the frontend SHALL derive the scene's daylight, twilight and celestial positions from the user's civil clock, update an open screen and resynchronize after sleep without requesting an external service. Explicit Light and Dark SHALL use their fixed appearances. Leaving the theme SHALL release its clock effects.

#### Scenario: Shared lighting across an open conversation

- **WHEN** a clock theme with sunrise at 07:30 and sunset at 17:00 is selected in System mode and a user opens or continues a conversation through sunset
- **THEN** the indoor and outdoor scenes reflect the same local phase, messages retain their contrast, and sending a message does not restart the cycle

#### Scenario: Explicit appearance or a change of theme

- **WHEN** a user selects an explicit mode or a theme without this schedule
- **THEN** the local cycle stops affecting the document and the ordinary mode rules apply

#### Scenario: Restore an inactive tab

- **WHEN** a user returns to a tab after its local sunset
- **THEN** the appearance reflects the current local time without replaying the missed hours
