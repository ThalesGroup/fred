## MODIFIED Requirements

### Requirement: Common skills include an explicit interview and grounded data workflows

The packaged catalog SHALL publish the following canonical skills and invocation modes, subject to the existing global enablement policy:

| Skill | User invocation | Model invocation |
| --- | --- | --- |
| analyze-data | Unavailable | Available |
| compare-options | Unavailable | Available |
| graph | Available | Available |
| grill-me | Available | Unavailable |
| grounded-research | Unavailable | Available |
| meeting-minutes | Available | Unavailable |
| summarize-document | Unavailable | Available |

`data-visualization` and `verify-answer` SHALL be absent from the packaged catalog. `graph` SHALL own the combined visualization scope. Existing per-name policy SHALL apply to its retained identity, without automatically transferring a retired name's policy or adding aliases. Instructions SHALL be English and UI titles/descriptions SHALL have French/English presentation. Skills SHALL use available tools without installing dependencies, inventing values or duplicating capability-specific access rules.

`compare-options` SHALL provide a compact procedure centered on decision criteria, comparable evidence and material trade-offs, treating missing values as unknown and using weighted scores only with supplied or approved weights. `summarize-document` SHALL provide a minimal fidelity procedure for ordinary summaries and a conditional packaged reference for multiple conflicting sources, complex documents or explicit fidelity/traceability needs. The core SHALL preserve consequential conditions, numbers, uncertainty and source attribution while following the requested output scope.

Original Fred procedures SHALL include their instructions in packaged resources without requiring external documentation downloads. Imported skills SHALL retain their upstream references and required notices.

#### Scenario: Explicit interview
- **WHEN** the user invokes grill-me
- **THEN** the agent asks adaptive decision questions and investigates accessible facts
- **AND** its method works without an executable Skill tool or mandatory repository/subagent access

#### Scenario: Evidence and missing tools
- **WHEN** a user asks for analysis with incomplete data or unavailable computation
- **THEN** the procedure makes limits explicit and uses supported tools and representations
- **AND** it never claims fabricated computations

#### Scenario: Model-only analysis, comparison and summary
- **WHEN** a user opens the command catalog or directly selects analyze-data, compare-options or summarize-document for execution
- **THEN** these skills are absent from user commands and the direct selections are rejected before inference
- **AND** eligible ReAct and native Deep agents can discover and load all three skills with agent-origin attribution

#### Scenario: Grounded research is model-only
- **WHEN** a user opens the command catalog or directly selects grounded-research for execution
- **THEN** grounded-research is absent from user commands and the direct selection is rejected before inference
- **AND** eligible ReAct agents, native Deep parents and native children can discover and load it autonomously with agent-origin attribution
- **AND** the existing global packaged-skill enablement policy remains effective

#### Scenario: Minutes require an explicit current selection for a new load
- **WHEN** a request has no current explicit meeting-minutes selection
- **THEN** the skill is unavailable for a new autonomous load by a ReAct agent, Deep parent or native child
- **AND** selecting it explicitly permits the existing preload or native pin workflow with user attribution
- **AND** ordinary reuse of already-loaded conversational context retains the existing continuity semantics

#### Scenario: A comparison does not fabricate a ranking
- **GIVEN** alternatives with missing evidence or unspecified priorities
- **WHEN** the model reads compare-options
- **THEN** its compact instructions preserve unknowns and material trade-offs, and reserve weighted scores for supplied or approved weights

#### Scenario: A short summary uses the minimal core
- **GIVEN** a simple supplied document and a short-summary request
- **WHEN** the model reads summarize-document
- **THEN** the core instructions are sufficient without requiring the complex-summary reference
- **AND** the output remains scoped to the user's requested length and purpose

#### Scenario: Complex or fidelity-sensitive summaries have targeted guidance
- **GIVEN** conflicting documents, a complex source or an explicit need for traceable fidelity
- **WHEN** the summary procedure selects its detailed branch
- **THEN** it directs the agent to read its packaged reference through the existing skill reference workflow
- **AND** the guidance preserves source disagreements and consequential qualifications without requiring a new skill or tool

#### Scenario: Retired skills and historical activity
- **WHEN** a fresh request selects data-visualization or verify-answer on an updated packaged runtime
- **THEN** normal unknown-skill validation rejects the selection without aliasing to another procedure
- **AND** existing stored messages, skill activity and usage records remain readable without rewriting their canonical names
