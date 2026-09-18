## Purpose

Defines what an agent template may declare as the starting point for a new
instance — which capabilities are pre-selected, how they are pre-configured, and
whether reasoning is offered and pre-armed — and the rules that keep those
declarations a seed the creating member can change rather than a lock.

## ADDED Requirements

### Requirement: A template may declare default configuration per capability

An agent template SHALL be able to declare default configuration values for the
capabilities it pre-selects, so a new instance starts configured rather than
merely equipped. The declaration SHALL carry configuration only; which
capabilities are pre-selected remains a separate declaration.

#### Scenario: A pre-configured capability reaches a new instance

- **WHEN** a member creates an agent from a template that declares default
  configuration for one of its pre-selected capabilities
- **THEN** the creation form starts with that configuration applied, and saving
  without touching it persists those values on the new instance

#### Scenario: The form reflects the declared configuration

- **WHEN** a template declares a configuration that determines how a capability
  pack is displayed
- **THEN** the creation form shows that pack in the state the declared
  configuration produces, so what the member sees matches what the agent will do

#### Scenario: Declared configuration is validated where it is declared

- **WHEN** a template declares default configuration that the capability's own
  schema rejects
- **THEN** the failure surfaces against the template rather than silently
  producing an agent that fails later when it is assembled

### Requirement: Template defaults are a seed, never a lock

Defaults declared by a template SHALL apply to newly created instances only, and
SHALL remain editable by the member creating the agent. An existing instance
SHALL NOT change behaviour when its template's defaults change.

#### Scenario: The member overrides a default before saving

- **WHEN** a member unticks a pre-selected capability, or edits its
  pre-configured values, before saving a new agent
- **THEN** the agent is created with the member's choice, not the template's

#### Scenario: An existing agent is unaffected by a template default change

- **WHEN** a template's declared defaults change after an agent was created from it
- **THEN** that agent keeps the capabilities and configuration stored at its last
  save

### Requirement: Defaults never exceed what the team may use

A template's declared defaults SHALL be narrowed to the capabilities the team is
allowed to use before they are offered. A default for a capability the team
cannot use SHALL be neither pre-selected, nor displayed, nor submitted.

#### Scenario: A default the team is not enabled for is dropped silently

- **WHEN** a member of a team creates an agent from a template whose defaults
  include a capability the team is not enabled for
- **THEN** that capability is absent from the form and from the created agent,
  and the creation succeeds with the remaining defaults

### Requirement: A template may declare its reasoning posture

An agent template SHALL be able to declare both that it offers per-question
reasoning and that new conversations start with reasoning already on. Neither
declaration SHALL override the platform's own reasoning gating.

#### Scenario: A reasoning-first template pre-arms new conversations

- **WHEN** a member creates an agent from a template declaring both reasoning
  settings, and later opens a new conversation with that agent
- **THEN** the agent offers reasoning and the conversation starts with it on

#### Scenario: A deployment without a reasoning-capable model is unaffected

- **WHEN** such an agent runs on a deployment where no model has reasoning enabled
- **THEN** no reasoning control is offered in the conversation, and the agent
  answers normally

### Requirement: A knowledge assistant template is available off the shelf

The platform SHALL offer a template that starts pre-equipped to answer questions
from the team's written material, covering the team corpus, the files attached to
a conversation, and the team wiki, and able to return its answer as a document.
It SHALL remain a starting point the member can narrow, not a fixed agent.

#### Scenario: Creating the knowledge assistant needs no capability picking

- **WHEN** a member of a team enabled for its capabilities creates an agent from
  this template and saves without opening the capabilities view
- **THEN** the agent can search the team corpus and the conversation's
  attachments, read the team wiki, and produce a downloadable document

#### Scenario: The blank-slate template is still the generic starting point

- **WHEN** a member browses the available templates
- **THEN** the pre-equipped knowledge assistant is offered alongside the
  blank-slate template, which keeps declaring no default capabilities
