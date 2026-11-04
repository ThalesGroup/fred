## MODIFIED Requirements

### Requirement: Mermaid guidance uses progressive skill loading

The packaged catalog SHALL include one English `graph` skill, presented as Visualization/Visualisation, that selects an appropriate diagram, data chart or table from the user's question, source facts and available rendering tools. It SHALL retain user and model invocation. Common guidance SHALL cover data fidelity, suitable representation, readable labels and supported output formats. Quantitative data, relationships, dates and scores SHALL come from supplied facts or actual tool results.

Mermaid syntax and examples SHALL reside in a packaged reference that the procedure directs the agent to read when Mermaid output is selected. This reference SHALL cover flowcharts, sequence, state, class and entity relationship diagrams, mindmaps, timelines, Gantt charts, pie and XY charts, user journeys and Git graphs without external-documentation downloads. Non-Mermaid output SHALL use the selected tool's supported formats and SHALL NOT require reading the Mermaid reference. Mermaid instructions SHALL remain within the shared skill workflow, without automatic global-prompt injection. The existing frontend Mermaid renderer and sanitization SHALL remain available.

#### Scenario: Mermaid catalog metadata before loading

- **GIVEN** a pod uses the packaged skills directory
- **WHEN** an agent receives its system prompt
- **THEN** the unified `graph` entry is advertised with its description and the existing execution-model-specific hint presentation
- **AND** diagram syntax examples remain absent until the corresponding reference is read

#### Scenario: User or model loads Mermaid

- **WHEN** a user invokes `/graph` with or without text, or the model reads its instructions with ReAct `load_skill` or Deep native `read_file`
- **THEN** the runtime supplies the unified visualization procedure with existing origin attribution and successful-load KPI
- **AND** the procedure directs a read of its packaged Mermaid reference when Mermaid is chosen
- **AND** no tool named `graph` is registered
- **AND** complete returned Mermaid diagrams continue to use the existing frontend renderer
- **AND** Mermaid instructions direct output to a fenced Markdown block in chat, rather than sending Mermaid source to the static HTML artifact viewer
- **AND** display labels and captions use the user's language without introducing the rendering engine unless requested

#### Scenario: The chosen diagram has type-specific guidance

- **WHEN** the procedure selects a Mermaid diagram family
- **THEN** its type-specific syntax and examples are accessible through the same skill's ReAct reference reader and Deep native filesystem
- **AND** applying the procedure does not require external documentation or loading a second skill
- **AND** the reference identifies the existing syntax baseline without claiming unperformed validation

#### Scenario: A numerical chart uses an available renderer

- **GIVEN** verified category values and an available plotting or static HTML rendering tool
- **WHEN** the procedure chooses a representation
- **THEN** its instructions select a suitable chart and use the tool's documented formats
- **AND** the Mermaid reference is conditional on choosing Mermaid, rather than required for every chart
- **AND** missing renderers lead to a useful table or a stated limitation without invented artifacts


### Requirement: Explicit skill selections compose within one turn

Managed web chat SHALL retain and render all explicit platform skill invocations in the same draft, including after another selection. Submission SHALL carry all distinct selected names in first-occurrence order, preserving canonical request text and every invocation occurrence. ReAct SHALL validate all selections and load their instructions before first inference through its existing loading boundary. Deep SHALL validate all selected names and load their instructions using native pinned_skills before inference, without Fred preload; actual reads matching any current selection SHALL retain user origin. Legacy single-selection requests and history SHALL remain supported. Duplicate invocation occurrences SHALL NOT cause duplicate explicit preloads or native pins.

#### Scenario: Select two platform skills

- **WHEN** a user completes `/meeting-minutes`, then `/graph`, and submits the request
- **THEN** both inline selections and surrounding text remain intact
- **AND** both distinct names reach the same execution turn
- **AND** ReAct receives both procedures before inference; Deep receives canonical user text and both native pins before inference

#### Scenario: Independent editing and duplicate occurrences

- **GIVEN** a draft contains two selected skills and a repeated invocation of one
- **WHEN** the user edits or removes one invocation
- **THEN** other recognized invocations remain selected and canonical copy/undo work
- **AND** a name still invoked elsewhere remains selected once for execution

#### Scenario: All-or-error ReAct validation

- **GIVEN** one selected ReAct or Deep skill is unavailable in the serving snapshot
- **WHEN** the request is submitted
- **THEN** it fails clearly before any model call without silently running only the remaining skills

#### Scenario: Preserve selections across history and same-exchange resume

- **WHEN** a multi-skill turn is optimistically rendered, reopened, copied, edited, restarted or resumed through HITL
- **THEN** all explicitly selected names remain represented independently of actual load events
- **AND** same-exchange resume does not duplicate ReAct preload or native pinning and preserves matching native user-origin attribution
- **AND** a fresh follow-up does not inherit those selections

#### Scenario: Combine an inline prompt with platform skills in either order

- **GIVEN** a managed user selects an available `/hello` prompt and two platform skills, in either selection order
- **WHEN** the request is submitted
- **THEN** the exact inline prompt is resolved under its owning team/id and its instructions reach the model alongside both procedures and the remaining request
- **AND** prompt selection, skill badges and their attribution coexist in the draft and history
- **AND** prompt resolution failure sends no partial skills-only turn
- **AND** an explicitly selected prompt homonym is not added as a platform skill

#### Scenario: Recall retains selected prompt and skill identities

- **GIVEN** a sent draft contains a selected prompt sharing a command with a platform skill or another prompt library
- **WHEN** the user recalls the turn and submits it unchanged
- **THEN** the canonical draft, selected prompt id and offset, and selected skills are restored
- **AND** the prompt is resolved only from the current authorized catalogs, without homonym fallback if unavailable
- **AND** equal drafts with different selections remain independently recallable

### Requirement: The first platform skill produces grounded minutes

The platform SHALL distribute English-written `meeting-minutes` instructions with a referenced minutes template under `fred_runtime/skills/meeting-minutes/`. This skill SHALL be user-invocable only. Its instructions SHALL guide the agent to read supplied notes, identify decisions and actions, and report owners or dates as missing when absent, using available document-reading tools.

#### Scenario: Notes omit a deadline

- **GIVEN** notes describe a decision and an assigned action without a deadline
- **WHEN** the agent uses `meeting-minutes` and its reference template
- **THEN** the output includes the supported decision and action and marks the deadline as unspecified
- **AND** it does not invent a deadline

#### Scenario: Only preparatory meeting material is supplied

- **GIVEN** an invitation or agenda describes proposed purchases, an estimated budget and a forecast deployment schedule without confirmed meeting decisions
- **WHEN** the agent uses `meeting-minutes` and its template
- **THEN** the instructions direct a clearly labelled preparatory summary with no confirmed decisions recorded
- **AND** proposed suppliers and budgets are not presented as approved, and project milestones are not inferred as action deadlines

#### Scenario: Evidence-dependent workflows lack sources

- **WHEN** a research, summary, comparison or minutes procedure has insufficient evidence to complete its requested output
- **THEN** its instructions guide the agent to use available context and tools, distinguish evidence from inference, and report the missing information
- **AND** they do not claim to have read unavailable sources or verified unsupported facts

### Requirement: Every prompt command expands in place when the message is sent

On submit, the web client SHALL read every prompt behind a prompt command of the message from its owning library, at that moment and never from a copy read earlier for the menu or a preview, one read per distinct prompt and all reads started together, and SHALL replace each command by that prompt's text at the command's position, keeping the order of the message and the user's own text on its side of each prompt. The model SHALL receive that assembled text and nothing about commands. Platform skills selected in the same message SHALL be requested together, as before. Resolution SHALL be all or nothing: when any prompt cannot be read, is empty, is no longer in its catalog or was picked for another agent, team or personal space, no turn SHALL be sent, no skills-only turn SHALL be sent, the draft SHALL be kept, and the error SHALL name the command it is about and say whether to choose it again or to retry. The message length limit SHALL apply to the assembled text.

#### Scenario: Two prompts expand in order

- **GIVEN** `/summary` whose prompt text is `Summarise the document.` and `/tone` whose prompt text is `Use a formal tone.`
- **WHEN** the user submits `First /summary then /tone please`
- **THEN** the turn's text reads, in this order: `First`, `Summarise the document.`, `then`, `Use a formal tone.`, `please`
- **AND** neither `/summary` nor `/tone` appears in the text the model receives

#### Scenario: A prompt edited since the menu showed it

- **GIVEN** a prompt whose text was read when its row was focused in the menu, and that a teammate edited since
- **WHEN** the user submits the message
- **THEN** the turn carries the text the library holds now

#### Scenario: Prompts and skills in one message

- **GIVEN** two prompt commands and the platform skill `/graph` in one message
- **WHEN** the user submits it
- **THEN** both prompt texts reach the model and the skill name travels with the turn as it does today

#### Scenario: One stale prompt holds the whole message back

- **GIVEN** a message holding `/summary` and `/tone`, and the `tone` prompt was deleted since it was picked
- **WHEN** the user submits it
- **THEN** nothing is sent and the draft is unchanged
- **AND** the error says that `/tone` is no longer available and must be removed and chosen again

#### Scenario: One unreadable prompt asks to retry

- **GIVEN** a message holding `/summary` and `/tone`, and reading `tone` fails with a server error
- **WHEN** the user submits it
- **THEN** nothing is sent and the error says that `/tone` could not be read and to try again in a moment

#### Scenario: The limit counts what is sent

- **GIVEN** a short typed line whose two prompts expand to more characters than the message limit
- **WHEN** the user submits it
- **THEN** nothing is sent and the error states the limit

### Requirement: Common skills include an explicit interview and grounded data workflows

The packaged catalog SHALL publish the following canonical skills and invocation modes, subject to the existing global enablement policy:

| Skill | User invocation | Model invocation |
| --- | --- | --- |
| analyze-data | Unavailable | Available |
| compare-options | Unavailable | Available |
| graph | Available | Available |
| grill-me | Available | Unavailable |
| grounded-research | Available | Available |
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
