## Purpose

Lets someone who administers a PPT Filler agent retrieve the PowerPoint template
that agent actually holds, so the file that governs every fill can be inspected,
handed over or used as the basis of a variant instead of being write-only.

## ADDED Requirements

### Requirement: The stored template can be retrieved

An agent instance's stored PowerPoint template SHALL be retrievable as the file
that was uploaded, byte for byte, so the retrieved file can be opened in
PowerPoint and re-uploaded unchanged.

The retrieval SHALL name the file so it is recognizable on disk, and SHALL
declare it as a PowerPoint presentation so the operating system opens it with
the right application.

#### Scenario: Retrieving the template of a configured agent

- **WHEN** the template of an agent instance that has one is requested
- **THEN** the uploaded `.pptx` is returned unchanged
- **AND** it is named and typed as a PowerPoint presentation

#### Scenario: The agent carries no template

- **WHEN** the template of an agent instance that has none is requested
- **THEN** the request is refused as not found
- **AND** no empty or placeholder file is returned

### Requirement: Retrieval is restricted to the agent's team

Retrieving a template SHALL require the same access as using the agent it belongs
to: the caller SHALL be authenticated, and SHALL be a member of the team that
owns the agent instance. A caller outside that team SHALL be refused.

Retrieval SHALL be authorized against the caller's own identity, never against
the platform's. A template is configuration material of one team and must not
become readable across teams by being served through a privileged path.

#### Scenario: A member of the owning team

- **WHEN** a member of the team owning the agent requests its template
- **THEN** the template is returned

#### Scenario: A caller outside the owning team

- **WHEN** an authenticated caller who is not a member of that team requests the template
- **THEN** the request is refused
- **AND** no part of the template is returned

#### Scenario: An unauthenticated caller

- **WHEN** the template is requested without an authenticated identity
- **THEN** the request is refused

### Requirement: The option is offered wherever the template is configured

Every surface that lets an administrator configure the PPT Filler template SHALL
also offer to download it, so the file is retrievable from the place it was
uploaded rather than from a separate screen.

The option SHALL be presented as unavailable, not hidden, while the agent holds
no saved template — its absence would otherwise read as the feature being
missing rather than as there being nothing to download.

#### Scenario: An agent with a saved template

- **WHEN** an administrator opens the PPT Filler options of an agent that has a saved template
- **THEN** the download option is offered and usable

#### Scenario: An agent with no template yet

- **WHEN** an administrator opens the PPT Filler options of an agent with no saved template
- **THEN** the download option is visible but unavailable

#### Scenario: A template picked but not yet saved

- **WHEN** an administrator picks a new template file and has not saved it
- **THEN** the download option still offers the saved template, not the picked file
- **AND** an agent with no saved template keeps the option unavailable

### Requirement: A failed retrieval is reported, never silent

When a retrieval cannot complete, the administrator SHALL be told, so a download
that produces nothing is never mistaken for a browser or network quirk.

#### Scenario: Retrieval fails

- **WHEN** the download is triggered and the template cannot be retrieved
- **THEN** the administrator is told the download failed
- **AND** the options panel keeps its current state, with nothing saved or changed
