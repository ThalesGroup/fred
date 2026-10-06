## Purpose

Let users and agents apply platform-owned Markdown workflows through one shared, read-only skill catalog, with progressive loading, normal conversation continuity and visible invocation in managed web chat.

## ADDED Requirements

### Requirement: Platform skills are published from a startup snapshot

The deployment SHALL configure an optional skill directory whose immediate skill subdirectories contain `SKILL.md` with a valid unique `name`, a `description` and Markdown instructions. Skill contents and references SHALL be read-only to agents. The pod SHALL publish a validated snapshot at startup and use it for catalog and file reads until restart. Invalid, duplicate, oversized or unreadable skills SHALL be excluded with bounded diagnostics without preventing other skills or the pod from working. The supported first-version catalog size SHALL be a few dozen skills; it SHALL NOT require a separate search service.

#### Scenario: No directory configured
- **WHEN** a pod starts without skill configuration
- **THEN** it exposes no skills or skill-loading tools
- **AND** the composed prompts are byte-identical to the previous no-skills behavior

#### Scenario: Invalid skill beside valid skills
- **GIVEN** the directory contains a valid skill and a malformed, duplicate or oversized skill
- **WHEN** the pod builds its snapshot
- **THEN** the valid skill is usable, affected invalid entries are excluded and diagnostics identify the problem without dumping file contents

#### Scenario: Restart publishes edits
- **GIVEN** a running pod has published a skill and its reference files
- **WHEN** their on-disk contents change
- **THEN** existing catalog entries and reads retain the startup version until restart
- **AND** after restart, new loads in new or existing conversations use the newly validated snapshot without rewriting historical messages

### Requirement: The system prompt advertises the skill catalog

Every ReAct agent, DeepAgent and Deep child with skills configured SHALL receive the same validated catalog names and descriptions inside the existing system prompt `<tools>` block. The catalog SHALL explain how to load instructions and references, without injecting all skill bodies. Catalog content SHALL NOT create or close reserved prompt-layer tags or alter platform instruction precedence. An empty catalog SHALL render no skill section.

#### Scenario: Catalog placement and progressive loading
- **WHEN** a supported agent begins a request with valid skills available
- **THEN** their names and descriptions appear within `<tools>`
- **AND** their full instructions are absent until loaded
- **AND** reserved tags in metadata cannot forge a higher-priority prompt block

### Requirement: Agents can load and combine skills through shared tools

Supported agents SHALL be able to choose a skill by its catalog name, obtain its instructions through a loading tool, read its references and continue their normal model/tool loop before responding. One request SHALL support multiple skills. Deep children SHALL have the same loading interface without receiving tools or permissions absent from their own execution context. No per-agent skill selection SHALL be required.

#### Scenario: Automatic selection and iteration
- **WHEN** a user's ordinary request matches a skill's description
- **THEN** the model can load that skill, consult a reference, call an available task tool and produce a final response
- **AND** this sequence works for ReAct, DeepAgent and a Deep child

#### Scenario: Several procedures contribute to a request
- **WHEN** the agent selects two different skills for one request
- **THEN** both instruction sets can be loaded and used without replacing one another or ending the tool loop

### Requirement: Skill file access stays within the declared skill

Skill loading SHALL resolve a catalog name on the server. Reference reads SHALL resolve a relative file path within that skill's published directory, support bounded UTF-8 text and reject traversal, absolute host paths, escaping symlinks, unsupported content and writes. Skill access SHALL NOT expose arbitrary host or conversation files, execute scripts, install tools or grant permissions. A frontmatter tool hint SHALL NOT be treated as a permission grant or an enforced restriction.

#### Scenario: Read an associated template
- **WHEN** an agent reads `references/modele-compte-rendu.md` from the valid `compte-rendu` skill
- **THEN** it receives that snapshot's reference text without needing general filesystem access

#### Scenario: Escape or write attempt
- **WHEN** a request attempts to read outside the selected skill or modify its files
- **THEN** the operation is refused without returning unrelated file contents

### Requirement: Web users can require a skill for their request

Managed web chat SHALL accept `/skill <name> <request>` and offer skill-name autocompletion from the selected agent's actual runtime catalog. Submission SHALL transmit a typed skill selection and the trailing request; the server SHALL validate and load the selected skill before the first model call, independently of model choice. The body SHALL be resolved from the server snapshot rather than trusted from client-supplied instructions. A bare `/skill` SHALL offer selection guidance without launching an empty agent turn. An unknown, invalid or unavailable explicit selection SHALL fail clearly before any model call, with no fallback to another skill or a prompt command.

#### Scenario: Explicit load precedes inference
- **WHEN** an authorized user submits `/skill compte-rendu prepare the minutes from these notes`
- **THEN** the runtime loads `compte-rendu` before its first model call
- **AND** the model receives those instructions and the trailing request

#### Scenario: Stale menu or forged selection
- **WHEN** a submitted name is unavailable in the serving pod's validated snapshot
- **THEN** the runtime reports an explicit selection error and does not call the model

#### Scenario: Keyboard and agent switching
- **WHEN** the user types the skill prefix and navigates the suggestions
- **THEN** arrow keys, completion, submission and dismissal work through the existing composer interaction
- **AND** switching the selected agent invalidates suggestions from the previous runtime

### Requirement: The skill dispatcher reserves its prompt command

The composer SHALL reserve `skill` for platform skill invocation. Prompt create/update/import paths SHALL refuse assigning that exact command and SHALL identify the reserved-name conflict. Existing prompts carrying `skill` SHALL retain their text and remain accessible through the library, but SHALL NOT be offered or dispatched as `/skill` prompt commands. Users SHALL be able to rename their command, and the migration guide SHALL explain this required action. Other prompt commands and their historical attribution SHALL remain unchanged.

#### Scenario: Legacy homonym
- **GIVEN** a team has a prompt whose command is `skill`
- **WHEN** the new composer is used
- **THEN** `/skill` opens the skill workflow and the prompt remains available through its library
- **AND** renaming its command restores prompt-command invocation

#### Scenario: New or imported reservation conflict
- **WHEN** prompt creation, command reassignment or import attempts to assign `skill`
- **THEN** it is refused with an actionable reserved-command error
- **AND** other accepted command names keep their existing behavior

#### Scenario: Editing a legacy prompt
- **GIVEN** a stored prompt already has the command `skill`
- **WHEN** its other fields are edited without changing that command
- **THEN** the edit remains allowed and the prompt stays accessible through its library
- **AND** renaming the command uses the ordinary prompt editor

### Requirement: Loaded instructions retain contextual continuity

The runtime SHALL retain loaded instructions and reference outputs in the conversation's normal message/checkpoint flow after a response. It SHALL NOT erase them merely because a turn ended or create a persistent active-skill mode. Agent guidance SHALL apply procedures according to the current request and the platform instruction hierarchy. Existing history budgets SHALL continue to apply; this capability SHALL NOT guarantee permanent full-text retention after trimming. An agent SHALL be able to reload a skill if its instructions are no longer available in context.

#### Scenario: Follow-up continues the same work
- **GIVEN** an agent loaded a skill and asked the user for clarification
- **WHEN** the user answers in the same conversation
- **THEN** the prior instructions remain available under normal history rules and the agent can continue the procedure

#### Scenario: A different request arrives
- **WHEN** the user changes to an unrelated request after a skill-guided response
- **THEN** no persistent selection forces the old procedure onto the new request
- **AND** the agent can choose other relevant skills

### Requirement: Skill loads have truthful compact attribution

Web chat SHALL show a compact load step containing the skill name and whether it was requested by the user or chosen by an agent. Runtime history SHALL preserve this attribution without requiring the current skill file to exist. Each actual load SHALL be represented once, including Deep-child loads; human-requested preloading SHALL NOT be represented as a model-issued tool call that never happened. Full instruction inspection in the web UI SHALL NOT be required.

#### Scenario: Explicit and automatic loads are distinguishable
- **WHEN** a user-required load or a model-selected load succeeds
- **THEN** its compact step identifies the correct origin and skill name
- **AND** reopening the conversation retains the attribution without duplicating the step

### Requirement: Skills respect available tools and existing authorization

Catalog access, explicit selection and skill tools SHALL use the serving runtime's existing authentication, managed-agent/team authorization and execution limits. Skill instructions SHALL NOT expand an agent's tools or bypass platform policies. When a required task tool or input is absent, agent guidance SHALL complete independently feasible work and explain the blocked portion, asking for necessary input when appropriate instead of inventing results or transferring automatically.

#### Scenario: Partial procedure can be completed
- **WHEN** a skill requests preparing and sending minutes but the agent has no sending tool
- **THEN** it can prepare the minutes and report that sending remains incomplete
- **AND** no tool or permission is automatically provisioned

#### Scenario: Unauthorized managed access
- **WHEN** a caller lacks permission to use the selected managed agent/team
- **THEN** catalog access and execution are refused through the existing authorization boundary

### Requirement: The first platform skill produces grounded minutes

The platform SHALL distribute a `compte-rendu` skill with a referenced minutes template. Its instructions SHALL guide the agent to read supplied notes, identify decisions and actions, and report owners or dates as missing when absent. It SHALL work through explicit web invocation and automatic model selection with available document-reading tools.

#### Scenario: Notes omit a deadline
- **GIVEN** notes describe a decision and an assigned action without a deadline
- **WHEN** the agent uses `compte-rendu` and its reference template
- **THEN** the output includes the supported decision and action and marks the deadline as unspecified
- **AND** it does not invent a deadline
