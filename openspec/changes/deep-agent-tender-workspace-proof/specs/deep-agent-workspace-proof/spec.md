## Purpose

Defines the first observable proof that a Fred Deep Agent can complete a fixed multi-document task,
retain an explicit plan and return only verified Workspace artifacts.

## ADDED Requirements

### Requirement: The Deep Agent completes the versioned tender scenario

The Deep Agent SHALL execute the canonical `reliable-tender-work-completion` prompt against only
the ingested `public-tender-response/source/` documents and SHALL account for every numbered user
instruction before finalizing.

#### Scenario: Later clarifications override initial requirements

- **GIVEN** the synthetic knowledge base is ingested without its validation files
- **WHEN** the canonical prompt is executed
- **THEN** the result uses 30 September 2027, 2.8 million documents and 99.90% availability
- **AND** it does not silently reuse any superseded value

#### Scenario: Evidence gaps remain gaps

- **GIVEN** certification, reference, staffing and price evidence is incomplete or non-compliant
- **WHEN** the agent derives its recommendation
- **THEN** it reports a conditional no-go and the four elimination blockers
- **AND** it does not present planned renewals, assignments or discounts as completed facts

### Requirement: Deep working state uses the canonical backends

The Deep runtime SHALL use native Deep state for ephemeral scratch and the scoped Fred Workspace
backend for durable `/workspace/` files. It SHALL NOT route the proof through legacy `/fs`, a host
filesystem, or a second storage client.

#### Scenario: Explicit plan survives into the next turn

- **GIVEN** an authorized Deep execution with scoped Workspace access
- **WHEN** the agent writes and updates `/workspace/plan.md`
- **THEN** the same team, user, agent-instance and session binding can read it in a later turn
- **AND** another binding cannot access it

#### Scenario: Command execution is unavailable

- **GIVEN** the Deep runtime uses its state and Fred Workspace backends
- **WHEN** the model tool set is assembled
- **THEN** command execution is not exposed
- **AND** every exposed filesystem tool has a concrete bounded implementation

### Requirement: User deliverables are verified typed artifacts

The agent SHALL create `compliance-matrix.csv`, `bid-recommendation.md`, and `response-plan.md`
through the existing text-artifact publication boundary and SHALL verify their persisted content
before claiming completion.

#### Scenario: All requested artifacts are real and consistent

- **GIVEN** publication succeeds for all three outputs
- **WHEN** the agent completes its verification step
- **THEN** each file exists, is non-empty and can be read from `/workspace/`
- **AND** the CSV contains every numbered requirement
- **AND** the three outputs agree on the recommendation, blockers, risks and dates
- **AND** the final runtime/history parts contain the corresponding persisted `LinkPart` values

#### Scenario: Publication failure stays truthful

- **GIVEN** one final artifact write or publication fails
- **WHEN** the agent produces its final response
- **THEN** it names the incomplete artifact and retains unaffected work
- **AND** it emits no success claim, filename-as-proof, or invented download URL for that artifact

### Requirement: The human decision follows dossier preparation

The first proof SHALL end with a request for human go/no-go validation after the dossier has been
prepared and verified. It SHALL NOT claim that the bid was approved or submitted.

#### Scenario: Human validation is requested at the correct boundary

- **GIVEN** the available analysis and artifacts are complete
- **WHEN** the agent reaches the end of the canonical prompt
- **THEN** it summarizes the conditional recommendation and verified deliverables
- **AND** it asks the user to make the final decision without introducing a new HITL mechanism

### Requirement: A proof run is reproducible and honestly reported

An acceptance record SHALL identify the fixture and Fred revisions, agent/template, model profile,
enabled capabilities, duration, tool/model calls, token usage when available, rubric score, hard
failures and verified artifact paths.

#### Scenario: First witnessed success meets the rubric

- **GIVEN** the same committed fixture and canonical prompt
- **WHEN** a Deep Agent run is accepted as the first proof
- **THEN** its recorded score is at least 80/100
- **AND** it has no hard failure from the committed evaluation rubric
- **AND** the record describes one witnessed run rather than claiming statistical reliability
