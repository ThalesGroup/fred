## Purpose

Defines how an authenticated person's UI theme and display-mode choices are saved, loaded and isolated from other accounts across browsers and frontend restarts.

## ADDED Requirements

### Requirement: A person owns their UI preferences

The control plane SHALL let an authenticated person read and replace only their own selected theme ID and display mode. The theme ID SHALL be nullable and, when present, match `^[a-z][a-z0-9-]{0,31}$`; the mode SHALL be `light`, `dark` or `system`. The control plane SHALL treat a valid theme ID as opaque and SHALL NOT require the ID to exist in its frontend catalog. A person with no saved values SHALL have no selected theme ID and use `system` mode.

#### Scenario: Save and read a choice

- **WHEN** an authenticated person saves theme ID `acme` and mode `dark`
- **THEN** a later authenticated read for that person returns `acme` and `dark`, including from another browser

#### Scenario: Unknown catalog ID

- **WHEN** a person saves a well-formed theme ID that the current frontend does not offer
- **THEN** the control plane stores and returns that ID unchanged

#### Scenario: Invalid choice

- **WHEN** a person submits an invalid theme ID or an unsupported mode
- **THEN** the request fails validation and the previously stored preference remains unchanged

#### Scenario: Account isolation

- **WHEN** two authenticated people use the same browser or call the preference API
- **THEN** each receives only their own saved choice, and neither can write the other's choice

### Requirement: Personal choices survive a frontend restart

The frontend SHALL resolve the signed-in person's database preference against the currently installed and offered theme catalog. A restart with the same built-in themes and deployment `theme-catalog.json` SHALL retain the same theme IDs. Deployment theme authors SHALL use a stable ID for the same theme across archive updates and SHALL NOT reuse an ID for a different theme. A hidden or absent selected ID SHALL remain saved while the frontend uses the existing platform fallback rules.

#### Scenario: Same custom catalog after restart

- **WHEN** the frontend restarts with a catalog that still declares `acme` and a person's saved ID is `acme`
- **THEN** the person sees `acme` after their preference loads

#### Scenario: Temporarily unavailable custom theme

- **WHEN** the catalog no longer declares a person's saved theme ID
- **THEN** the frontend uses the offered platform default or first offered theme and retains the saved ID for a later catalog update

### Requirement: The first application paint uses the signed-in person's choice

The frontend SHALL keep a browser cache scoped by authenticated user ID for early theme application, then reconcile it with the database result before painting application content. It SHALL NOT apply a different person's cached preference to the signed-in person's application content. A failed preference read SHALL use that person's scoped cache when available, otherwise the platform default and `system` mode, and SHALL retry on a later load.

#### Scenario: Returning person with a scoped cache

- **WHEN** a person reloads the same browser after saving `cloud` and `dark`
- **THEN** their first painted application content uses Cloud in dark mode

#### Scenario: Different person on the same browser

- **WHEN** a second person signs in on a browser that cached the first person's choice
- **THEN** the second person's application content waits for or uses only the second person's preference, never the first person's choice

#### Scenario: New browser

- **WHEN** a person signs in from a browser without a scoped cache
- **THEN** the frontend loads the database preference before painting application content
