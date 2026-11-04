## ADDED Requirements

### Requirement: Common skills include an explicit interview and grounded data workflows

The packaged catalog SHALL include an explicit-only grill-me procedure adapted for general users, a user-facing analyze-data procedure and an agent-only data-visualization procedure. Instructions SHALL be English and UI titles/descriptions SHALL have French/English presentation. New skills SHALL be enabled by default and respect current invocation and administrative policy. They SHALL use available tools without installing dependencies, inventing values or duplicating capability-specific access rules.

#### Scenario: Explicit interview
- **WHEN** the user invokes grill-me
- **THEN** the agent asks adaptive decision questions and investigates accessible facts
- **AND** its method works without an executable Skill tool or mandatory repository/subagent access

#### Scenario: Evidence and missing tools
- **WHEN** a user asks for analysis with incomplete data or unavailable computation
- **THEN** the procedure makes limits explicit and uses supported tools and representations
- **AND** it never claims fabricated computations

### Requirement: Distributed imported skills preserve licensing and provenance

Imported material SHALL record its exact upstream revision and retain required license and copyright notices in distributed packages. Restricted resources SHALL not be copied without rights.

#### Scenario: Packaged interview license
- **WHEN** the runtime distribution includes the adapted Matt Pocock interview
- **THEN** the MIT notice and upstream revision accompany the procedure
