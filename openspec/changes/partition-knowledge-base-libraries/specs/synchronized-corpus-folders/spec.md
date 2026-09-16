## Purpose

Keeps a corpus folder written by a machine distinct from one written by people:
how it is marked, what a person may and may not do to it, and how everything it
holds is read back.

## ADDED Requirements

### Requirement: A corpus folder records the machine that synchronizes it

A folder SHALL be able to record that a machine writes it, as a qualified owner
reference naming what owns it and which one. The record SHALL be writable by a
service identity alone, so that no person can mark a folder — their own or
anyone's — as machine-written.

A folder nested beneath a marked folder SHALL be treated as machine-written
without carrying a record of its own, so that the two can never disagree.

A folder carrying no such record SHALL behave exactly as a corpus folder behaves
today, in every respect.

#### Scenario: A service identity marks a folder it is about to fill

- **WHEN** a service identity records a machine owner against a folder it holds
  the right to write in
- **THEN** the folder is marked, and reports its owner to anyone who may read it

#### Scenario: A person cannot mark a folder

- **WHEN** a person attempts to record a machine owner against any folder
- **THEN** the attempt is refused, whatever rights that person holds over it

#### Scenario: Nesting is derived, never copied

- **WHEN** a folder is created beneath a marked folder, at any depth
- **THEN** it is treated as machine-written
- **AND** it carries no record of its own that could drift from its root's

#### Scenario: An unmarked folder is untouched by this capability

- **WHEN** a person acts on a folder carrying no machine owner
- **THEN** every operation behaves exactly as it did before this capability
  existed

### Requirement: A machine-written folder refuses content changes from a person

The system SHALL refuse, from a person, every change to what a machine-written
folder contains or is called: adding a document, removing a document, creating a
folder inside it, and renaming or moving it.

A refusal SHALL name the base the folder belongs to, so the reader learns why
rather than only that they may not.

The service identity that synchronizes the folder SHALL keep exactly the rights
it holds today; this requirement removes nothing from it.

The refusal SHALL be decided after the existing authorization check, so that a
caller holding no right over the folder is still told they hold no right, and
learns nothing about the folder from being refused.

#### Scenario: A person may not add a document to it

- **WHEN** a person holding the right to write in a machine-written folder
  uploads a document into it
- **THEN** the upload is refused, naming the base the folder belongs to
- **AND** no document is created

#### Scenario: A person may not create a folder inside it

- **WHEN** a person creates a folder beneath a machine-written folder
- **THEN** the creation is refused

#### Scenario: A person may not rename or move it

- **WHEN** a person renames a machine-written folder, or moves it under another
- **THEN** the change is refused, and the folder keeps the name recorded when it
  was created

#### Scenario: The synchronizing machine is unaffected

- **WHEN** the service identity that owns the folder writes, updates, removes a
  document, or creates a folder beneath it
- **THEN** every operation succeeds exactly as it does today

#### Scenario: Having no right is still reported as having no right

- **WHEN** a person holding no right over a machine-written folder attempts to
  change it
- **THEN** they are refused for lacking the right, not for the folder being
  machine-written

### Requirement: Deleting a machine-written folder stays available to people

A machine-written folder SHALL remain deletable by a person holding the right to
delete it, with the same cascade over its nested folders and documents as any
other corpus folder.

The confirmation offered before deleting SHALL name the base the folder belongs
to, so that the reader understands they are removing what a base fills and not
only a folder.

This is deliberate and is the one asymmetry in this capability: content is
guarded, existence is not.

#### Scenario: A person deletes a machine-written folder

- **WHEN** a person holding the right to delete it confirms the deletion
- **THEN** the folder, everything nested beneath it and their documents are
  removed, exactly as for any other folder

#### Scenario: The confirmation says what is being removed

- **WHEN** a person is asked to confirm deleting a machine-written folder
- **THEN** the confirmation names the base that fills it

### Requirement: A library's documents are listed in full, however they are nested

Listing the documents a library holds SHALL include every document held in a
folder nested beneath it, at any depth, and not only those sitting directly in
the library.

The total reported alongside the listing SHALL count that same set, so that
paging through the listing reaches every document counted.

A library whose documents all sit in nested folders SHALL NOT be reported as
holding none.

#### Scenario: Documents nested below the library are listed

- **WHEN** the documents of a library holding documents in nested folders are
  listed
- **THEN** the listing includes documents from every depth beneath it

#### Scenario: The total matches what can be paged through

- **WHEN** a listing reports a total
- **THEN** paging through the listing reaches exactly that many documents

#### Scenario: A library mirroring a source tree is not reported empty

- **WHEN** a library whose every document sits in a nested folder is listed
- **THEN** it reports the documents it holds, and is not presented as empty
