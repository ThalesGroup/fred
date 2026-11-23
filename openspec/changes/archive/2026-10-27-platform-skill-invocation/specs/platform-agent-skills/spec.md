## MODIFIED Requirements

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
- **AND** no standalone `/skill` dispatcher row is shown; named skills use a distinct platform pictogram and localized origin hint
- **AND** hovering the selected or sent skill name shows its description from the current runtime catalog when available, with its platform origin

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

### Requirement: Skill file access stays within the declared skill

Web selections and ReAct loading SHALL resolve a catalog name on the server. ReAct reference reads SHALL resolve a relative file path within that skill's published directory, support bounded UTF-8 text and reject traversal, absolute host paths, escaping symlinks, unsupported content and writes. Deep native access SHALL follow the separate physical-filesystem requirement: current files remain confined to the configured root, without replacing physical body bytes with snapshot content; per-skill eligibility SHALL still derive from validated metadata and current policy. Skill access SHALL NOT expose arbitrary host or conversation files, execute scripts, install tools or grant permissions. A frontmatter tool hint SHALL NOT be treated as a permission grant or an enforced restriction.

#### Scenario: Read an associated template

- **WHEN** a ReAct agent reads `references/meeting-minutes-template.md` from the valid `meeting-minutes` skill
- **THEN** it receives that snapshot's reference text without needing general filesystem access

#### Scenario: Escape or write attempt

- **WHEN** a ReAct request attempts to read outside the selected skill or modify its files
- **THEN** the operation is refused without returning unrelated file contents

## ADDED Requirements

### Requirement: Skill invocation controls distinguish user and agent requests

Skills SHALL accept boolean user-invocable (default true) and disable-model-invocation (default false) frontmatter controls. Invalid values SHALL exclude the affected skill with bounded diagnostics. User-ineligible skills SHALL be unavailable for direct user selections but remain eligible for autonomous use unless disabled for model invocation. Explicit-only skills SHALL load only for a current eligible selection. These controls SHALL apply to catalogs, loaders, references, native file searches and children without granting permissions or erasing already-loaded context.

#### Scenario: Agent-only skill
- **WHEN** a skill has user-invocable false and model invocation enabled
- **THEN** it is absent from user commands and direct selections are rejected
- **AND** agents can discover and load it with truthful attribution

#### Scenario: Explicit-only and unavailable skills
- **WHEN** an explicit-only skill is selected by a user
- **THEN** it loads for that request but is unavailable for new autonomous loads on later turns
- **AND** disabling both invocation routes leaves neither route eligible

### Requirement: Deep native pins preserve truthful load visibility

Explicit Deep selections SHALL be deduplicated in request order and passed as pinned_skills. Successful native instruction loads SHALL emit user-origin activity and usage exactly once per actual load. Unknown, ineligible and globally disabled names SHALL be rejected. Failed native pins SHALL not be reported as successes. Resume and replay SHALL not reload selections. Parent selections SHALL not blindly pin every child.

#### Scenario: Multiple selected skills and resume
- **WHEN** a Deep turn selects two skills and subsequently resumes a human approval
- **THEN** both load natively before inference in selection order
- **AND** the resume does not repeat their loads or usage counts
