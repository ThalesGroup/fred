## MODIFIED Requirements

### Requirement: Skill invocation controls distinguish user and agent requests

Skills SHALL accept boolean user-invocable (default true) and disable-model-invocation (default false) frontmatter controls. Invalid values SHALL exclude the affected skill with bounded diagnostics. User-ineligible skills SHALL be unavailable for direct user selections but remain eligible for autonomous use unless disabled for model invocation. Explicit-only skills SHALL load only for a current eligible selection. These controls SHALL apply to catalogs, loaders, references, native file searches and children without granting permissions or erasing already-loaded context.

#### Scenario: Agent-only skill
- **WHEN** a skill has user-invocable false and model invocation enabled
- **THEN** it is absent from user commands and direct selections are rejected
- **AND** agents can discover and load it with truthful attribution
- **AND** users authorized for the conversation can preview its eligible instructions without being able to select it as a command

#### Scenario: A selected skill is disabled before sending
- **GIVEN** the composer contains a selected skill that is subsequently disabled globally
- **WHEN** execution rejects the stale selection
- **THEN** the application remains usable and preserves the canonical draft for correction
- **AND** editor history retains only skill identities matching its current document, including undo and redo

#### Scenario: Explicit-only and unavailable skills
- **WHEN** an explicit-only skill is selected by a user
- **THEN** it loads for that request but is unavailable for new autonomous loads on later turns
- **AND** disabling both invocation routes leaves neither route eligible

#### Scenario: Capability aliases preserve target eligibility
- **GIVEN** an eligible skill contains an alias resolving to an ineligible skill
- **WHEN** an agent or system-origin capability reads or concatenates that alias
- **THEN** the resolved target's existing permission and eligibility rules are enforced before returning its content
- **AND** allowed aliases and ordinary non-skill system access retain their existing behavior

### Requirement: Deep native pins preserve truthful load visibility

Explicit Deep selections SHALL be deduplicated in request order and passed as pinned_skills. Successful native instruction loads SHALL emit user-origin activity and usage exactly once per actual load. Unknown, ineligible and globally disabled names SHALL be rejected. Failed native pins SHALL not be reported as successes. Resume and replay SHALL not reload selections. Parent selections SHALL not blindly pin every child.

#### Scenario: Multiple selected skills and resume
- **WHEN** a Deep turn selects two skills and subsequently resumes a human approval
- **THEN** both load natively before inference in selection order
- **AND** the resume does not repeat their loads or usage counts

#### Scenario: Explicit loads appear before reasoning
- **WHEN** initial parent skill loads succeed for the user's explicit selections
- **THEN** their activity rows appear in selection order before the Thinking toggle
- **AND** they remain visible while streaming and when reasoning is collapsed
- **AND** later, autonomous and child loads retain their chronological place inside the reasoning trace

#### Scenario: The trace overview preserves the submitted graph input
- **GIVEN** local content capture is enabled
- **WHEN** a Deep turn submits a canonical user message and selected skill names
- **THEN** the root and trace overview input contain the submitted messages, including the skill command, and pinned_skills
- **AND** model and tool child observations cannot replace that overview input
- **AND** model observations retain their actual messages, including native skill instructions, without inventing a provider-level pinned_skills argument

#### Scenario: A pinned turn completes and survives reload
- **WHEN** native middleware emits multiple partial model updates for a pinned turn
- **THEN** the streamed answer completes with one final response and its usage
- **AND** that response is persisted and remains available after reloading the conversation
- **AND** the current request appears once alongside legitimate previous turns and native skill instructions
- **AND** middleware context repairs do not appear as new tool executions

#### Scenario: Context recovery reuses one observed pin
- **WHEN** native model recovery retries with the same already-read pin
- **THEN** the instructions remain available and exactly one successful load activity and usage count are emitted for that pin
- **AND** a genuinely new pin or independent graph namespace is observed independently
