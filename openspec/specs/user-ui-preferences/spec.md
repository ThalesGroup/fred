# user-ui-preferences Specification

## Purpose

Defines how authenticated people's durable display choices are saved, restored and isolated across browser data wipes, devices and frontend restarts.

## Requirements

### Requirement: A person owns one display-preferences record

The control plane SHALL let an authenticated person read and partially update only their own preferences. The record SHALL contain a nullable theme ID, `light`/`dark`/`system` mode, nullable `en`/`fr` language, navigation-sidebar collapsed state, `recent`/`alpha` team sort, `name`/`created_at:desc`/`updated_at:desc` agent sort, nullable trace-expansion choice and a bounded map of named pane widths. The theme ID, when present, SHALL match `^[a-z][a-z0-9-]{0,31}$` and SHALL remain opaque to the control plane. An absent record SHALL return the documented defaults and be distinguishable from a saved record.

#### Scenario: Save and read several choices

- **WHEN** an authenticated person sets theme `acme`, mode `dark`, language `fr`, collapses the sidebar and resizes a pane
- **THEN** a later read for that person returns those choices, including from another browser

#### Scenario: Partial update

- **WHEN** a person changes the team sort mode
- **THEN** the saved theme, language and other choices remain unchanged

#### Scenario: Invalid choice

- **WHEN** a person submits an invalid theme ID, mode, language, sort value or pane width
- **THEN** the request fails validation and no stored choice changes

#### Scenario: Account isolation

- **WHEN** two authenticated people use the same browser or call the preferences API
- **THEN** each receives only their own saved choices, and neither can write the other's record

#### Scenario: Account deletion

- **WHEN** a person's account is deleted through the Control Plane
- **THEN** that person's preferences record is deleted with the account

### Requirement: Existing browser choices can seed a new record

After authentication, when no database record exists, the frontend SHALL import valid legacy display choices still present in that browser into the authenticated person's record and mark the browser import complete only after a successful save. It SHALL NOT seed another person's record from those legacy keys or overwrite an existing database record with browser data. Browser data that has already been erased SHALL use defaults. The migration note SHALL make clear that legacy keys do not identify their owner on a shared browser.

#### Scenario: First load after upgrade

- **WHEN** a person signs in with no database record and their browser still holds a valid theme and language choice
- **THEN** those choices seed their database record and are restored on a later browser with cleared storage

#### Scenario: Existing database choice wins

- **WHEN** a person signs in with a saved database record and older browser values
- **THEN** the database values win and the older values do not overwrite the record

#### Scenario: Browser was already wiped

- **WHEN** neither a database record nor legacy browser choices exist
- **THEN** the frontend uses the platform theme default, system mode, navigator language and other documented defaults

### Requirement: Preferences resolve before application content paints

The frontend SHALL resolve the signed-in person's database preferences against the current installed and offered theme catalog before painting application content. It MAY use a browser cache scoped by authenticated user ID while loading. It SHALL NOT apply another person's cached choice to the signed-in person's content. On a failed preference read, it SHALL use that person's scoped cache when available, otherwise defaults, and retry on a later load.

#### Scenario: New browser

- **WHEN** a person signs in from a browser without a scoped cache
- **THEN** the frontend loads the database preferences before painting application content

#### Scenario: Shared browser

- **WHEN** another person signs in on a browser with a previous person's scoped cache
- **THEN** the new person's application content uses only the new person's preferences or defaults

### Requirement: Theme IDs remain stable across restarts

A frontend restart with the same built-in themes and deployment `theme-catalog.json` SHALL retain the same theme IDs. Deployment theme authors SHALL use a stable ID for the same theme across archive updates and SHALL NOT reuse an ID for a different theme. A hidden or absent selected ID SHALL remain saved while the frontend uses the existing platform fallback rules.

#### Scenario: Same custom catalog after restart

- **WHEN** the frontend restarts with a catalog that still declares `acme` and a person's saved ID is `acme`
- **THEN** the person sees `acme` after their preferences load

#### Scenario: Temporarily unavailable custom theme

- **WHEN** the catalog no longer declares a person's saved theme ID
- **THEN** the frontend uses the offered platform default or first offered theme and retains the saved ID for a later catalog update
