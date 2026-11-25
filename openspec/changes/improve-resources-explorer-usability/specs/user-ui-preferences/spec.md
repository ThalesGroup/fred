# Spec Delta

## ADDED Requirements

### Requirement: Resources file-browser visibility is a personal preference

The Control Plane SHALL save the Resources file browser's open/closed choice in the authenticated person's existing display-preferences record. The choice SHALL default to closed. Only this visibility choice SHALL be database-backed; tree width and expanded branches SHALL retain their existing browser-local or in-memory behavior.

#### Scenario: Save and restore visibility

- **WHEN** a person opens or closes the Resources file browser
- **THEN** a later read for that person, including from another browser, returns the chosen state
- **AND** other saved preferences remain unchanged

#### Scenario: Default without a saved choice

- **WHEN** a person has no preferences record or the preferences read fails and no failed-write session fallback exists
- **THEN** the Resources file browser starts closed without reading an older browser value

#### Scenario: Keep browser-local tree details

- **WHEN** a person resizes the tree or expands a folder branch
- **THEN** no preferences API write is made for those actions

#### Scenario: Keep choices isolated

- **GIVEN** two people use the same browser
- **WHEN** one person changes the file-browser visibility
- **THEN** the other person's stored visibility is unchanged and only their own preference or default is applied at their next sign-in

### Requirement: Failed personal preference writes remain usable locally

The frontend SHALL keep an authenticated person's chosen display preference active if its database write fails after bounded retry. It SHALL store only failed fields in account-scoped browser session storage, restore them for that person in the same session, and clear each fallback field after a successful write. Browser storage failure SHALL NOT reverse the current choice. The fallback SHALL NOT be imported automatically into the database.

#### Scenario: Save fails while changing a control

- **WHEN** a person opens the Resources file browser or changes another display preference and its database write fails
- **THEN** the control keeps the chosen value and the failed field is available on a reload in the same browser session

#### Scenario: Successful later write

- **GIVEN** a failed field is held in session storage
- **WHEN** a later write for that field succeeds
- **THEN** that field's fallback is removed without clearing unrelated failed fields

#### Scenario: Shared browser

- **GIVEN** one person has a failed-write fallback
- **WHEN** another person signs in on the same browser
- **THEN** the second person receives only their own database values or session fallback

#### Scenario: Session storage unavailable

- **WHEN** a preference write and the session storage write both fail
- **THEN** the current control still keeps the person's choice for the current page lifetime

## MODIFIED Requirements

### Requirement: Database values alone initialize personal preferences

After authentication, the frontend SHALL initialize database-backed display preferences from the authenticated person's database response, overlaid only by account-scoped session fallback created by failed writes in the current browser session. An absent record or failed read SHALL apply documented defaults plus that explicit fallback, if present. Older browser values SHALL NOT seed the database or initialize preferences. Database-backed display controls SHALL use in-memory state after initialization. Resizable pane widths and trace expansion remain browser-local.

#### Scenario: First load after upgrade

- **WHEN** a person signs in with no database record and their browser still holds an old theme or language choice
- **THEN** signed-in content uses the platform theme default, system mode, navigator language and other documented defaults, and no import PATCH occurs

#### Scenario: Saved database choice

- **WHEN** a person signs in with a saved database record and different browser values
- **THEN** the database values initialize signed-in content and the browser values do not overwrite the record

#### Scenario: Failed database read

- **WHEN** the preference API read fails while the browser retains an older personal choice
- **THEN** signed-in content uses defaults plus any explicit failed-write fallback for that person, without applying older browser values or writing them to the database

#### Scenario: Failed display-preference save

- **WHEN** a sidebar or sort change cannot be saved after a bounded transient retry
- **THEN** the control keeps the chosen value in memory and in that person's browser-session fallback

#### Scenario: Help language during a preference outage

- **WHEN** a person switches Help Center language while the preference API is unavailable
- **THEN** the documentation changes language immediately and the choice remains usable in that browser session

### Requirement: Preferences resolve before application content paints

The frontend SHALL resolve the signed-in person's database preferences and any account-scoped failed-write session fallback against the current installed and offered theme catalog before painting application content. Before authentication, the static theme boot MAY use public platform settings and OS color mode but SHALL NOT read a personal browser theme or mode choice. On a failed preference read, the frontend SHALL use defaults plus any explicit failed-write fallback and retry on a later load.

#### Scenario: New browser

- **WHEN** a person signs in from a new browser
- **THEN** the frontend loads the database preferences before painting application content

#### Scenario: Shared browser

- **WHEN** another person signs in on a browser with a previous person's local choices
- **THEN** the new person's signed-in content uses only the new person's database preferences, failed-write session fallback or defaults
