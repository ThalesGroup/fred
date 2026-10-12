## Purpose

Defines the capability packs offered by the agent form's Simple view: which
packs a team member can switch on, which backend capabilities each one grants,
and how a pack's displayed state is derived from the agent's stored capability
selection so the Simple and Advanced views never disagree.

## ADDED Requirements

### Requirement: Document reading is granted by the document-access packs

The Simple view SHALL NOT offer a standalone pack whose only purpose is to
enable verbatim document reading and exhaustive extraction. Both capabilities
SHALL instead be granted by the two packs that already grant document access —
"Team resources" and "Conversation attachments" — and SHALL be enabled whenever
either of those packs is on.

#### Scenario: Enabling team resources grants the reading capabilities

- **WHEN** a member switches on "Team resources" on an agent with no capability
  selected
- **THEN** verbatim reading and exhaustive extraction are enabled on that agent,
  alongside the pack's other capabilities

#### Scenario: Enabling conversation attachments grants the reading capabilities

- **WHEN** a member switches on "Conversation attachments" on an agent with no
  capability selected
- **THEN** verbatim reading and exhaustive extraction are enabled on that agent

#### Scenario: Reading survives while either pack remains on

- **WHEN** both document-access packs are on and the member switches one of them
  off
- **THEN** verbatim reading and exhaustive extraction remain enabled, because
  the other pack still grants them

#### Scenario: Reading is withdrawn when both packs are off

- **WHEN** the member switches off the last remaining document-access pack
- **THEN** verbatim reading and exhaustive extraction are no longer enabled on
  that agent

#### Scenario: No standalone document-reading pack is offered

- **WHEN** a member opens the Simple capabilities view
- **THEN** no pack card offers document reading on its own

### Requirement: A pack lists the capabilities it grants

Each pack SHALL display, in its expandable list of included capabilities, the
backend capabilities that switching the pack on enables, each with its
availability status for the team. A pack MAY omit a capability that implements
the pack's own premise rather than adding a distinct ability to the agent.

#### Scenario: Team resources lists its granted capabilities

- **WHEN** a member expands the "Team resources" pack
- **THEN** the list shows document access, tabular data, summarization,
  similarity search, verbatim reading, and exhaustive extraction

#### Scenario: Conversation attachments lists its granted capabilities

- **WHEN** a member expands the "Conversation attachments" pack
- **THEN** the list shows summarization, verbatim reading, and exhaustive
  extraction, and omits the document-access capability that implements
  attaching files

#### Scenario: A capability the platform admin has not enabled is marked unavailable

- **WHEN** a pack grants a capability that the platform administrator has not
  enabled for the team
- **THEN** that capability is shown as unavailable in the pack's list, and
  switching the pack on does not enable it

### Requirement: Similarity search stays scoped to the team corpus

Similarity search SHALL be granted only by the "Team resources" pack. The
Simple view SHALL NOT grant it through the "Conversation attachments" pack,
because similarity search does not cover the files attached to a conversation
and would return no result for them.

#### Scenario: Attachments-only agent does not get similarity search

- **WHEN** a member switches on "Conversation attachments" while "Team
  resources" is off
- **THEN** similarity search is not enabled on that agent

### Requirement: Pack state reflects the stored capability selection

A pack's on/off state SHALL be derived from the agent's stored capability
selection rather than held separately, so the Simple and Advanced views cannot
disagree. A document-access pack SHALL derive its state from the document-access
capability alone, never from the capabilities it shares with the other pack —
otherwise clearing one shared capability would read as withdrawing access to
documents entirely. Toggling a pack SHALL leave every capability the pack does
not grant untouched.

#### Scenario: Clearing document access in the Advanced view turns the packs off

- **WHEN** a member clears the document-access capability in the Advanced view
  and returns to the Simple view
- **THEN** both document-access packs are shown as off

#### Scenario: Clearing a shared capability leaves the pack on

- **WHEN** a member clears only summarization or a reading capability in the
  Advanced view, leaving document access on
- **THEN** the pack stays on, and that capability is shown in the pack's list as
  available but not active

#### Scenario: Toggling a pack preserves unrelated capabilities

- **WHEN** a member switches a pack on or off
- **THEN** capabilities granted by no pack, or granted only by other packs that
  remain on, keep their previous state
