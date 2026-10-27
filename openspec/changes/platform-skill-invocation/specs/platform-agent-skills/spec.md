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
