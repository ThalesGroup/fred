# Platform Agent Skills Specification

## Purpose

Let users and agents apply platform-owned Markdown workflows through one shared, read-only skill catalog, with progressive loading, normal conversation continuity and visible invocation in managed web chat.

## Requirements

### Requirement: Platform skills are published from a startup snapshot

Platform-distributed skills and their reference files SHALL reside under `fred_runtime/skills/` in the `fred-runtime` package and SHALL be included in its wheel and source distribution. The deployment SHALL configure an optional skill directory whose immediate skill subdirectories contain `SKILL.md` with a valid unique `name`, a `description` and Markdown instructions. The packaged directory SHALL be resolvable from an installed runtime outside the repository. Packaging alone SHALL NOT enable skills without configuration. Skill contents and references SHALL be read-only to agents. The pod SHALL publish a validated snapshot at startup for the web catalog, ReAct explicit preload, preview and ReAct reads until restart. Deep native reads SHALL use the physical configured directory through upstream FilesystemBackend. Invalid, duplicate, oversized or unreadable skills SHALL be excluded from the web/ReAct snapshot with bounded diagnostics without preventing other skills or the pod from working. The supported first-version catalog size SHALL be a few dozen skills; it SHALL NOT require a separate search service.

#### Scenario: Skills available from an installed runtime distribution

- **GIVEN** `fred-runtime` is built and installed outside the monorepo checkout
- **WHEN** a pod is configured to use its packaged skills directory
- **THEN** the shipped skills and references are discoverable and readable from that distribution
- **AND** no copy of those files under `apps/fred-agents` is required

#### Scenario: No directory configured

- **WHEN** a pod starts without skill configuration
- **THEN** it exposes no skills or skill-loading tools
- **AND** no skill catalog or body is injected, including the former automatic Mermaid rules

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

Every ReAct agent with skills configured SHALL receive validated catalog names, descriptions and optional advisory argument hints inside the existing system prompt `<tools>` block. Deep parents and native children SHALL receive the upstream native catalog through create_deep_agent skills configuration, without a duplicate Fred catalog or custom skills middleware. Both catalogs SHALL explain progressive instruction/reference loading without injecting all skill bodies. ReAct catalog content SHALL escape reserved prompt-layer tags and render no section when empty. Deep SHALL use upstream formatting and its native empty-source section; its trusted source files SHALL follow the platform instruction hierarchy.

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

### Requirement: Mermaid guidance uses progressive skill loading

The packaged catalog SHALL include an English `mermaid` skill with an advisory argument hint and the existing conservative diagram syntax rules. Mermaid instructions SHALL be loaded only through the shared skill workflow; runtime prompt assembly SHALL NOT inject the former SDK output contract automatically. The existing frontend Mermaid renderer and sanitization SHALL remain available.

#### Scenario: Mermaid catalog metadata before loading

- **GIVEN** a pod uses the packaged skills directory
- **WHEN** an agent receives its system prompt
- **THEN** `mermaid` is advertised with its description in the native Deep index or with its description and advisory hint in the ReAct catalog
- **AND** its diagram syntax instructions are absent until loaded

#### Scenario: User or model loads Mermaid

- **WHEN** a user invokes `/mermaid` with or without text, or the model reads its instructions with ReAct `load_skill` or Deep native `read_file`
- **THEN** the runtime supplies its instructions with the existing origin attribution and successful-load KPI
- **AND** no tool named `mermaid` is registered
- **AND** complete returned Mermaid diagrams continue to use the existing frontend renderer

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

Web selections and ReAct loading SHALL resolve a catalog name on the server. ReAct reference reads SHALL resolve a relative file path within that skill's published directory, support bounded UTF-8 text and reject traversal, absolute host paths, escaping symlinks, unsupported content and writes. Deep native access SHALL follow the separate physical-filesystem requirement: current files remain confined to the configured root, without per-skill snapshot filtering. Skill access SHALL NOT expose arbitrary host or conversation files, execute scripts, install tools or grant permissions. A frontmatter tool hint SHALL NOT be treated as a permission grant or an enforced restriction.

#### Scenario: Read an associated template

- **WHEN** a ReAct agent reads `references/modele-compte-rendu.md` from the valid `compte-rendu` skill
- **THEN** it receives that snapshot's reference text without needing general filesystem access

#### Scenario: Escape or write attempt

- **WHEN** a ReAct request attempts to read outside the selected skill or modify its files
- **THEN** the operation is refused without returning unrelated file contents

### Requirement: Deep agents can read the published skills filesystem

Deep parents and native children SHALL mount the configured physical skill directory at `/skills/` with unmodified upstream `FilesystemBackend(root_dir=directory, virtual_mode=True)` in their existing composite backend. Fred SHALL configure skills through `create_deep_agent(skills=["/skills/"])` and the explicit child's `skills` field, without constructing skills middleware, synthetic metadata files, a custom snapshot filesystem backend or an additional native catalog prompt. Upstream SHALL own discovery, metadata caching, instruction/reference reads, listing, search and pagination. Matching physical folder/frontmatter names SHALL identify well-formed native skills. Agent and capability writes to `/skills` and its descendants SHALL be denied, and production resources SHALL be read-only on disk. Existing conversation workspace/artifact behavior SHALL remain intact. ReAct SHALL retain its current snapshot and confined tools; Deep SHALL register neither Fred skill tool. Web previews and ReAct preload SHALL retain their existing validated startup service and trusted attribution. Deep SHALL NOT preload selected skills, validate their bodies against the startup snapshot, or prepend Fred skill-instruction messages; the canonical user request SHALL reach native discovery and model-driven reads unchanged.

#### Scenario: Native instruction and reference reads

- **GIVEN** the published `compte-rendu` skill contains instructions and `references/modele-compte-rendu.md`
- **WHEN** a Deep parent or native child uses `read_file` on `/skills/compte-rendu/SKILL.md` and then its canonical reference path
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

- **GIVEN** the current user turn selects `compte-rendu` through the typed slash invocation
- **WHEN** the Deep parent or child successfully reads that skill's SKILL.md at offset zero
- **THEN** its actual load event and KPI use user origin without adding a preload or changing the native tool result
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
- **AND** explicit Deep selection remains user text without preload or snapshot body validation; actual native reads use user origin for the currently selected skill and agent origin for other skills, while ReAct retains both confined Fred tools and user-origin preload

### Requirement: Web users can require a skill for their request

Managed web chat SHALL accept `/<name> [request]` at the invocation position and retain `/skill <name> [request]` compatibility and offer skill-name autocompletion from the selected agent's actual runtime catalog. Submission SHALL transmit typed name-only skill selections and the complete canonical user text including every invocation at its original position; for ReAct, the server SHALL validate and load the selected skill before the first model call from its snapshot rather than client instructions. Deep SHALL use the canonical request as ordinary user text, without Fred preload or snapshot body validation; native model choice SHALL determine instruction/reference reads. A named invocation SHALL remain valid without arguments, even if the skill requires information to finish. Argument hints SHALL be optional descriptive text, never submission requirements. A bare `/skill` SHALL offer selection guidance without launching an empty agent turn. An unknown, invalid or unavailable explicit ReAct selection SHALL fail clearly before any model call, with no fallback to another skill or a prompt command.

#### Scenario: Explicit load precedes inference

- **WHEN** an authorized user submits `/compte-rendu prepare the minutes from these notes` to ReAct
- **THEN** the runtime loads `compte-rendu` before its first model call
- **AND** the model receives those instructions and the complete request

#### Scenario: Explicit Deep selection follows native loading

- **WHEN** an authorized user submits `/compte-rendu prepare the minutes from these notes` to Deep
- **THEN** the first inference receives the canonical user message and upstream skill metadata, without a Fred-loaded instruction message or user-origin load event
- **AND** the model can read `/skills/compte-rendu/SKILL.md` and its references with native `read_file`, with actual reads retaining user-origin events/KPI for the selected name and agent origin otherwise
- **AND** invoke, streaming, checkpoint follow-up and HITL resume use the same native behavior

#### Scenario: Discover skills directly from the slash menu

- **WHEN** an authorized web user types `/` in the composer
- **THEN** every skill from the selected runtime catalog is offered directly, alongside prompt commands
- **AND** a prefix such as `/comp` filters those skill names without requiring `/skill` first
- **AND** selecting a skill completes the canonical invocation without sending a turn or losing existing request text
- **AND** prompt and skill entries sharing a name remain independently selectable
- **AND** no standalone `/skill` dispatcher row is shown; named skills use a distinct platform pictogram and localized origin hint
- **AND** hovering the selected or sent skill name shows its description from the current runtime catalog when available, with its platform origin

#### Scenario: Named invocation without arguments

- **WHEN** a user submits `/compte-rendu` without meeting notes in context
- **THEN** the turn starts; ReAct preloads instructions before inference, while Deep uses native metadata and model-driven instruction reads
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
- **WHEN** the catalog and composer suggestions are rendered
- **THEN** the supplied hint is shown as advisory text and both skills are usable
- **AND** non-string, blank or over-256-character hints are omitted with bounded diagnostics while retaining the valid skill

#### Scenario: Skill badge in the composer and user message

- **WHEN** a user completes a known `/<name>` selection or types a whitespace-delimited known name
- **THEN** the composer shows a discreet icon/name token inline with the editable request, with the complete name visible and no filled pill, separate row or removal button, allowing submission without extra text
- **AND** editing any invocation character removes recognition and preserves surrounding text; deleting surrounding request text does not remove the skill
- **AND** persisted name-only selection metadata lets the sent user bubble display the same skill badge alongside its request, including after reopening history without the current catalog
- **AND** Deep selection metadata preserves the badge/preview without a preload event, instruction injection or load count; native agent-origin reads do not select ordinary user mentions
- **AND** automatic agent/child loads and ordinary messages merely mentioning `/skill` do not label the user turn as explicitly selected
- **AND** copying a selected user turn includes the skill invocation and request

#### Scenario: Existing empty-request representation

- **GIVEN** a selected skill's stored question is exactly `/skill <name>`
- **WHEN** the user message is rendered or copied
- **THEN** the UI interprets the stored question as the existing no-request sentinel, shows the skill label alone, and copies canonical `/<name>` text
- **AND** a literal request identical to that sentinel remains indistinguishable under the existing name-only wire representation; all other request text is retained

#### Scenario: Stale menu or forged selection

- **WHEN** a submitted ReAct name is unavailable in the serving pod's validated snapshot
- **THEN** the runtime reports an explicit selection error and does not call the model

#### Scenario: Keyboard and agent switching

- **WHEN** the user types the skill prefix and navigates the suggestions
- **THEN** arrow keys, completion, submission and dismissal work through the existing composer interaction
- **AND** switching the selected agent invalidates suggestions from the previous runtime

### Requirement: Explicit skill selections compose within one turn

Managed web chat SHALL retain and render all explicit platform skill invocations in the same draft, including after another selection. Submission SHALL carry all distinct selected names in first-occurrence order, preserving canonical request text and every invocation occurrence. ReAct SHALL validate all selections and load their instructions before first inference through its existing loading boundary. Deep SHALL preserve native upstream loading without Fred preload; actual reads matching any current selection SHALL use user origin. Legacy single-selection requests and history SHALL remain supported. Duplicate invocation occurrences SHALL NOT cause duplicate explicit preloads.

#### Scenario: Select two platform skills

- **WHEN** a user completes `/compte-rendu`, then `/verify-answer`, and submits the request
- **THEN** both inline selections and surrounding text remain intact
- **AND** both distinct names reach the same execution turn
- **AND** ReAct receives both procedures before inference; Deep receives the canonical user text and uses native reads

#### Scenario: Independent editing and duplicate occurrences

- **GIVEN** a draft contains two selected skills and a repeated invocation of one
- **WHEN** the user edits or removes one invocation
- **THEN** other recognized invocations remain selected and canonical copy/undo work
- **AND** a name still invoked elsewhere remains selected once for execution

#### Scenario: All-or-error ReAct validation

- **GIVEN** one selected ReAct skill is unavailable in the serving snapshot
- **WHEN** the request is submitted
- **THEN** it fails clearly before any model call without silently running only the remaining skills

#### Scenario: Preserve selections across history and same-exchange resume

- **WHEN** a multi-skill turn is optimistically rendered, reopened, copied, edited, restarted or resumed through HITL
- **THEN** all explicitly selected names remain represented independently of actual load events
- **AND** same-exchange resume does not duplicate ReAct preload and preserves matching native user-origin attribution
- **AND** a fresh follow-up does not inherit those selections

#### Scenario: Combine an inline prompt with platform skills in either order

- **GIVEN** a managed user selects an available `/hello` prompt and two platform skills, in either selection order
- **WHEN** the request is submitted
- **THEN** the exact inline prompt is resolved under its owning team/id and its instructions reach the model alongside both procedures and the remaining request
- **AND** prompt selection, skill badges and their attribution coexist in the draft and history
- **AND** prompt resolution failure sends no partial skills-only turn
- **AND** an explicitly selected prompt homonym is not added as a platform skill

### Requirement: ReAct slash commands combine platform skills and two prompt libraries

For ReAct managed chat, the slash menu SHALL offer platform skills from the selected runtime alongside prompts carrying commands from the current chat team and the caller's personal library. The menu SHALL identify each entry's source and preserve independently selectable homonyms. A personal chat SHALL offer its personal prompt library once. Prompts without commands SHALL remain available through the existing library panel. Deep and other execution families SHALL retain their existing prompt-library sources. Available prompt commands SHALL complete, render and resolve inline before or after selected skills in all managed chats, with the same blue prompt icon/name treatment in the draft and sent history.

#### Scenario: ReAct team chat offers three sources

- **GIVEN** a ReAct team agent, a personal prompt command and a team prompt command
- **WHEN** the authorized user types `/`
- **THEN** the menu offers both prompt commands alongside the runtime's platform skills with their source labels
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

- **WHEN** a personal ReAct chat opens or the active team or agent changes
- **THEN** each eligible prompt source appears once and prior selections and cached responses do not dispatch another scope's prompt
- **AND** failed reads or unavailable personal identity do not fall back to a different selected prompt; an invalidated completed choice requires command editing or reselection

#### Scenario: Pending team discovery cannot change typed precedence

- **GIVEN** the personal command catalog is available while the chat team's catalog is unresolved
- **WHEN** the user submits a typed prompt command without explicitly selecting a row
- **THEN** personal fallback is refused until the team's absence of that command is established
- **AND** an explicit personal row selection remains independently usable while team discovery is pending

#### Scenario: Other execution families retain current behavior

- **WHEN** the selected template is Deep, Graph, Proxy or not yet resolved as ReAct
- **THEN** the personal-plus-team command addition is not enabled
- **AND** the existing skill and prompt dispatch behavior is preserved

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

Web chat SHALL show a compact load step for actual loads containing the skill name and whether it was preloaded for ReAct by the user or read by an agent. Deep selection alone SHALL NOT emit a load step or user-origin attribution; its canonical invocation text and name-only selection metadata SHALL remain in history, independently of loading. Runtime history SHALL preserve this attribution without requiring the current skill file to exist. Each actual load SHALL be represented once, including Deep-child loads; human-requested preloading SHALL NOT be represented as a model-issued tool call that never happened. Full instruction inspection in the web UI SHALL NOT be required.

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

The platform SHALL distribute English-written instructions and references for a focused quality/reliability catalog: `grounded-research`, `summarize-document`, `compare-options`, `verify-answer` and the existing `compte-rendu` skill with a referenced minutes template under `fred_runtime/skills/compte-rendu/`. The minutes instructions SHALL guide the agent to read supplied notes, identify decisions and actions, and report owners or dates as missing when absent. It SHALL work through explicit web invocation and automatic model selection with available document-reading tools.

#### Scenario: Notes omit a deadline

- **GIVEN** notes describe a decision and an assigned action without a deadline
- **WHEN** the agent uses `compte-rendu` and its reference template
- **THEN** the output includes the supported decision and action and marks the deadline as unspecified
- **AND** it does not invent a deadline

#### Scenario: Evidence-dependent workflows lack sources

- **WHEN** a research, summary, comparison or verification skill has insufficient evidence to complete its requested output
- **THEN** its instructions guide the agent to use available context and tools, distinguish evidence from inference, and report the missing information
- **AND** they do not claim to have read unavailable sources or verified unsupported facts

### Requirement: Read-only skill instruction preview

Managed web chat SHALL make an explicitly selected inline skill name clickable in the composer and in sent or reopened user messages, and each successful skill-load row activatable in the reasoning trace regardless of user, agent or child origin. Activating it SHALL open the existing right-hand chat panel with the complete name, description, optional argument hint and formatted instructions from that skill's current runtime snapshot. Catalog responses SHALL remain metadata-only. A separate authenticated, typed detail read SHALL use the selected managed instance's runtime source and the existing team-use authorization. It SHALL expose only the selected startup-snapshot `SKILL.md`, never an arbitrary client path. Preview SHALL NOT send a user turn, invoke a model, load instructions into agent context or modify the draft. Preview SHALL use a large neutral `Skill: <name>` title, optional `Arguments:` followed by the argument hint above `Description:` and its text, and a divider before the instructions. It SHALL omit redundant content headings and technical runtime-version labels. Activating the currently previewed skill again SHALL close the panel; activating another skill SHALL replace its contents. Historical preview SHALL read the current runtime snapshot without claiming to reconstruct the previously loaded body.

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
- **AND** arguments, when supplied, are labeled and shown above the description, without dispatching a turn or editing the draft

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

The platform SHALL emit one skill-usage counter per actual successful skill load, with the validated skill name, trusted user-or-model origin and existing bound team/session/exchange/managed-instance attribution when available. Explicit user preloads SHALL have user origin; automatic agent and Deep-child loads SHALL have model origin. Failed loads, preview reads, reference-file reads, history/status replay and resumes without a new load SHALL NOT increment this counter. An actual subsequent successful reload SHALL count again; continuing to use instructions already retained in context SHALL NOT imply a newly observed invocation. KPI events SHALL NOT contain skill bodies, reference text or user requests. Collection SHALL use the existing fail-open KPI mechanism and SHALL NOT add direct blocking storage calls to loading.

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
