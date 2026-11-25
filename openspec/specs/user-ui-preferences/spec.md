# user-ui-preferences Specification

## Purpose

Defines how authenticated people's durable display choices are saved, restored and isolated across browser data wipes, devices and frontend restarts.

## Requirements

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

### Requirement: A person owns one display-preferences record

The control plane SHALL let an authenticated person read and partially update only their own preferences. The record SHALL contain a nullable theme ID, `light`/`dark`/`system` mode, nullable `en`/`fr` language, navigation-sidebar collapsed state, `recent`/`alpha` team sort, `name`/`created_at:desc`/`updated_at:desc` agent sort. Resizable pane widths and trace expansion SHALL remain in browser localStorage and SHALL NOT be sent to the preferences API. The theme ID, when present, SHALL match `^[a-z][a-z0-9-]{0,31}$` and SHALL remain opaque to the control plane. An absent record SHALL return the documented defaults and be distinguishable from a saved record.

#### Scenario: Save and read several choices

- **WHEN** an authenticated person sets theme `acme`, mode `dark`, language `fr` and collapses the sidebar
- **THEN** a later read for that person returns those choices, including from another browser

#### Scenario: Partial update

- **WHEN** a person changes the team sort mode
- **THEN** the saved theme, language and other choices remain unchanged

#### Scenario: Invalid choice

- **WHEN** a person submits an invalid theme ID, mode, language, sort value or a browser-local display field
- **THEN** the request fails validation and no stored choice changes

#### Scenario: Pane width remains browser-local

- **WHEN** a person resizes a pane and later clears browser storage
- **THEN** the pane returns to its default width and no preferences API write was made for that resize

#### Scenario: Trace expansion remains browser-local

- **WHEN** a person expands or collapses a thought trace and later clears browser storage
- **THEN** the trace returns to its automatic default and no preferences API write was made for that toggle

#### Scenario: Account isolation

- **WHEN** two authenticated people use the same browser or call the preferences API
- **THEN** each receives only their own saved choices, and neither can write the other's record

#### Scenario: Account deletion

- **WHEN** a person's account is deleted through the Control Plane
- **THEN** that person's preferences record is deleted with the account

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

### Requirement: Theme IDs remain stable across restarts

A frontend restart with the same built-in themes and deployment `theme-catalog.json` SHALL retain the same theme IDs. Deployment theme authors SHALL use a stable ID for the same theme across archive updates and SHALL NOT reuse an ID for a different theme. A hidden or absent selected ID SHALL remain saved while the frontend uses the existing platform fallback rules.

#### Scenario: Same custom catalog after restart

- **WHEN** the frontend restarts with a catalog that still declares `acme` and a person's saved ID is `acme`
- **THEN** the person sees `acme` after their preferences load

#### Scenario: Temporarily unavailable custom theme

- **WHEN** the catalog no longer declares a person's saved theme ID
- **THEN** the frontend uses the offered platform default or first offered theme and retains the saved ID for a later catalog update
