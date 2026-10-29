# Platform Agent Skills Specification

## Purpose

Let users and agents apply platform-owned Markdown workflows through one shared, read-only skill catalog, with progressive loading, normal conversation continuity and visible invocation in managed web chat.

## Requirements

### Requirement: Platform skills are published from a startup snapshot

Platform-distributed skills and their reference files SHALL reside under `fred_runtime/skills/` in the `fred-runtime` package and SHALL be included in its wheel and source distribution. The deployment SHALL configure an optional skill directory whose immediate skill subdirectories contain `SKILL.md` with a valid unique `name`, a `description` and Markdown instructions. The packaged directory SHALL be resolvable from an installed runtime outside the repository. Omitting skill configuration SHALL enable the packaged directory. Explicit null SHALL disable skills. A configured custom directory SHALL retain its existing behavior. Skill contents and references SHALL be read-only to agents. The pod SHALL publish a validated snapshot at startup for the web catalog, ReAct explicit preload, preview and ReAct reads until restart. Deep native reads SHALL use the physical configured directory through upstream FilesystemBackend. Invalid, duplicate, oversized or unreadable skills SHALL be excluded from the web/ReAct snapshot with bounded diagnostics without preventing other skills or the pod from working. The supported first-version catalog size SHALL be a few dozen skills; it SHALL NOT require a separate search service.

#### Scenario: Skills available from an installed runtime distribution

- **GIVEN** `fred-runtime` is built and installed outside the monorepo checkout
- **WHEN** a pod is configured to use its packaged skills directory
- **THEN** the shipped skills and references are discoverable and readable from that distribution
- **AND** no copy of those files under `apps/fred-agents` is required

#### Scenario: No directory configured

- **WHEN** a pod starts without skill configuration
- **THEN** it exposes the packaged catalog with progressive loading
- **AND** explicitly setting skills to null instead exposes no skills, loading tools, catalog or body

#### Scenario: Invalid skill beside valid skills

- **GIVEN** the directory contains a valid skill and a malformed, duplicate or oversized skill
- **WHEN** the pod builds its snapshot
- **THEN** the valid skill is usable, affected invalid entries are excluded and diagnostics identify the problem without dumping file contents

#### Scenario: Restart publishes edits

- **GIVEN** a running pod has published a skill and its reference files
- **WHEN** their on-disk contents change
- **THEN** web catalog entries, previews, explicit ReAct preloads and ReAct reads retain the startup version until restart, while Deep native reads see the current physical file
- **AND** after restart, new loads in new or existing conversations use the newly validated snapshot without rewriting historical messages

### Requirement: The system prompt advertises the skill catalog

Every ReAct agent with skills configured SHALL receive validated catalog names, descriptions and optional advisory argument hints inside the existing system prompt `<tools>` block. Deep parents and native children SHALL receive the upstream native catalog through create_deep_agent skills configuration, without a duplicate Fred catalog or replacement loading middleware; Fred policy hooks SHALL filter eligibility without replacing upstream loading. Both catalogs SHALL explain progressive instruction/reference loading without injecting all skill bodies. ReAct catalog content SHALL escape reserved prompt-layer tags and render no section when empty. Deep SHALL use upstream formatting and its native empty-source section; its trusted source files SHALL follow the platform instruction hierarchy.

#### Scenario: Catalog placement and progressive loading

- **WHEN** a ReAct agent begins a request with valid skills available
- **THEN** their names, descriptions and available advisory hints appear within `<tools>`
- **AND** their full instructions are absent until loaded
- **AND** reserved tags in metadata cannot forge a higher-priority prompt block

#### Scenario: Procedural instructions do not define executable tools

- **WHEN** a catalog entry is advertised or its instructions are loaded by a user or agent
- **THEN** the context explicitly identifies the skill as a procedure to follow, not a callable function
- **AND** argument hints are identified as useful user input rather than tool schemas or JSON parameter names
- **AND** loading does not register a tool named after that skill

#### Scenario: Platform rules allow the advertised procedure without trusting arbitrary content

- **WHEN** a configured catalog skill is read through its declared loader or supplied by the runtime as a selected skill
- **THEN** the platform instructions permit applying its task procedure under the existing platform instruction hierarchy
- **AND** documents and arbitrary tool results cannot claim procedural authority merely through a skill name, filesystem path or reserved tag
- **AND** the procedure cannot change platform rules, permissions or the declared tool set

### Requirement: Mermaid guidance uses progressive skill loading

The packaged catalog SHALL include an English `graph` skill, presented as Graphs, with an advisory argument hint. Its procedure SHALL choose a representation suited to the question and source facts, with type-specific syntax and examples in a single self-contained `SKILL.md`. It SHALL cover flowcharts, sequence, state, class and entity relationship diagrams, mindmaps, timelines, Gantt charts, pie and XY charts, user journeys and Git graphs without requiring reference-file or external-documentation reads. Quantitative data, relationships, dates and scores SHALL come from supplied facts or actual tool results. Mermaid instructions SHALL be loaded only through the shared skill workflow; runtime prompt assembly SHALL NOT inject the former SDK output contract automatically. The existing frontend Mermaid renderer and sanitization SHALL remain available.

#### Scenario: Mermaid catalog metadata before loading

- **GIVEN** a pod uses the packaged skills directory
- **WHEN** an agent receives its system prompt
- **THEN** `graph` is advertised with its description in the native Deep index or with its description and advisory hint in the ReAct catalog
- **AND** its diagram syntax instructions are absent until loaded

#### Scenario: User or model loads Mermaid

- **WHEN** a user invokes `/graph` with or without text, or the model reads its instructions with ReAct `load_skill` or Deep native `read_file`
- **THEN** the runtime supplies its instructions with the existing origin attribution and successful-load KPI
- **AND** no tool named `graph` is registered
- **AND** complete returned Mermaid diagrams continue to use the existing frontend renderer
- **AND** Mermaid instructions direct output to a fenced Markdown block in chat, rather than sending Mermaid source to the static HTML artifact viewer
- **AND** display labels and captions use the user's language without introducing the rendering engine unless requested

#### Scenario: The chosen diagram has type-specific guidance

- **WHEN** the graph procedure selects a representation
- **THEN** its syntax guidance and examples are included in the same instructions through both the ReAct skill loader and the Deep native filesystem
- **AND** applying the procedure does not require fetching external documentation or another graph skill file
- **AND** the guidance identifies the installed syntax baseline without claiming unperformed validation

### Requirement: Agents can load and combine skills through shared tools

Supported agents SHALL be able to choose a skill by its catalog name, obtain its instructions through its runtime-specific loading interface, read its references and continue their normal model/tool loop before responding. One request SHALL support multiple skills. Deep children SHALL have the same native loading interface as their parent without receiving tools or permissions absent from their own execution context. No per-agent skill selection SHALL be required.

#### Scenario: Automatic selection and iteration

- **WHEN** a user's ordinary request matches a skill's description
- **THEN** the model can load that skill, consult a reference, call an available task tool and produce a final response
- **AND** this sequence works for ReAct, DeepAgent and a Deep child

#### Scenario: Several procedures contribute to a request

- **WHEN** the agent selects two different skills for one request
- **THEN** both instruction sets can be loaded and used without replacing one another or ending the tool loop

### Requirement: Skill file access stays within the declared skill

Web selections and ReAct loading SHALL resolve a catalog name on the server. ReAct reference reads SHALL resolve a relative file path within that skill's published directory, support bounded UTF-8 text and reject traversal, absolute host paths, escaping symlinks, unsupported content and writes. Deep native access SHALL follow the separate physical-filesystem requirement: current files remain confined to the configured root, without replacing physical body bytes with snapshot content; per-skill eligibility SHALL still derive from validated metadata and current policy. Skill access SHALL NOT expose arbitrary host or conversation files, execute scripts, install tools or grant permissions. A frontmatter tool hint SHALL NOT be treated as a permission grant or an enforced restriction.

#### Scenario: Read an associated template

- **WHEN** a ReAct agent reads `references/meeting-minutes-template.md` from the valid `meeting-minutes` skill
- **THEN** it receives that snapshot's reference text without needing general filesystem access

#### Scenario: Escape or write attempt

- **WHEN** a ReAct request attempts to read outside the selected skill or modify its files
- **THEN** the operation is refused without returning unrelated file contents

### Requirement: Deep agents can read the published skills filesystem

Deep parents and native children SHALL mount the configured physical skill directory at `/skills/` with unmodified upstream `FilesystemBackend(root_dir=directory, virtual_mode=True)` in their existing composite backend. Fred SHALL configure skills through `create_deep_agent(skills=["/skills/"])` and the explicit child's `skills` field, without a replacement instruction loader, synthetic files or a duplicate native catalog prompt. Fred SHALL enforce per-turn eligibility using filtered native metadata and filesystem permissions while preserving the native loading implementation. Upstream SHALL own discovery, metadata caching, instruction/reference reads, listing, search and pagination. Matching physical folder/frontmatter names SHALL identify well-formed native skills. Agent and capability writes to `/skills` and its descendants SHALL be denied, and production resources SHALL be read-only on disk. Existing conversation workspace/artifact behavior SHALL remain intact. ReAct SHALL retain its current snapshot and confined tools; Deep SHALL register neither Fred skill tool. Web previews and ReAct preload SHALL retain their existing validated startup service and trusted attribution. Explicit Deep selections SHALL use native pinned_skills and load before the next model call. Fred SHALL NOT implement a replacement preload or validate physical bodies against its snapshot; the canonical user request SHALL remain unchanged.

#### Scenario: Native instruction and reference reads

- **GIVEN** the published `meeting-minutes` skill contains instructions and `references/meeting-minutes-template.md`
- **WHEN** a Deep parent or native child uses `read_file` on `/skills/meeting-minutes/SKILL.md` and then its canonical reference path
- **THEN** the returned contents match the current physical files, including bounded continuation reads
- **AND** the model can follow relative references and continue its normal tool loop

#### Scenario: Published files remain read-only and isolated

- **WHEN** a Deep agent lists `/skills/`, searches a reference, attempts to create/edit/delete a skill file or targets an escaping path
- **THEN** supported reads stay inside the configured filesystem root and agent/capability mutations and escaping access are refused
- **AND** ordinary scratchpad and artifact operations retain their existing permissions and contents

#### Scenario: Native constructor discovers live files without Fred adapters

- **GIVEN** an enabled packaged or configured physical directory and a well-formed skill
- **WHEN** parent and explicit child are compiled through create_deep_agent
- **THEN** both discover instructions using the same mounted filesystem through native skills configuration
- **AND** changing instruction or reference contents is visible to subsequent native reads without rebuilding a snapshot
- **AND** disabled skill configuration adds neither a skills route nor native skills configuration

#### Scenario: Native reads preserve load visibility

- **WHEN** a Deep parent or child successfully reads a skill's instructions beginning at offset zero
- **THEN** the existing skill-load activity and successful-load KPI record that skill with trusted execution scope and user origin when its name matches the current typed user selection, otherwise agent origin
- **AND** continuation pages, references, failures, UI previews and history replay add no load counts
- **AND** a later successful new offset-zero read counts as another actual load

#### Scenario: Requested and autonomous native loads are distinguished

- **GIVEN** the current user turn selects `meeting-minutes` through the typed slash invocation
- **WHEN** the Deep parent or child successfully reads that skill's SKILL.md at offset zero
- **THEN** its actual load event and KPI use user origin without adding a Fred preload or changing the native tool result
- **AND** other skills read in the same turn use agent origin
- **AND** same-exchange web HITL resumes retain the original typed selection and user-origin reads; new turns do not inherit it
- **AND** a later turn without a current selection uses agent origin, even if prior user text mentioned that slash
- **AND** reference reads, continuation windows, failures and selection alone do not count as skill loads

#### Scenario: Native references retain readable previews

- **WHEN** a successful native read returns a published skill reference
- **THEN** its trace entry can open the returned text in the existing exclusive reference panel
- **AND** paginated output is presented as the returned excerpt rather than a claim that the whole file was loaded

#### Scenario: Deep skill access uses only the filesystem

- **WHEN** a configured Deep parent or native child binds its model tools
- **THEN** `load_skill` and `read_skill_file` are absent from Fred's tool registrations and current loading guidance
- **AND** native filesystem reads retain reference previews and selection-aware KPI attribution
- **AND** explicit Deep selection reaches native pinned_skills without Fred preload or snapshot body validation; native successful pins use user origin, while independent native reads retain selection-aware origin and ReAct retains both confined tools

### Requirement: Web users can require a skill for their request

Managed web chat SHALL accept `/<name> [request]` at the invocation position and retain `/skill <name> [request]` compatibility and offer skill-name autocompletion from the selected agent's actual runtime catalog. Submission SHALL transmit typed name-only skill selections and the complete canonical user text including every invocation at its original position; for ReAct, the server SHALL validate and load the selected skill before the first model call from its snapshot rather than client instructions. Deep SHALL preserve canonical user text and pass eligible names through native pinned_skills before inference, without Fred preload or snapshot body validation; native filesystem reads SHALL load further references. A named invocation SHALL remain valid without arguments, even if the skill requires information to finish. Argument hints SHALL be optional descriptive text, never submission requirements. A bare `/skill` SHALL offer selection guidance without launching an empty agent turn. An unknown, invalid or unavailable explicit ReAct or Deep selection SHALL fail clearly before any model call, with no fallback to another skill or a prompt command.

#### Scenario: Explicit load precedes inference

- **WHEN** an authorized user submits `/meeting-minutes prepare the minutes from these notes` to ReAct
- **THEN** the runtime loads `meeting-minutes` before its first model call
- **AND** the model receives those instructions and the complete request

#### Scenario: Explicit Deep selection follows native loading

- **WHEN** an authorized user submits `/meeting-minutes prepare the minutes from these notes` to Deep
- **THEN** the first inference receives canonical user text, eligible upstream metadata and the instructions loaded by native pinned_skills, with one user-origin event per successful pin
- **AND** the model can read `/skills/meeting-minutes/SKILL.md` and its references with native `read_file`, with actual reads retaining user-origin events/KPI for the selected name and agent origin otherwise
- **AND** invoke, streaming, checkpoint follow-up and HITL resume use the same native behavior
- **AND** platform guidance identifies a matching slash command as the user's request to apply the procedure and directs instruction and required reference reads before drafting or using task tools, without a Fred preload or an extra model/tool call
- **AND** the current name-only selections appear as a user-request reminder in the existing per-turn system context, without paths, skill bodies or another catalog; fresh turns without selections remove it and same-exchange resumes retain it

#### Scenario: Discover skills directly from the slash menu

- **WHEN** an authorized web user types `/` in the composer
- **THEN** every skill from the selected runtime catalog is offered directly, alongside prompt commands
- **AND** a prefix such as `/comp` filters those skill names without requiring `/skill` first
- **AND** selecting a skill completes the canonical invocation without sending a turn or losing existing request text
- **AND** prompt and skill entries sharing a name remain independently selectable
- **AND** no standalone `/skill` dispatcher row is shown; named skills use a distinct pictogram and a tooltip containing their localized title and description, without a platform-origin label
- **AND** hovering the selected or sent skill name shows its localized title followed by a colon and its current description when available, without platform-origin or slash-command text
- **AND** skill suggestions display the English canonical name without a slash, in parentheses after a different localized title, while insertion and copying preserve canonical slash commands

#### Scenario: Named invocation without arguments

- **WHEN** a user submits `/meeting-minutes` without meeting notes in context
- **THEN** the turn starts; ReAct preloads instructions before inference, while Deep pins the selected instructions natively
- **AND** the agent is guided to ask for notes rather than invent meeting content
- **AND** a supplied `argument-hint` does not prevent submission

#### Scenario: Attach a skill to existing draft text

- **GIVEN** a request already contains text, including multiple lines
- **WHEN** the user types a skill command at the caret before, after or within that text and selects a skill
- **THEN** only the active command range is replaced and the existing request text is preserved
- **AND** the selected name stays at the invocation position using canonical `/<name>` text, with no turn dispatched by completion

#### Scenario: Direct typing and manual copy

- **WHEN** a current catalog name is typed or pasted as `/<name>` at a whitespace boundary and followed by whitespace
- **THEN** it becomes a selected skill at that position without dispatching a turn
- **AND** copying the displayed skill alone or the entire message preserves the canonical slash invocation
- **AND** complete delimited skill names take precedence for typing/paste; explicitly choosing a prompt homonym retains prompt behavior

#### Scenario: Inline wrapping and scrolling

- **GIVEN** a skill is selected in a multiline or overflowing request
- **WHEN** the text wraps, contains a newline or is scrolled
- **THEN** subsequent lines start at the normal left text inset and the inline skill scrolls with the line where it was inserted
- **AND** a sent skill label and request share the same text baseline

#### Scenario: Selected skill argument placeholder

- **GIVEN** the composer contains a selected skill with an empty request
- **WHEN** the request field is displayed
- **THEN** its placeholder shows the skill's argument hint when supplied, otherwise the generic optional-request prompt
- **AND** the hint is not inserted into the request and does not prevent empty submission

#### Scenario: Optional argument hints

- **GIVEN** one valid skill supplies `argument-hint` and another omits it
- **WHEN** either skill is selected in the composer
- **THEN** the supplied hint is shown as advisory text after the selected skill, not in the suggestion list, and both skills are usable
- **AND** non-string, blank or over-256-character hints are omitted with bounded diagnostics while retaining the valid skill

#### Scenario: Skill badge in the composer and user message

- **WHEN** a user completes a known `/<name>` selection or types a whitespace-delimited known name
- **THEN** the composer shows an icon/name token inline with the editable request, as a small filled container with the complete display title visible, its canonical name retained for execution/copy, and no separate row or removal button, allowing submission without extra text
- **AND** the token is edited as one block: it cannot be entered with the keyboard, and removing it removes the whole invocation while preserving surrounding text; deleting surrounding request text does not remove the skill
- **AND** persisted name-only selection metadata lets the sent user bubble display the same skill badge alongside its request, including after reopening history without the current catalog
- **AND** Deep selection metadata preserves the badge/preview independently of actual native pin/read events; selection alone and ordinary user mentions do not count as loads
- **AND** automatic agent/child loads and ordinary messages merely mentioning `/skill` do not label the user turn as explicitly selected
- **AND** copying a selected user turn includes the skill invocation and request

#### Scenario: Existing empty-request representation

- **GIVEN** a selected skill's stored question is exactly `/skill <name>`
- **WHEN** the user message is rendered or copied
- **THEN** the UI interprets the stored question as the existing no-request sentinel, shows the skill label alone, and copies canonical `/<name>` text
- **AND** a literal request identical to that sentinel remains indistinguishable under the existing name-only wire representation; all other request text is retained

#### Scenario: Stale menu or forged selection

- **WHEN** a submitted ReAct or Deep name is unavailable in the serving pod's validated snapshot
- **THEN** the runtime reports an explicit selection error and does not call the model

#### Scenario: Keyboard and agent switching

- **WHEN** the user types the skill prefix and navigates the suggestions
- **THEN** arrow keys, completion, submission and dismissal work through the existing composer interaction
- **AND** switching the selected agent invalidates suggestions from the previous runtime

### Requirement: Explicit skill selections compose within one turn

Managed web chat SHALL retain and render all explicit platform skill invocations in the same draft, including after another selection. Submission SHALL carry all distinct selected names in first-occurrence order, preserving canonical request text and every invocation occurrence. ReAct SHALL validate all selections and load their instructions before first inference through its existing loading boundary. Deep SHALL validate all selected names and load their instructions using native pinned_skills before inference, without Fred preload; actual reads matching any current selection SHALL retain user origin. Legacy single-selection requests and history SHALL remain supported. Duplicate invocation occurrences SHALL NOT cause duplicate explicit preloads or native pins.

#### Scenario: Select two platform skills

- **WHEN** a user completes `/meeting-minutes`, then `/verify-answer`, and submits the request
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

Web chat SHALL show a compact load step for actual loads containing the skill name and whether it was user-required or autonomously read by an agent. Deep selection alone SHALL NOT emit a load step or user-origin attribution; a successful native pin SHALL emit one user-origin load, without a fictional model tool call; its canonical invocation text and name-only selection metadata SHALL remain in history, independently of loading. Runtime history SHALL preserve this attribution without requiring the current skill file to exist. Each actual load SHALL be represented once, including Deep-child loads; human-requested preloading SHALL NOT be represented as a model-issued tool call that never happened. Full instruction inspection in the web UI SHALL NOT be required.

#### Scenario: Explicit and automatic loads are distinguishable

- **WHEN** a user-required load or a model-selected load succeeds
- **THEN** its compact step identifies the correct origin and skill name
- **AND** reopening the conversation retains the attribution without duplicating the step

#### Scenario: Skill loads share chronological step numbering

- **GIVEN** a successful skill load is followed by two tool calls in the trace
- **WHEN** the user expands the reasoning trace
- **THEN** the skill load has the same compact numbered marker as the tools, with step numbers 1, 2 and 3 in chronological order
- **AND** reasoning and ordinary notes remain unnumbered, while the header still reports two tool executions

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

The platform SHALL distribute English-written instructions and references for a focused quality/reliability catalog: `grounded-research`, `summarize-document`, `compare-options`, `verify-answer` and the existing `meeting-minutes` skill with a referenced minutes template under `fred_runtime/skills/meeting-minutes/`. The minutes instructions SHALL guide the agent to read supplied notes, identify decisions and actions, and report owners or dates as missing when absent. It SHALL work through explicit web invocation and automatic model selection with available document-reading tools.

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

- **WHEN** a research, summary, comparison or verification skill has insufficient evidence to complete its requested output
- **THEN** its instructions guide the agent to use available context and tools, distinguish evidence from inference, and report the missing information
- **AND** they do not claim to have read unavailable sources or verified unsupported facts

### Requirement: Read-only skill instruction preview

Managed web chat SHALL make an explicitly selected inline skill name clickable in the composer and in sent or reopened user messages, and each successful skill-load row activatable in the reasoning trace regardless of user, agent or child origin. Activating it SHALL open the existing right-hand chat panel with the complete name, description, optional argument hint and formatted instructions from that skill's current runtime snapshot. Catalog responses SHALL remain metadata-only. A separate authenticated, typed detail read SHALL use the selected managed instance's runtime source and the existing team-use authorization. It SHALL expose only the selected startup-snapshot `SKILL.md`, never an arbitrary client path. Preview SHALL NOT send a user turn, invoke a model, load instructions into agent context or modify the draft. Preview SHALL use a large neutral `Skill: <name>` title, `Description:` and its text above optional `Arguments:` followed by the argument hint, and a divider before the instructions. It SHALL omit redundant content headings and technical runtime-version labels. Activating the currently previewed skill again SHALL close the panel; activating another skill SHALL replace its contents. Historical preview SHALL read the current runtime snapshot without claiming to reconstruct the previously loaded body.

#### Scenario: Preview from the composer

- **GIVEN** the composer contains a selected skill and an editable request
- **WHEN** the user activates the skill name by pointer or keyboard
- **THEN** its instructions open in the right-hand panel with readable Markdown and metadata
- **AND** the skill and request remain unchanged, no turn or model call occurs, and the inline name remains complete without a removal cross

#### Scenario: Preview from a stored user message

- **GIVEN** a reopened user message has explicit user-origin skill attribution
- **WHEN** the user activates its skill name
- **THEN** the panel reads the current snapshot of that message's managed agent runtime
- **AND** it does not expose technical runtime-version labels or claim to reconstruct historical instructions

#### Scenario: Preview from a skill-load trace row

- **GIVEN** a successful skill-load step requested by the user or chosen by an agent or child
- **WHEN** the user activates its row by pointer, Enter or Space
- **THEN** the current skill instructions open in the existing right-hand panel, replacing any other push panel
- **AND** the localized description precedes the labeled arguments, when supplied, followed by the authored instructions, without dispatching a turn or editing the draft

#### Scenario: Toggle the same skill preview

- **GIVEN** a skill preview is open from a composer, stored user message or skill-load trace row
- **WHEN** the user activates that same skill again
- **THEN** the panel closes without changing the draft or dispatching a turn
- **AND** activating another skill opens its preview instead

#### Scenario: Authorized and source-confined detail reads

- **WHEN** an authorized user requests a known skill for an enabled managed instance in their team
- **THEN** the detail endpoint returns its typed metadata, snapshot revision and bounded content from that instance's selected runtime source
- **AND** a caller lacking team-use permission receives no content, an unknown or invalid name is rejected, and no alternate source or arbitrary file is read

#### Scenario: Missing or outdated runtime

- **WHEN** the selected runtime does not support detail reads or the skill is no longer available
- **THEN** the panel shows a clear unavailable state without displaying cached content from another selection or changing the draft

#### Scenario: Preview replacement and closure

- **WHEN** another skill, team or managed instance is selected while a detail read is pending
- **THEN** an earlier response cannot replace the current preview
- **AND** only one chat side panel is open and closing it leaves the current conversation and draft intact

### Requirement: Reference-read trace steps preview their returned file

Managed web chat SHALL localize the platform skill reference-reading tool label in English and French. Activating a successful reference-read trace step SHALL open the exact text returned by that call in the existing exclusive right-hand chat panel, with the relative file path and skill name clearly identifiable. Preview SHALL use stored authorized conversation results, including in reopened history, without a new file read, tool/model invocation or draft mutation. Switching between a skill and a reference, or between references, SHALL replace the panel contents; activating the currently previewed reference again SHALL close it. Markdown SHALL be sanitized and local links SHALL NOT grant arbitrary file access. Pending, failed or unavailable results SHALL retain clear existing trace detail/error behavior rather than display an unrelated file.

#### Scenario: Open the reference actually loaded

- **GIVEN** a successful read of a skill reference whose returned text is in conversation history
- **WHEN** the user activates its trace row by pointer or keyboard
- **THEN** the right-hand panel displays that result's text and file/skill identity
- **AND** changes to the current runtime file do not change this historical preview, no tool/model call occurs and the draft remains unchanged

#### Scenario: Replace a skill preview with a reference

- **GIVEN** a skill's instruction preview is open
- **WHEN** the user activates a completed reference-read step
- **THEN** the same panel displays the reference instead of the skill instructions
- **AND** activating the skill name restores its preview, while a second activation of the same reference closes the panel

#### Scenario: A reference read has not succeeded

- **WHEN** a reference-read trace step is pending, failed or lacks its stored result
- **THEN** inspecting it exposes its existing progress/error/unavailable details and no unrelated reference content

### Requirement: Successful skill loads have origin-aware usage KPIs

The platform SHALL emit one skill-usage counter per actual successful skill load, with the validated skill name, trusted user-or-model origin and existing bound team/session/exchange/managed-instance attribution when available. User-required loads, including native Deep pins and matching selected native reads, SHALL have user origin; autonomous agent and Deep-child loads SHALL have model origin. Failed loads, preview reads, reference-file reads, history/status replay and resumes without a new load SHALL NOT increment this counter. An actual subsequent successful reload SHALL count again; continuing to use instructions already retained in context SHALL NOT imply a newly observed invocation. KPI events SHALL NOT contain skill bodies, reference text or user requests. Collection SHALL use the existing fail-open KPI mechanism and SHALL NOT add direct blocking storage calls to loading.

#### Scenario: User, model and child choices remain distinguishable

- **WHEN** a user-selected skill, a model-selected skill and a Deep-child-selected skill each load successfully
- **THEN** the counter records one user-origin load and two model-origin loads with their serving context
- **AND** forwarding the child event to the parent or reopening the trace does not add another count

#### Scenario: Loading fails or only preview occurs

- **WHEN** a skill load fails, a file/skill preview opens, a reference is read or a request resumes without another load
- **THEN** none of those operations adds a successful skill-load count
- **AND** a later actual successful reload adds one count

#### Scenario: KPI collection is unavailable

- **WHEN** the existing KPI sink is unavailable during a successful skill load
- **THEN** loading retains the existing fail-open behavior and the model receives the successfully read instructions

### Requirement: Team, platform and personal dashboards compare skill usage by origin

Authorized team, platform and personal dashboards SHALL show the same dedicated skill-usage subsection and a table with one row per returned skill and columns for user-origin loads, model-origin loads and their total over the selected time range. Count columns SHALL be sortable, missing origins SHALL display zero, and loading/empty/error states SHALL follow existing dashboard conventions. The shared typed KPI preset SHALL apply the requested date interval and team filter on the server, using existing team-read and platform-observation authorization. A team-scoped query SHALL NOT return another team's counts. Platform scope SHALL aggregate all recorded serving teams. Historical skill names SHALL remain reportable independently of the current catalog. Results SHALL return at most the top 100 skills by total, with a deterministic tie order and a visible truncation indication when needed. The UI SHALL identify these as successful loads, with data collected from instrumentation deployment onwards; no historical backfill SHALL be implied.

#### Scenario: Skill usage within one team and one time range

- **GIVEN** two teams load the same skill inside and outside the requested interval
- **WHEN** an authorized team viewer selects that interval
- **THEN** the table counts only loads for that team within the interval, split by user and model
- **AND** a missing origin is zero and changing the period or refreshing uses the existing dashboard query lifecycle

#### Scenario: Platform aggregate and authorization

- **WHEN** an authorized platform observer selects an interval
- **THEN** the table aggregates recorded loads across teams and allows sorting by either origin or total
- **AND** unauthorized team/platform callers receive no aggregate data, following existing KPI authorization

#### Scenario: Removed skills and large historical catalogs

- **GIVEN** recorded loads include a skill removed from the current catalog and more than 100 distinct skill names
- **WHEN** the dashboard queries the matching interval
- **THEN** historical names participate in the top-total ranking without requiring current catalog availability
- **AND** the response and UI identify that the table is truncated rather than claiming complete coverage

#### Scenario: Personal usage is isolated from other users

- **GIVEN** two users load the same skill across several teams
- **WHEN** an authenticated user requests their personal skill usage over a date range
- **THEN** counts include only loads bound to that user within that range, across their teams
- **AND** the model-origin column includes model loads in that user's own conversations
- **AND** no supplied user identifier can select another user's data
- **AND** team parameters are rejected, matching existing personal KPI presets

#### Scenario: The same subsection at each dashboard scope

- **WHEN** a viewer opens platform, authorized team or personal usage
- **THEN** a dedicated skill-usage subsection displays the same sortable origin table
- **AND** personal space shows only that user's skill usage without requiring elevated team permissions
- **AND** team space shows only the selected team's skill usage under existing aggregate permissions, without a personal skill subsection or personal skill query
- **AND** platform analytics shows only the platform skill aggregate
- **AND** changing period or team cannot display a previous query's skill counts

### Requirement: Slash commands combine platform skills and two prompt libraries

For managed chat, whatever the agent's execution family, the slash menu SHALL offer prompts carrying commands from the current chat team and from the caller's personal library, alongside the platform skills the selected runtime provides. The menu SHALL identify each entry's source by the section it is listed under and preserve independently selectable homonyms. A personal chat SHALL offer its personal prompt library once. Prompts without commands SHALL remain available through the existing library panel. This requirement SHALL NOT change which agents are offered platform skills. Available prompt commands SHALL complete, render and resolve inline before or after selected skills in all managed chats, with the same prompt container treatment in the draft and sent history.

#### Scenario: Team chat offers three sources

- **GIVEN** a team agent of any execution family, a personal prompt command and a team prompt command
- **WHEN** the authorized user types `/`
- **THEN** the menu offers both prompt commands alongside the runtime's platform skills, each under the section of its source
- **AND** personal data is queried under the caller's own personal scope and team prompts under the chat team

#### Scenario: Duplicate prompt commands retain their source

- **GIVEN** personal and team libraries both contain `/summary`
- **WHEN** the user selects either prompt row and submits after completion
- **THEN** the exact selected prompt is fetched from its owning library and its text reaches the agent with the existing command attribution
- **AND** a typed prompt command without an explicit selection resolves the chat team's match first, then the personal match

#### Scenario: Skills and prompt commands remain separate

- **GIVEN** a platform skill and a prompt share a name
- **WHEN** the user explicitly selects the prompt row
- **THEN** prompt text is submitted through the existing prompt-command path without a typed skill selection
- **AND** selecting the skill row completes its canonical invocation without sending and subsequent submission uses the unchanged ReAct skill-loading path
- **AND** typing/paste retains existing delimited-skill precedence

#### Scenario: Personal scope is not duplicated or carried between chats

- **WHEN** a personal chat opens or the active team or agent changes
- **THEN** each eligible prompt source appears once and prior selections and cached responses do not dispatch another scope's prompt
- **AND** failed reads or unavailable personal identity do not fall back to a different selected prompt; an invalidated completed choice requires command editing or reselection

#### Scenario: Pending team discovery cannot change typed precedence

- **GIVEN** the personal command catalog is available while the chat team's catalog is unresolved
- **WHEN** the user submits a typed prompt command without explicitly selecting a row
- **THEN** personal fallback is refused until the team's absence of that command is established
- **AND** an explicit personal row selection remains independently usable while team discovery is pending

#### Scenario: Personal commands do not depend on the agent kind

- **WHEN** the selected template is ReAct, Deep, Graph, Proxy or not yet resolved
- **THEN** the caller's personal prompt commands are offered in a team chat
- **AND** the existing skill availability and skill dispatch behavior are preserved

### Requirement: The slash menu lists its entries in titled sections by source

The slash menu SHALL group its entries in up to three sections, always in this order: the chat team's prompt commands, the caller's personal prompt commands, then platform skills. Each section SHALL have a visible heading that names it for assistive technology: the team section's heading SHALL include the team's name, shown on one line and truncated with an ellipsis when too long; the personal section's heading SHALL name the personal space; the skills section's heading SHALL name platform skills. Headings SHALL NOT be uppercased. A section with no entry to show, including after filtering on the typed text, SHALL be hidden together with its heading. Rows SHALL NOT carry a source label of their own. Keyboard navigation SHALL treat all displayed entries as one continuous list in display order and SHALL stop at the first and at the last entry without wrapping.

#### Scenario: Three sections in a team chat

- **GIVEN** a team chat whose team is named "Finance", with a team prompt command, a personal prompt command and a platform skill
- **WHEN** the user types `/`
- **THEN** the menu shows a section titled with the team name "Finance", then a personal-space section, then a platform-skills section, each holding its own entries
- **AND** no row shows a source label

#### Scenario: Empty and unmatched sections are hidden

- **GIVEN** a team chat where only the personal library holds a command whose name contains `re`
- **WHEN** the user types `/re`
- **THEN** only the personal-space section and its heading are shown

#### Scenario: Personal chat shows one commands section

- **WHEN** the user types `/` in a personal-space chat
- **THEN** the prompt commands appear once, under the personal-space section, with no team section

#### Scenario: A shared command name appears in both sections

- **GIVEN** the team and the personal library both contain `/summary`
- **WHEN** the user types `/sum`
- **THEN** `/summary` is listed once in the team section and once in the personal-space section, and each row selects its own prompt

#### Scenario: Arrow keys cross section boundaries

- **GIVEN** the menu shows a team section followed by a personal-space section
- **WHEN** the focus is on the last team entry and the user presses ArrowDown
- **THEN** the focus moves to the first personal-space entry
- **AND** ArrowUp from the first displayed entry and ArrowDown from the last one leave the focus where it is

#### Scenario: Long team name

- **GIVEN** a team whose name is wider than the menu
- **WHEN** the menu opens
- **THEN** the team heading stays on one line and ends with an ellipsis

#### Scenario: Rows stay compact

- **GIVEN** the menu lists a prompt command and a platform skill that has an argument hint and a long description
- **WHEN** the menu is shown
- **THEN** each row shows its name above its description, the description on one line and cut with an ellipsis when too long
- **AND** hovering a row gives its full description
- **AND** the skill's argument hint is not shown in the menu

### Requirement: Picking a menu row inserts the command and never sends

In the slash menu, Enter, Tab and a pointer activation on a row SHALL all do the same thing, for a prompt command and for a platform skill alike: insert the row's command in the composer at the command being typed, keep the surrounding text, close the menu and send nothing. A turn SHALL only be sent by the ordinary submit, with the menu closed: Enter again, or the send button. That submit SHALL resolve a picked prompt command to the exact prompt of the picked row (its id and its owning library) and send the same expanded text and the same command attribution whichever way the row was picked. Shift+Enter SHALL keep its ordinary composer behaviour while the menu is open. Because Enter on a row sends nothing, the menu SHALL receive it whether or not sending is possible at that moment (an attachment still uploading, a draft over the length limit): the row is inserted and no line break is added. Picking a row SHALL replace the whole name under the caret, whatever its case, including the part of the name that follows the caret.

#### Scenario: Enter inserts while sending is blocked

- **GIVEN** an attachment is still uploading, or the draft is over the length limit, and the menu is open on `/su` with `/summary` focused
- **WHEN** the user presses Enter
- **THEN** the composer reads `/summary ` with the command shown as a token, no line break is added and no turn is sent

#### Scenario: The whole name under the caret is replaced

- **GIVEN** the draft `hello /MAR` with the caret between `A` and `R`, and the menu listing `/summary`
- **WHEN** the user picks `/summary`
- **THEN** the draft reads `hello /summary ` with nothing left of the typed name

#### Scenario: Enter on a prompt row inserts it

- **GIVEN** the menu is open on `/su` with the prompt command `/summary` focused
- **WHEN** the user presses Enter
- **THEN** the composer reads `/summary ` with the command shown as a token, the menu is closed and no turn is sent

#### Scenario: A second Enter sends

- **GIVEN** a prompt command was inserted from the menu with Enter
- **WHEN** the user presses Enter again
- **THEN** the turn is sent with the prompt's text in place of the command and the command attribution of the picked prompt

#### Scenario: Enter and Tab reach the same send

- **GIVEN** the same draft and the same focused prompt row
- **WHEN** the row is picked once with Enter and once with Tab, each followed by Enter
- **THEN** both turns carry the same text and the same command attribution

### Requirement: The slash menu searches inside command names

The slash menu SHALL match the typed text against the command name only, never against a prompt's name or description. The match SHALL ignore case and SHALL accept the typed text anywhere inside the name. Inside each section, entries whose name starts with the typed text SHALL be listed before the others, and each of the two groups SHALL keep the order the catalog returned. Sections SHALL keep their order and their entries SHALL stay grouped, so keyboard navigation follows the displayed order. When the menu opens or the typed text changes, the focus SHALL be on the first row displayed, whichever section holds an entry starting with the typed text. A command typed in full by hand SHALL still be recognised only in its exact, lowercase spelling.

#### Scenario: Match inside a name, whatever the case

- **GIVEN** the commands `/search` and `/summary`
- **WHEN** the user types `/MAR`
- **THEN** the menu lists `/summary` only

#### Scenario: The description is not searched

- **GIVEN** a command `/search` whose description is "Chercher"
- **WHEN** the user types `/cher`
- **THEN** the menu says that no command matches

#### Scenario: Names starting with the text come first in each section

- **GIVEN** the team commands `/pre-sum` and `/big-sum`, and the personal commands `/my-sum`, `/sum-up` and `/sum`, in that catalog order
- **WHEN** the user types `/sum`
- **THEN** the team section lists `/pre-sum` then `/big-sum`, and the personal section lists `/sum-up`, `/sum`, then `/my-sum`
- **AND** the focus is on `/pre-sum`, the first row displayed

### Requirement: The empty slash menu says why it is empty

When the slash menu has no row to show, it SHALL stay visible and show one status line. While a command catalog it reads has not answered yet, the line SHALL say that the commands are loading and SHALL NOT say that there is no command or no match. When every catalog has answered and none holds a command or a skill, the line SHALL say that there is no command yet and what the user can do, in words that hold in a team chat and in the personal space: add a command to one of their personal prompts, and, in a team, an editor can add one to a team prompt. When commands exist but none matches the typed text, the line SHALL say that no command matches. Rows from a catalog that has already answered SHALL be shown while another one is loading. When a catalog could not be read and has never answered, and no catalog is loading, the line SHALL say that the commands could not be loaded and how to retry, and SHALL NOT say that there is no command or no match; the failed catalog SHALL be asked again each time the user starts a new command, not on each character of its name.

#### Scenario: Catalogs still loading

- **GIVEN** the team's command catalog has not answered yet and nothing else is available
- **WHEN** the user types `/`
- **THEN** the menu shows a loading line and does not claim that there is no command

#### Scenario: Nothing exists

- **GIVEN** every catalog has answered and there is no team command, no personal command and no skill
- **WHEN** the user types `/`
- **THEN** the menu says there is no command yet and how to add one, with the same text in a team chat and in the personal space

#### Scenario: Nothing matches

- **GIVEN** commands exist
- **WHEN** the user types `/zzz`
- **THEN** the menu says that no command matches

#### Scenario: A catalog could not be read

- **GIVEN** reading the team's command catalog failed and nothing else is available
- **WHEN** the user types `/`
- **THEN** the menu says that the commands could not be loaded and to type `/` again to retry, and the catalog is asked again once
- **AND** typing further characters of the name does not ask it again

### Requirement: Sending waits for the command catalogs

Submitting a message SHALL never race the command catalogs (the team's prompt commands, the personal prompt commands and the agent's platform skills). A `/name`-shaped word is a slash followed by a name, delimited on both sides by whitespace or a text boundary. When the draft holds at least one such word that the user did not pick from the menu, and a catalog has not answered yet, the submit SHALL wait for every such catalog before resolving the message, then resolve it as usual; it SHALL NOT send the draft as typed in the meantime and SHALL NOT show an error for the wait. A catalog whose read had failed SHALL be asked once more at that moment. Only when a catalog still has no answer after that SHALL the message be held back, with the "try again in a moment" message naming the first typed command. A word that matches no command once the catalogs have answered SHALL be sent as plain text, with no message to the user. A draft with no such word, or whose commands were all picked from the menu, SHALL NOT wait. A second submit while one is waiting SHALL send nothing more, and a wait that ends after the chat's team, agent or personal space changed SHALL send nothing.

#### Scenario: A typed personal command while the personal catalog loads

- **GIVEN** a team chat where `/summary` is a team command and `/tone` a personal one, and the personal catalog has not answered yet
- **WHEN** the user submits `/summary and /tone now`
- **THEN** nothing is sent until the personal catalog answers
- **AND** the turn then expands both prompts, and the model never receives the literal `/tone`

#### Scenario: Right after the page loads

- **GIVEN** neither prompt catalog has answered yet
- **WHEN** the user submits `/summary report`
- **THEN** nothing is sent until both have answered, and the turn then carries the `summary` prompt
- **AND** pressing Enter a second time while waiting does not send a second turn

#### Scenario: A typed skill while the skill catalog loads

- **GIVEN** the agent's skill catalog has not answered yet
- **WHEN** the user submits `/review notes`
- **THEN** nothing is sent until it answers, and the turn then requires the `review` skill

#### Scenario: Ordinary text that starts with a slash

- **GIVEN** a catalog that has not answered yet, and no command named `nosuch`
- **WHEN** the user submits `see /etc and /nosuch please`
- **THEN** once the catalog has answered the message is sent as typed, and no error is shown

#### Scenario: No command-shaped word

- **GIVEN** catalogs that have not answered yet
- **WHEN** the user submits `see /etc/hosts and a/b`
- **THEN** the message is sent at once

#### Scenario: A failed catalog answers when asked again

- **GIVEN** reading the team's command catalog failed
- **WHEN** the user submits `/summary report`
- **THEN** the catalog is asked once more, it answers, and the turn carries the `summary` prompt

#### Scenario: A failed catalog fails again

- **GIVEN** reading the team's command catalog failed and fails again when asked
- **WHEN** the user submits `hello /summary report`
- **THEN** nothing is sent, the draft is kept and the message says that `/summary` could not be read and to try again in a moment

### Requirement: A command that cannot run says why

When a prompt command cannot be run on submit, the user SHALL be told which of two cases applies, and nothing SHALL be sent. When the picked prompt is no longer in its catalog (deleted, or its command renamed), when reading it is refused or it is not found, or when the token was picked for another agent, team or personal space, the message SHALL say that the command is no longer available and tell the user to remove it from the message and choose it again. When the read fails for another reason, or a catalog needed to resolve a typed command still has no answer after the submit waited for it and asked it again, the message SHALL tell the user to try again in a moment.

#### Scenario: The prompt was deleted or renamed

- **GIVEN** a prompt command picked from the menu whose prompt has since left its catalog
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to remove the command and choose it again

#### Scenario: The token belongs to another agent or team

- **GIVEN** a prompt command picked before the chat's team, agent or personal space changed
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to remove the command and choose it again

#### Scenario: A read that failed

- **GIVEN** a prompt command whose prompt exists but whose read fails with a network or server error
- **WHEN** the user submits
- **THEN** nothing is sent and the message asks to try again in a moment

### Requirement: A prompt token in the composer opens a preview of its prompt

A completed prompt command token in the composer SHALL be a control that opens a preview in the chat side panel, like a platform skill token: reachable and activated in the same way, with the same hover, press and keyboard-focus indication, and still behaving as one block of text. The panel SHALL show, from top to bottom, the prompt's name, its `/command`, then the prompt's current text, read when the panel opens from the library that owns the picked prompt; it SHALL NOT show a description. While the text is being read the panel SHALL say so, and when it cannot be read (not found, or access refused) it SHALL say so in a short message instead of showing another prompt's text. Activating the same token again SHALL close the panel. Opening or closing the preview SHALL NOT change the draft and SHALL NOT send anything. The token's hover hint SHALL name its source with the wording of the menu's section headings: the personal space, or the team with its name.

#### Scenario: Preview before sending

- **GIVEN** a draft holding the token of the team prompt "Résumé" with the command `/summary`
- **WHEN** the user activates the token
- **THEN** the side panel shows "Résumé", then `/summary`, then the prompt's current text
- **AND** the draft is unchanged and nothing is sent

#### Scenario: The prompt cannot be read

- **GIVEN** a token whose prompt was deleted, or that the user may no longer read
- **WHEN** the user activates the token
- **THEN** the panel shows the name and the command with a short message saying the prompt cannot be shown

#### Scenario: Hover hint uses the section wording

- **WHEN** the user hovers a personal prompt token and a team prompt token in a team named "Finance"
- **THEN** the hints read the personal-space heading and the "Finance" team heading, as in the menu

### Requirement: Invoked prompts and skills are shown as small containers

A completed prompt command or platform skill SHALL be shown as a small filled container holding its icon and its name, in the composer and in sent or reopened user messages. Prompt command names SHALL retain their leading `/` in command menu rows, composer tokens and sent-message badges. Platform skills, including legacy `/skill <name>` invocations, SHALL display their localized title without a leading slash, falling back to the canonical name. Presentation SHALL NOT change stored or copied canonical invocations or how a command is recognised. Every container SHALL use the same colour pair, the secondary container one, for a platform skill and for a prompt whether it comes from the team or from the personal space; icon and name SHALL take the container's content colour, with distinct prompt and skill icons. The container SHALL have a small corner radius and light horizontal padding and SHALL NOT change the height of the line it sits on. In the user's sent message, whose bubble has the same colour as the container, the container SHALL carry a thin outline that keeps it distinguishable without changing its size. Clickable containers SHALL keep their hover and keyboard-focus indication.

#### Scenario: Tokens in the composer

- **GIVEN** a draft holding a completed prompt command and a completed platform skill among ordinary text
- **WHEN** the composer shows the draft
- **THEN** the prompt and the skill each appear in a container of the same colour with their own icon, the prompt command preceded by `/` and the skill title without a slash
- **AND** the line is exactly as tall as a line of plain text

#### Scenario: Badges in a sent message

- **GIVEN** a sent message that invoked a prompt command and a platform skill
- **WHEN** the conversation shows the message
- **THEN** both appear as containers with the same colours as in the composer
- **AND** each container is visibly outlined against the message bubble, whose height per line is unchanged

#### Scenario: Prompt slashes and skill titles remain distinct

- **GIVEN** a prompt command `summary` and a platform skill `review`
- **WHEN** they are listed in the command menu, completed in the composer and shown in a sent message
- **THEN** the prompt reads `/summary` and the skill shows its localized title, or `review` when no localized title exists, in all three places
- **AND** copying a sent message that invoked the skill gives `/review` once, not `//review`

#### Scenario: Team and personal prompts look the same

- **WHEN** a team prompt and a personal prompt are each completed in the composer
- **THEN** both use the same container, with the prompt icon

### Requirement: The composer caret stays visible in the empty field

When the chat composer is empty and focused, the text caret SHALL be fully visible, at its usual height, in front of the placeholder. The placeholder SHALL NOT be part of the editable text, SHALL remain announced to assistive technology as the field's placeholder, SHALL NOT move and SHALL leave the field at the height of one line.

#### Scenario: Caret over the placeholder

- **GIVEN** an empty composer showing its placeholder
- **WHEN** the user focuses the field
- **THEN** the whole caret is visible at the start of the line, drawn over the placeholder
- **AND** the placeholder text and the field height are the same as before focusing

### Requirement: Composer tokens behave as one block

In the chat composer, a completed prompt command or platform skill token SHALL behave as a single unit of text. The Left and Right arrow keys SHALL move the caret across a token in one press, and extending a selection SHALL take a token as a whole. Backspace with the caret right after a token, and Delete with the caret right before it, SHALL remove the whole invocation, leaving no stray slash and no doubled or leading space, and SHALL NOT reopen the command menu. Undo SHALL restore the removed token with its selection identity. Tokens next to each other SHALL each behave independently. The command menu SHALL stay closed while the caret sits right after a rendered token, prompt or skill alike, picked or typed by hand, including a token at the very end of the draft; it SHALL open as usual for a new `/` typed elsewhere or for a name still being typed with no token yet. Away from a token, the same keys SHALL keep their ordinary one-character behaviour.

One rule SHALL decide what a token is, in the composer, on submit, when a stored message is rendered and on recall: a `/name` is a token only while whitespace or a text boundary delimits it on both sides. A character typed right before or right after a token SHALL dissolve it into plain text, which then follows the rules of a name typed by hand; removing that character SHALL NOT bring back the prompt or skill the token had been picked as. When an edit removes one token, every other token SHALL keep the prompt or skill it was picked as, including when the removed token and the one next to it read the same: the composer SHALL move tokens by the edit the editor made, not by comparing the text before and after.

#### Scenario: Arrow keys jump over a token

- **GIVEN** a draft `Before /meeting-minutes after` whose skill is shown as a token
- **WHEN** the caret is right after the token and the user presses the Left arrow once
- **THEN** the caret is right before the token
- **AND** pressing the Right arrow once puts it back right after the token

#### Scenario: Backspace removes the whole token

- **GIVEN** a draft `Before /meeting-minutes after` with the caret right after the token
- **WHEN** the user presses Backspace
- **THEN** the draft reads `Before after`, the skill is no longer selected and the command menu stays closed
- **AND** undo restores `Before /meeting-minutes after` with its token

#### Scenario: Delete removes the whole token

- **GIVEN** a draft `Before /meeting-minutes after` with the caret right before the token
- **WHEN** the user presses Delete
- **THEN** the draft reads `Before after`

#### Scenario: A token typed by hand behaves like a picked one

- **GIVEN** the user typed `/summary` and a space by hand, without picking a row, and the prompt is shown as a token
- **WHEN** the user presses Backspace once
- **THEN** only the space is removed and the token is still shown
- **AND** a second Backspace removes the whole token

#### Scenario: The menu stays closed on a token at the end of the draft

- **GIVEN** a prompt token, picked in the menu or typed by hand, followed by a single space
- **WHEN** the user removes that space with Backspace
- **THEN** the token is still shown and the command menu is closed
- **AND** typing a space or text after it keeps the menu closed
- **AND** typing a new `/re` further on opens the menu for that new command only

#### Scenario: Two tokens side by side

- **GIVEN** a draft `/review /meeting-minutes notes` showing two tokens
- **WHEN** the user removes the second token with Delete
- **THEN** the draft reads `/review notes` and the first token is still selected

#### Scenario: Removing the first of two tokens with the same name

- **GIVEN** a draft `/summary /summary x` whose first token was picked from the team and the second from the personal space
- **WHEN** the user removes the first token with Backspace
- **THEN** the draft reads `/summary x` and its token is the personal prompt, for the hint, the preview and the submit
- **AND** the same holds for `a /summary /summary x`, and undo restores both tokens with their own prompt

#### Scenario: A picked prompt before a skill of the same name

- **GIVEN** a draft `/review /review x` whose first token was picked as a prompt and the second as a platform skill
- **WHEN** the user removes the first token with Backspace
- **THEN** the draft reads `/review x` and its token is the skill

#### Scenario: Letters typed right after a token

- **GIVEN** the prompt token `/sum` at the end of the draft, picked from the menu, and another command `/summary`
- **WHEN** the user types `mary x` right after it
- **THEN** the draft reads `/summary x`, the `sum` prompt is no longer selected and the line is read as the `summary` command typed by hand
- **AND** submitting it sends the `summary` prompt, and the sent message shows its badge and is recalled as `/summary`

#### Scenario: A character typed right before a token

- **GIVEN** a prompt or skill token at the start of the draft
- **WHEN** the user types `x` right before it
- **THEN** the token is plain text again and submitting sends the draft as typed

#### Scenario: Removing the glued character

- **GIVEN** a picked token that a glued character turned back into text
- **WHEN** the user removes that character
- **THEN** the name is a name being typed like any other, with no token until it is delimited, and it is not bound to the prompt or skill picked earlier

### Requirement: The composer accepts several prompt commands in one message

In managed chat, the slash menu SHALL keep offering prompt commands, from the chat team and from the personal space, when the message already holds one or more prompt commands, at any position where a command can be typed. Each completed prompt command SHALL be its own token: one block for the caret, selection and deletion, with its own source hint and its own preview of the prompt it was picked from. Editing or removing one token SHALL leave the other prompt and skill tokens recognised. A message SHALL hold at most 16 prompt commands; a message holding more SHALL NOT be sent and the user SHALL be told the limit. This requirement supersedes any earlier statement that a message carries a single prompt command.

#### Scenario: The menu still offers prompts after a first one

- **GIVEN** the composer holds the prompt token `/summary` followed by a space
- **WHEN** the user types `/`
- **THEN** the menu lists the team's and the personal prompt commands under their sections, alongside the platform skills

#### Scenario: Two prompt tokens with their own preview

- **GIVEN** the user picked `/summary` from the team section and `/tone` from the personal section
- **WHEN** the user activates the `/tone` token
- **THEN** the side panel shows the name, the command and the current text of the personal `tone` prompt
- **AND** activating the `/summary` token then shows the team `summary` prompt instead

#### Scenario: Removing one token keeps the other

- **GIVEN** a message holding the tokens `/summary` and `/tone`
- **WHEN** the user deletes the `/summary` token with one Backspace
- **THEN** `/tone` is still a token, picked from the same library as before

#### Scenario: Removing one of two tokens with the same name

- **GIVEN** a message holding `/summary` picked from the team, then `/summary` picked from the personal space
- **WHEN** the user deletes the first token with one Backspace
- **THEN** the remaining token is still the personal prompt

#### Scenario: Too many prompt commands

- **GIVEN** a message holding 17 prompt commands
- **WHEN** the user submits it
- **THEN** nothing is sent, the draft is kept and a message says a message can hold at most 16 commands

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

- **GIVEN** two prompt commands and the platform skill `/verify-answer` in one message
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

### Requirement: The command descriptor lists every prompt command of the turn

A turn sent with one or more prompt commands SHALL carry, in its command descriptor, an optional list named `prompts` with one entry per prompt command occurrence, in the order of the typed line. Each entry SHALL give the command, the prompt's id and name, the position of the command in the typed line, and the position and length of that prompt's text in the text that was sent. Positions SHALL be counted as the web client counts string positions (UTF-16 code units), like the existing draft offset; the runtime SHALL NOT interpret them. The descriptor's existing single fields SHALL stay and SHALL describe the first prompt command of the line, with the user's own text as its appended text. The list SHALL be additive and optional on the execution request and on the stored turn: a request without it SHALL be accepted, and a turn stored without it SHALL be served unchanged. The runtime SHALL accept at most 16 entries and SHALL reject a request whose list is longer or malformed, as it does for any invalid request field. The list SHALL be stored and served back with the turn as it was sent. It SHALL remain side data: client-supplied, used for display only, never a source of text for the model and never resolved against the prompt library at display time.

#### Scenario: Two prompts are listed with their positions

- **WHEN** the user sends `First /summary then /tone please` with both prompts resolved
- **THEN** the stored turn's descriptor lists `summary` then `tone`, each with its prompt id and name, its position in the typed line and the position and length of its text in the stored text
- **AND** the single fields name `summary`, its prompt id and its position

#### Scenario: A single prompt is listed too

- **WHEN** the user sends `/summary the report`
- **THEN** the descriptor lists one entry for `summary` and its single fields are what they are today

#### Scenario: A request without the list is accepted

- **GIVEN** a client that sends the descriptor with its single fields only
- **WHEN** the turn is executed and stored
- **THEN** the request is accepted and the stored descriptor has no list

#### Scenario: An oversized list is rejected

- **WHEN** a request carries a descriptor listing 17 prompts
- **THEN** the runtime rejects the request as invalid and runs no turn

#### Scenario: The list survives a reload

- **GIVEN** a stored turn whose descriptor lists two prompts
- **WHEN** the conversation history is read again
- **THEN** the served descriptor carries the same two entries

### Requirement: A sent message shows one badge per prompt command, each opening its own prompt text

The transcript SHALL render a sent message as the line the user typed, with one prompt badge per listed prompt command at its position and the platform skill badges at theirs. Activating a prompt badge SHALL open the side panel on that prompt alone: its name, its `/command`, then the part of the stored text that came from that prompt. The panel SHALL NOT show the user's own words or another prompt's text under that prompt's name, and SHALL NOT read the prompt library. Copying the message SHALL give the line the user typed. A stored descriptor whose list does not fit the stored turn (a position outside the text, a command not found at its position in the typed line, entries out of order or overlapping) SHALL be ignored as a whole and the message SHALL render from the single fields.

#### Scenario: Two badges at their positions

- **GIVEN** a stored turn sent as `First /summary then /tone please`
- **WHEN** the conversation is displayed, live or after a reload
- **THEN** the bubble reads `First`, a `/summary` badge, `then`, a `/tone` badge, `please`
- **AND** no prompt text is shown in the bubble

#### Scenario: A badge opens its own prompt text

- **GIVEN** that message
- **WHEN** the user activates the `/tone` badge
- **THEN** the panel shows the name of the `tone` prompt, `/tone` and `Use a formal tone.`
- **AND** it shows neither `First`, `then`, `please` nor the text of `summary`

#### Scenario: A single prompt no longer shows the user's words

- **GIVEN** a turn sent after this change as `/summary the report`
- **WHEN** the user activates its badge
- **THEN** the panel shows the prompt's text without `the report`

#### Scenario: The prompt changed after the message was sent

- **GIVEN** a sent message with two prompt badges, and one of the prompts was edited or deleted since
- **WHEN** the user activates its badge
- **THEN** the panel shows the text that was sent, with no error

#### Scenario: Copy gives the typed line

- **WHEN** the user copies that message
- **THEN** the clipboard holds `First /summary then /tone please`

#### Scenario: A list that does not fit the turn is ignored

- **GIVEN** a stored descriptor whose list points outside the stored text
- **WHEN** the conversation is displayed
- **THEN** the message renders as a single-prompt turn from the single fields, with no error

### Requirement: Recall restores every prompt command of a sent message

Recalling a sent message SHALL put the typed line back in the composer and SHALL restore each listed prompt command as a token bound to the prompt it was sent with (its id, at its position), alongside the selected skills. Submitting the recalled line unchanged SHALL resolve each prompt from the currently authorised catalogs by that id, with no fallback to a prompt of the same name; a prompt that is no longer available SHALL hold the message back as on any submit. Two sent messages with the same typed line but different prompts SHALL remain separately recallable.

#### Scenario: Recall two prompts picked from different libraries

- **GIVEN** a sent message where `/summary` came from the team and `/summary-2` from the personal space
- **WHEN** the user recalls it and submits it unchanged
- **THEN** both tokens are restored and the same two prompts are read from their own libraries

#### Scenario: A recalled prompt was deleted

- **GIVEN** a recalled message with two prompt tokens, one of whose prompts was deleted
- **WHEN** the user submits it
- **THEN** nothing is sent and the error names that command

#### Scenario: Same line, different prompts

- **GIVEN** two sent messages typed `/summary` that ran the team prompt and the personal prompt
- **WHEN** the user browses the sent messages with ArrowUp
- **THEN** both are offered, each restoring its own prompt

### Requirement: Hand-typed prompt commands resolve one by one

A prompt command typed in full without picking a row SHALL be recognised and resolved for each occurrence on its own, with the rules that hold for a single one: the chat team's command first, then the personal one; no personal fallback before the team catalog has answered, the submit waiting for it as the requirement "Sending waits for the command catalogs" states; exact, case-sensitive name. A typed name that is also a platform skill SHALL keep the existing precedence: delimited, it is a skill selection, unless the user picked the prompt row for that token. Picked and typed prompt commands SHALL mix freely in one message.

#### Scenario: Two typed names from two libraries

- **GIVEN** `/summary` exists only in the team and `/tone` only in the personal space
- **WHEN** the user types `/summary and /tone now` in full and submits
- **THEN** both prompts are read, the first from the team and the second from the personal space, and both expand in place

#### Scenario: A homonym resolves per name

- **GIVEN** `/summary` exists in the team and in the personal space
- **WHEN** the user types it twice without picking a row and submits
- **THEN** both occurrences run the team's prompt

#### Scenario: Team catalog still loading

- **GIVEN** a message with a picked personal prompt and a typed `/tone` known only in the personal space, while the team catalog has not answered
- **WHEN** the user submits
- **THEN** nothing is sent until the team catalog answers
- **AND** once it has answered that it holds no `/tone`, the turn is sent with the picked prompt and the personal `tone` prompt

#### Scenario: A typed skill homonym stays a skill

- **GIVEN** a platform skill and a prompt both named `review`
- **WHEN** the user types `/summary then /review the text` without picking a row for `review`, and submits
- **THEN** `summary` expands as a prompt and `review` travels as a skill selection, not as a prompt

### Requirement: Single-prompt turns and older readers are unaffected

A turn stored before this change, whose descriptor has only the single fields, SHALL render, open its panel, copy and recall exactly as before. A reader that knows only the single fields SHALL still render a turn that lists several prompts: the first prompt as a badge at its position, the rest of the typed line as text, and the whole sent text in the panel. A turn stored by a runtime that does not know the list SHALL be stored and served with its single fields, and SHALL render that same way.

#### Scenario: An old conversation

- **GIVEN** a conversation whose command turns were stored before this change
- **WHEN** it is opened
- **THEN** each of those turns shows one badge, and its panel shows the whole text that was sent, as today

#### Scenario: A reader that ignores the list

- **GIVEN** a stored turn listing two prompts, read by a client that knows only the single fields
- **WHEN** it is displayed
- **THEN** the first prompt shows as a badge, the second as the `/name` the user typed, and nothing errors

#### Scenario: A runtime that does not know the list

- **GIVEN** a turn with two prompt commands sent to a runtime that predates the list
- **WHEN** the turn runs and the conversation is reloaded
- **THEN** the agent received the full assembled text of both prompts
- **AND** the reloaded message shows the first prompt as a badge and the second as the `/name` the user typed

### Requirement: The same prompt command may appear more than once in a message

A prompt command present several times in one message SHALL be expanded at each occurrence, each with its own token, badge and descriptor entry. A prompt used several times SHALL be read once per submit.

#### Scenario: The same command twice

- **GIVEN** `/summary` whose prompt text is `Summarise the document.`
- **WHEN** the user submits `/summary of A, /summary of B`
- **THEN** the sent text holds `Summarise the document.` twice, each followed by its own words
- **AND** the message shows two `/summary` badges and the prompt was read once

### Requirement: The first prompt command names the conversation

When the first message of a conversation holds prompt commands, the conversation's title SHALL be built from the name of the first prompt command of the line, followed by the user's own text, as it is today for a single command.

#### Scenario: A new conversation started with two prompts

- **GIVEN** `/summary` is the command of the prompt named `Weekly review`
- **WHEN** a new conversation starts with `/summary /tone the Q3 report`
- **THEN** the conversation's title starts with `Weekly review` and continues with `the Q3 report`

### Requirement: Running prompt commands leaves prompt use counters unchanged

Sending a message with one or several prompt commands SHALL NOT change a prompt's use counters, as is the case today for a single command. Copying a prompt from the library, choosing it in an agent form and attaching it to a conversation SHALL keep counting as they do.

#### Scenario: Two commands run

- **GIVEN** two prompts with known use counters
- **WHEN** the user sends a message that runs both through their commands
- **THEN** neither counter changes

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

### Requirement: Packaged skill presentation follows the interface language

The frontend SHALL display French or English titles and descriptions for packaged skills using i18n, with English or authored fallback. Runtime catalog and load provenance SHALL distinguish packaged skills from custom homonyms. Canonical names, commands, copied text, stored selection identity, English model metadata, bodies and argument hints SHALL remain unchanged.

#### Scenario: Localized invocation and historical activity
- **WHEN** the interface language changes between French and English
- **THEN** menus, composer/history badges, detail metadata, load activity and administration use the corresponding title and description
- **AND** commands and selection payloads retain their canonical names

#### Scenario: Custom homonym or missing translation
- **WHEN** a custom source uses a packaged name or reliable packaged provenance is absent
- **THEN** the frontend retains authored metadata rather than applying an unrelated translation

### Requirement: Feature managers administer packaged skills globally

Administration SHALL provide a global Skills tab under Features with packaged inventory, invocation modes, source availability and one enabled control per skill. Only feature-management permission SHALL allow administration. No exception SHALL mean enabled, including newly shipped skills. Shared persistent overrides SHALL have audit identity/time and atomic idempotent updates. Custom directories SHALL retain their existing behavior.

#### Scenario: Global opt-out across replicas
- **WHEN** an authorized manager disables a packaged skill
- **THEN** new loads from the next turn, including existing conversations and resumes on another replica, are denied in discovery, selections, pins, native reads/searches, loaders, children and capability access
- **AND** in-flight work and already-read history are preserved

#### Scenario: Concurrent independent updates
- **WHEN** two managers change different skills through separate instances
- **THEN** both changes remain persisted and affect the next server-resolved execution policy

#### Scenario: Mixed or unavailable runtime sources
- **WHEN** a source is unreachable or cannot enforce enablement
- **THEN** administration reports its status and does not claim effective global disablement
- **AND** legacy runtimes cannot resolve managed execution while active restrictions require unsupported enforcement

### Requirement: Common skills include an explicit interview and grounded data workflows

The packaged catalog SHALL include an explicit-only grill-me procedure adapted for general users, a user-facing analyze-data procedure and an agent-only data-visualization procedure. Instructions SHALL be English and UI titles/descriptions SHALL have French/English presentation. New skills SHALL be enabled by default and respect current invocation and administrative policy. They SHALL use available tools without installing dependencies, inventing values or duplicating capability-specific access rules.

Original Fred procedures SHALL include their instructions in packaged resources without requiring external documentation downloads. Imported skills SHALL retain their upstream references and required notices.

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

### Requirement: Native skill read guidance requests complete instructions explicitly

Deep parent and native-child guidance SHALL require explicitly requesting 1000
lines when reading a skill's main instructions. It SHALL explain that an omitted
limit can return only 100 lines, require checking the returned window and
truncation information, and direct continuation before applying the procedure.
Complete instructions already present in context SHALL remain reusable.

#### Scenario: Autonomous main-instruction read

- **WHEN** a Deep parent or native child receives its available skill guidance
- **THEN** it is explicitly directed to pass a limit of 1000 for the main skill file
- **AND** it is directed to retrieve remaining instructions before applying them
- **AND** native tool defaults, explicit windows and reference pagination are unchanged

### Requirement: Skill activity discloses partial instruction reads

A successful native first-page skill read SHALL disclose whether its actual
returned window is partial through existing load attribution and activity.
Pagination, size truncation or unproven full coverage SHALL NOT appear as a
confirmed full-file read. French activity SHALL say "Skill partiellement chargé"
and English activity SHALL say "Skill partially loaded" for partial reads.
The flag SHALL survive streaming and history reload with the existing trusted
origin and parent/child attribution. Existing successful-read counting and
continuation/reference exclusions SHALL remain unchanged. This disclosure SHALL
describe the individual read and SHALL NOT assert cumulative page coverage.

#### Scenario: First 100 lines of a longer skill

- **WHEN** a successful native read returns lines 1-100 of a 222-line main skill file
- **THEN** its activity is marked partial in the selected UI language
- **AND** its accessible name and trace label convey the same partial status
- **AND** reloading history preserves that disclosure

#### Scenario: Size-clipped output despite a large requested window

- **WHEN** the requested window could cover the whole skill but the actual output is clipped by size, including inside one source line
- **THEN** the activity is partial regardless of the requested line limit
- **AND** unknown or missing coverage information cannot establish completeness

#### Scenario: Complete and legacy loads

- **WHEN** a native read proves full-file coverage without truncation, a native full pin or ReAct load succeeds, or an older stored activity lacks the new flag
- **THEN** the existing complete-load presentation is retained

#### Scenario: Parent and child windows are independent

- **WHEN** concurrent Deep parent and native-child main-file reads return different coverage
- **THEN** each activity retains its own partial flag and trusted execution identity
- **AND** continuation pages, references, empty windows and failed reads do not add load counts
