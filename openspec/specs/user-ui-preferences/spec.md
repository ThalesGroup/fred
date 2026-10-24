# user-ui-preferences Specification

## Purpose

Defines how authenticated people's durable display choices are saved, restored and isolated across browser data wipes, devices and frontend restarts.

## Requirements

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

After authentication, the frontend SHALL initialize database-backed display preferences only from the authenticated person's database response. An absent record or failed read SHALL apply documented defaults. Existing browser values SHALL NOT seed the database, initialize database-backed preferences or act as a fallback when their database read fails. Database-backed display controls SHALL use in-memory state after the database read and SHALL NOT mirror those preferences to browser storage. Resizable pane widths and trace expansion remain browser-local.

#### Scenario: First load after upgrade

- **WHEN** a person signs in with no database record and their browser still holds an old theme or language choice
- **THEN** signed-in content uses the platform theme default, system mode, navigator language and other documented defaults, and no import PATCH occurs

#### Scenario: Saved database choice

- **WHEN** a person signs in with a saved database record and different browser values
- **THEN** the database values initialize signed-in content and the browser values do not overwrite the record

#### Scenario: Failed database read

- **WHEN** the preference API read fails while the browser retains an older personal choice
- **THEN** signed-in content uses defaults for that load, without applying the browser choice or writing it to the database

#### Scenario: Failed display-preference save

- **WHEN** a sidebar or sort change cannot be saved after a bounded transient retry
- **THEN** the control returns to the last confirmed database value rather than presenting an unsaved choice as durable

#### Scenario: Help language during a preference outage

- **WHEN** a person switches Help Center language while the preference API is unavailable
- **THEN** the documentation changes language immediately and a warning explains that the profile choice was not saved

### Requirement: Preferences resolve before application content paints

The frontend SHALL resolve the signed-in person's database preferences against the current installed and offered theme catalog before painting application content. Before authentication, the static theme boot MAY use public platform settings and OS color mode but SHALL NOT read a personal browser theme or mode choice. On a failed preference read, the frontend SHALL use defaults and retry on a later load.

#### Scenario: New browser

- **WHEN** a person signs in from a new browser
- **THEN** the frontend loads the database preferences before painting application content

#### Scenario: Shared browser

- **WHEN** another person signs in on a browser with a previous person's local choices
- **THEN** the new person's database-backed content uses only the new person's preferences or defaults

### Requirement: Theme IDs remain stable across restarts

A frontend restart with the same built-in themes and deployment `theme-catalog.json` SHALL retain the same theme IDs. Deployment theme authors SHALL use a stable ID for the same theme across archive updates and SHALL NOT reuse an ID for a different theme. A hidden or absent selected ID SHALL remain saved while the frontend uses the existing platform fallback rules.

#### Scenario: Same custom catalog after restart

- **WHEN** the frontend restarts with a catalog that still declares `acme` and a person's saved ID is `acme`
- **THEN** the person sees `acme` after their preferences load

#### Scenario: Temporarily unavailable custom theme

- **WHEN** the catalog no longer declares a person's saved theme ID
- **THEN** the frontend uses the offered platform default or first offered theme and retains the saved ID for a later catalog update
