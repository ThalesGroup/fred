## Purpose

Defines how a system that synchronizes a source writes documents into a library
it has been granted — addressed by the source's own identity, versioned by the
source's own versioning, and reconciled without either side keeping a private
record of Fred-side identifiers.

## ADDED Requirements

### Requirement: A document is addressed by the caller's source key, and writing it twice updates one document

A caller SHALL address each document by a source key of its own choosing, unique
within the target library. Fred SHALL derive the document's identity from the
library and that key, so that writing the same key again updates the same
document rather than creating another.

The caller SHALL NOT be required to learn, store or return any Fred-side
identifier in order to update or remove what it wrote.

A source key SHALL be bounded in length and character set, and SHALL NOT be
interpreted: its meaning belongs to the caller.

#### Scenario: Re-writing a source key updates one document

- **WHEN** a caller writes a document at a source key, and later writes different
  content at that same key
- **THEN** the library holds one document for that key, carrying the later
  content, and no second document was created

#### Scenario: A caller needs no Fred-side identifier to maintain its documents

- **WHEN** a caller writes, updates and then removes a document, having retained
  nothing but its own source key
- **THEN** every operation succeeds

#### Scenario: Two libraries may use the same source key independently

- **WHEN** two libraries each receive a document at the same source key
- **THEN** each holds its own document, and updating one leaves the other
  unchanged

### Requirement: Versions come from the source and are never interpreted

A caller MAY attach a version to each document, and MAY record a version for the
library as a whole. Fred SHALL store both, SHALL return them on request, and
SHALL compare a document version only for equality.

Neither version SHALL be parsed, ordered or validated beyond its bounds. A caller
that supplies neither SHALL still be able to write, update and remove documents.

#### Scenario: A library reports the source version it last accepted

- **WHEN** a caller records a source version for a library, and a later run asks
  what version that library holds
- **THEN** the recorded version is returned exactly as it was given

#### Scenario: A source with no versioning of its own is fully served

- **WHEN** a caller writes, updates and removes documents without supplying any
  version
- **THEN** every operation succeeds

#### Scenario: An opaque version is not interpreted

- **WHEN** a caller supplies versions that are not ordered, not dated and not
  numeric
- **THEN** they are stored and returned unchanged, and no behaviour depends on
  their form

### Requirement: Removal is addressed by source key and leaves the library untouched

A caller SHALL remove a document by the same source key it wrote. Removing a
document SHALL NOT require the caller to read the library, rewrite the library's
contents, or restate any of the library's own properties.

Fred SHALL NOT remove a document because a caller stopped mentioning it: a
document disappears when a caller says so.

#### Scenario: Removing a document does not disturb the library

- **WHEN** a caller removes one document from a library that has a name, a
  description and other documents
- **THEN** that document is gone, the library's own properties are unchanged, and
  its other documents remain

#### Scenario: Removing what is already gone is not an error

- **WHEN** a caller removes a source key the library does not hold
- **THEN** the call succeeds and nothing changes

#### Scenario: Silence is not a removal

- **WHEN** a caller writes some of a library's documents and never mentions the
  others
- **THEN** the unmentioned documents remain

### Requirement: A synchronizing write is recorded as a machine write

A write through this surface SHALL be attributed to the service identity that
made it, and SHALL NOT be recorded as activity by a person.

#### Scenario: Automated traffic is distinguishable from human traffic

- **WHEN** a service identity writes a document through this surface
- **THEN** the operational record attributes it to that service rather than to a
  human user

### Requirement: Authorization is scoped to the target library

Writing or removing a document SHALL require permission to write in the target
library. Holding a broad service role SHALL NOT on its own authorize either.

Where a document's path requires folders that do not yet exist within the
library, creating them SHALL be authorized by permission over their parent, so
that one grant over a library reaches its whole subtree and nothing outside it.

A path that would place a document outside the target library SHALL be refused,
and SHALL create nothing.

#### Scenario: A service role alone authorizes nothing

- **WHEN** a caller holding a service identity but no permission over a library
  attempts to write into it
- **THEN** the write is refused

#### Scenario: One grant reaches the whole subtree

- **WHEN** a caller holding permission over a library writes a document several
  folders deep within it
- **THEN** the missing folders are created, the document is written, and no
  further grant was required

#### Scenario: A path cannot escape the library

- **WHEN** a caller writes a document at a path that would leave the target
  library
- **THEN** the write is refused and no folder is created

### Requirement: A write reports its outcome

A write SHALL report whether it succeeded, and on failure SHALL report bounded,
sanitized error information. A caller SHALL NOT have to infer success from the
absence of a failure in a stream of progress.

#### Scenario: A failed write says so

- **WHEN** a document cannot be written
- **THEN** the caller receives a failure carrying bounded error information, and
  no partial document remains in the library
