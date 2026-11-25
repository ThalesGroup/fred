# Spec Delta

## ADDED Requirements

### Requirement: Resources file-browser visibility is a personal preference

The Control Plane SHALL save the Resources file browser's open/closed choice in the authenticated person's existing display-preferences record. The choice SHALL default to closed. Only this visibility choice SHALL be database-backed; tree width and expanded branches SHALL retain their existing browser-local or in-memory behavior.

#### Scenario: Save and restore visibility

- **WHEN** a person opens or closes the Resources file browser
- **THEN** a later read for that person, including from another browser, returns the chosen state
- **AND** other saved preferences remain unchanged

#### Scenario: Default without a saved choice

- **WHEN** a person has no preferences record or the preferences read fails
- **THEN** the Resources file browser starts closed without reading an older browser value

#### Scenario: Keep browser-local tree details

- **WHEN** a person resizes the tree or expands a folder branch
- **THEN** no preferences API write is made for those actions

#### Scenario: Keep choices isolated

- **GIVEN** two people use the same browser
- **WHEN** one person changes the file-browser visibility
- **THEN** the other person's stored visibility is unchanged and only their own preference or default is applied at their next sign-in

### Requirement: Failed personal preference writes remain usable locally

The frontend SHALL keep an authenticated person's chosen display preference active in memory if its database write fails after bounded retry. The failure SHALL NOT reject the preference save, reverse the control, or show a user-facing error. It MAY log a warning in the browser console. It SHALL NOT store the failed choice in browser storage, and a later load SHALL use the database value or default.

#### Scenario: Save fails while changing a control

- **WHEN** a person opens the Resources file browser or changes another display preference and its database write fails
- **THEN** the control keeps the chosen value for the current page lifetime without a user-facing error or browser-storage write

#### Scenario: Reload after a failed write

- **GIVEN** a preference write failed
- **WHEN** the person reloads the application
- **THEN** the database value or documented default is applied

#### Scenario: Shared browser

- **GIVEN** one person has an unsaved in-memory choice
- **WHEN** another person signs in on the same browser
- **THEN** the second person receives only their own database values or defaults

## MODIFIED Requirements

### Requirement: Database values alone initialize personal preferences

After authentication, the frontend SHALL initialize database-backed display preferences from the authenticated person's database response. An absent record or failed read SHALL apply documented defaults. Older browser values SHALL NOT seed the database or initialize preferences. Database-backed display controls SHALL use in-memory state after initialization. Resizable pane widths and trace expansion remain browser-local.

#### Scenario: First load after upgrade

- **WHEN** a person signs in with no database record and their browser still holds an old theme or language choice
- **THEN** signed-in content uses the platform theme default, system mode, navigator language and other documented defaults, and no import PATCH occurs

#### Scenario: Saved database choice

- **WHEN** a person signs in with a saved database record and different browser values
- **THEN** the database values initialize signed-in content and the browser values do not overwrite the record

#### Scenario: Failed database read

- **WHEN** the preference API read fails while the browser retains an older personal choice
- **THEN** signed-in content uses defaults without applying older browser values or writing them to the database

#### Scenario: Failed display-preference save

- **WHEN** a sidebar or sort change cannot be saved after a bounded transient retry
- **THEN** the control keeps the chosen value in memory without a user-facing error or browser-storage write

#### Scenario: Help language during a preference outage

- **WHEN** a person switches Help Center language while the preference API is unavailable
- **THEN** the documentation changes language immediately and the choice remains usable until the page reloads

### Requirement: Preferences resolve before application content paints

The frontend SHALL resolve the signed-in person's database preferences against the current installed and offered theme catalog before painting application content. Before authentication, the static theme boot MAY use public platform settings and OS color mode but SHALL NOT read a personal browser theme or mode choice. On a failed preference read, the frontend SHALL use defaults and retry on a later load.

#### Scenario: New browser

- **WHEN** a person signs in from a new browser
- **THEN** the frontend loads the database preferences before painting application content

#### Scenario: Shared browser

- **WHEN** another person signs in on a browser with a previous person's local choices
- **THEN** the new person's signed-in content uses only the new person's database preferences or defaults
