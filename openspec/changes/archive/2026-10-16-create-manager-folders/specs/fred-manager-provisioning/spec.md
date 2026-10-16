## ADDED Requirements

### Requirement: Authorized folder creation in Resources

The Resources journey SHALL let an admitted person with effective write permission
create a folder at the root or inside a folder of the current personal, team or
project space using fred-manager only. Creation SHALL make no Temporal call; its governance router SHALL require no ingestion client.
The server MUST enforce the person's unique organization and current write authority;
administration, membership or analyst rights alone SHALL NOT grant content writes.

#### Scenario: Create and browse
- **WHEN** an authorized editor creates a folder in the current location
- **THEN** the folder is persisted there and appears in the refreshed first page
- **AND** the user can open it and return using the existing breadcrumb

#### Scenario: Revocation and isolation
- **WHEN** a caller lacks write permission, loses it before a waiting write is admitted, or targets another person's private space or another organization
- **THEN** creation is refused without inserting a folder

#### Scenario: Repeated submission and navigation
- **WHEN** the user submits repeatedly while creation is pending or navigates away
- **THEN** that dialog issues at most one concurrent create request and its completion does not change the new location

### Requirement: Folder creation validates location and name

Creation SHALL trim surrounding whitespace and accept a nonempty single-segment name
of at most 255 Unicode scalar values, without slash, backslash or control characters.
It SHALL preserve the existing 15-level folder ceiling and sibling name uniqueness.
Invalid names/depth SHALL return 422, missing parents 404, foreign-space parents 400,
and duplicate sibling names 409. Refused creations MUST NOT change stored content.

#### Scenario: Invalid name or excessive nesting
- **WHEN** the requested name is invalid or the new folder would exceed 15 levels
- **THEN** the server returns 422 and the UI keeps the dialog open with an error

#### Scenario: Duplicate or invalid parent
- **WHEN** a caller creates an existing sibling name or supplies a missing or foreign-space parent
- **THEN** the server returns the corresponding conflict or location error
- **AND** the UI preserves the entered name and lets the user correct or cancel
