## ADDED Requirements

### Requirement: Capabilities included with an agent without free selection are shown and configurable

For a template that offers no free capability selection
(`supports_capabilities=false`), the agent form SHALL list each capability the
template includes, as advertised to the team, as always active: it SHALL NOT be
switchable off, SHALL carry an "Included" label, and SHALL render its
configuration form. The form SHALL NOT offer capability packs for that template,
and SHALL show a neutral message when the template includes no capability. A save
SHALL store the configuration of every included capability in
`tuning.capability_config`, validated by the pod as for any capability, and SHALL
ignore a submitted selection.

#### Scenario: Bind a graph agent to a library

- **WHEN** a member creates a mindmap agent and, under "Included with this agent", binds document access to one library
- **THEN** the agent is saved with document access selected and its stored config binds that library

#### Scenario: An included capability cannot be turned off

- **WHEN** a member opens the Simple or Advanced capabilities view of such an agent
- **THEN** document access shows an "Included" badge and no switch

#### Scenario: Agent including nothing

- **WHEN** the template offers no free selection and includes no capability
- **THEN** the form shows one neutral message and no "not supported" text

### Requirement: Builtin knowledge search stays within the bound libraries

When an agent instance's active capabilities bind it to libraries (a
`document_scope` chat control with `bound_library_ids`), the builtin
`knowledge.search` SHALL search the intersection of the turn's library
selection and the bound libraries, or the bound libraries when the turn selects
none, whatever the client sends. A selection with no bound library SHALL return
no hits and SHALL NOT search unfiltered.

#### Scenario: API run without a selection

- **WHEN** a client runs a bound agent without any library selection in its runtime context
- **THEN** `knowledge.search` searches only the bound libraries

#### Scenario: Selection outside the binding

- **WHEN** the turn selects only libraries the agent is not bound to
- **THEN** `knowledge.search` returns no hits and does not query Knowledge Flow
