## ADDED Requirements

### Requirement: Native skill read guidance requests complete instructions explicitly

Deep parent and native-child guidance SHALL require explicitly requesting 1000
lines when reading a skill's main instructions. It SHALL explain that an omitted
limit can return only 100 lines, require checking the returned window and
truncation information, and direct continuation before applying the procedure.
Complete instructions already present in context SHALL remain reusable.

#### Scenario: Autonomous main-instruction read

- **WHEN** a Deep parent or native child receives its available skill guidance
- **THEN** it is explicitly directed to pass a limit of 1000 for the main skill file
- **AND** it is directed to retrieve remaining instructions before applying them
- **AND** native tool defaults, explicit windows and reference pagination are unchanged

### Requirement: Skill activity discloses partial instruction reads

A successful native first-page skill read SHALL disclose whether its actual
returned window is partial through existing load attribution and activity.
Pagination, size truncation or unproven full coverage SHALL NOT appear as a
confirmed full-file read. French activity SHALL say "Skill partiellement chargé"
and English activity SHALL say "Skill partially loaded" for partial reads.
The flag SHALL survive streaming and history reload with the existing trusted
origin and parent/child attribution. Existing successful-read counting and
continuation/reference exclusions SHALL remain unchanged. This disclosure SHALL
describe the individual read and SHALL NOT assert cumulative page coverage.

#### Scenario: First 100 lines of a longer skill

- **WHEN** a successful native read returns lines 1-100 of a 222-line main skill file
- **THEN** its activity is marked partial in the selected UI language
- **AND** its accessible name and trace label convey the same partial status
- **AND** reloading history preserves that disclosure

#### Scenario: Size-clipped output despite a large requested window

- **WHEN** the requested window could cover the whole skill but the actual output is clipped by size, including inside one source line
- **THEN** the activity is partial regardless of the requested line limit
- **AND** unknown or missing coverage information cannot establish completeness

#### Scenario: Complete and legacy loads

- **WHEN** a native read proves full-file coverage without truncation, a native full pin or ReAct load succeeds, or an older stored activity lacks the new flag
- **THEN** the existing complete-load presentation is retained

#### Scenario: Parent and child windows are independent

- **WHEN** concurrent Deep parent and native-child main-file reads return different coverage
- **THEN** each activity retains its own partial flag and trusted execution identity
- **AND** continuation pages, references, empty windows and failed reads do not add load counts
