## Context

See `proposal.md` for motivation and the confirmed extension of #2711. The relevant existing seams are:

- `react/middleware/frame.py` and `deep/deep_runtime.py` both assemble LangChain middleware. Deep passes `skills=["/skills/"]` to `create_deep_agent` and to its explicitly configured general-purpose child.
- The installed `deepagents.middleware.skills.SkillsMiddleware` parses and validates metadata through a `BackendProtocol`, caches it in agent state and supports disabling its default system-prompt append. It provides no loading tool. Deep uses the native prompt/catalog produced by `skills=`; Fred continues to disable execution and deny writes to the skill mount.
- `react/react_prompting.py:compose_system_prompt` owns the four-block assembly shared by both runtimes. Catalogs belong in `<tools>`; `escape_reserved_prompt_tags` is the existing content-boundary helper.
- `react/react_tool_resolution.py` normalizes common ReAct/Deep tools; `react/react_tool_binding.py`, `ToolObservabilityMiddleware` and the shared transport own tool traces/events. Existing checkpoint hygiene trims model input without rewriting persisted history.
- `useComposerCommands.ts` already supports `/`, prefix filtering, keyboard completion and prompt-command submission. `RuntimeContext.command`/`TurnCommand` is prompt attribution only, not a trusted skill-selection channel.
- Control-plane resolves managed instances to configured runtime sources. It must not read pod-local files or aggregate an unrelated pod's catalog. Prompt writes currently permit the name `skill`.

The active prompt-command changes explicitly excluded user-invocable platform skills. They remain historical scope statements; the developer has now approved this new feature and the reservation of `/skill`.

## Goals / Non-Goals

**Goals:** one pod-owned read-only source, a shared source folder with native Deep loading and the existing ReAct/web snapshot, and a typed web selection with deterministic ReAct preload and native model-driven Deep loading. Reuse upstream parsing and Fred's prompt, event, authorization and history seams.

**Non-Goals:** see `proposal.md`. In particular, this is platform middleware plus shared tools, not an agent-selected capability package; per-agent enablement and Graph integration are excluded. No new permission grant follows from loading a skill.

## Decisions

### 1. Build a bounded immutable snapshot at pod startup

Add optional skill-directory configuration to `AgentPodConfig` and carry a pod-lifetime catalog/service through `RuntimeConfig`/`RuntimeServices`. Store the platform-owned instruction files and references under `libs/fred-runtime/fred_runtime/skills/`, with the example in `skills/compte-rendu/`. This is package data, distinct from the Python middleware/service implementation. `apps/fred-agents` consumes the runtime package and does not own or duplicate these files.

Include all declared skill Markdown/reference files in the `fred-runtime` wheel and source distribution; the current `pyproject.toml` only explicitly declares migration templates as package data. Resolve the packaged directory from the installed runtime package, not a repository-relative path or the shell's working directory. Resolve other configured relative deployment paths against the project/configuration root. An enabled deployment can select the packaged directory through the optional configuration; installing the package alone does not activate skills. Image and volume deployments retain the same read-only snapshot contract. Verify discovery/reference reads from a built, installed distribution outside the checkout, since editable monorepo installs can hide omitted package data.

Enumerate only skill subdirectories and approved UTF-8 instruction/reference files. Canonicalize and confine paths before copying bytes into a bounded immutable backend implementing the required `BackendProtocol` read operations. Reject writes and exclude unreadable, oversized or escaping entries. Run the upstream public discovery hook against that backend once at bootstrap, reuse its validated `SkillMetadata`, and reject duplicate names instead of adopting upstream's last-wins merge. Publish the files and metadata together. After upstream validation, use the existing public YAML dependency to read only Fred's optional `argument-hint` extension from the first YAML document. Expose it as nullable `SkillSummary.argument_hint` (1–256 characters); ignore an invalid hint with bounded folder diagnostics while keeping the otherwise valid skill. Hints are descriptive metadata, never required-argument validation or variable substitution. No filesystem scans or blocking disk reads belong in model-call hooks.

ReAct retains `SnapshotSkillsMiddleware`, immutable instruction/reference reads and catalog rendering. The web catalog, ReAct explicit user preload and previews also retain the existing validated startup service. Bootstrap creates one unmodified native FilesystemBackend for the same physical directory, off-thread; request-scoped composites reuse it without resolving disk paths. Do not retain a second canonical file mapping or build a Deep snapshot backend.

Deep delegates discovery and prompt injection to `create_deep_agent(skills=["/skills/"])`, including `skills` on the explicitly declared child. Native metadata is cached per conversation by upstream. Native instruction/reference reads use the actual filesystem and can see edits before restart; the web catalog, preview and ReAct explicit preload remain startup snapshots. Production resources must remain identical and read-only across replicas; restart after deployment to refresh web metadata. Well-formed native skills use matching directory/frontmatter names. The trusted directory is the packaged `fred_runtime/skills/` by default; existing configured directories remain supported. No subclass, monkey patch, alternate parser or custom skills middleware is needed.

### 2. Keep catalog rendering within the existing prompt hierarchy

For ReAct, render validated names/descriptions and advisory hints and short Fred loading guidance through the shared prompt composer into `<tools>`, before its closing tag. Deep uses upstream native skills prompt injection and does not also receive the Fred skill catalog. Use the existing reserved-tag escaping for metadata and for any skill text added to a model message. ReAct does not append an upstream skills section. Deep accepts upstream placement while the existing runtime denies script execution and maintains platform instruction precedence. Full bodies and references enter conversation messages only when loaded.

Build the ReAct catalog fragment once for the snapshot and reuse it in compiled ReAct prompts. With no valid ReAct skills, omit its middleware/tools/fragment; an enabled Deep source delegates empty discovery to upstream. Apart from the developer-approved removal of automatic Mermaid guidance described below, preserve no-skills prompt behavior. Platform instructions retain precedence; skills describe procedures, not new authority.

Move the former `fred-sdk` Mermaid output contract into `fred_runtime/skills/mermaid/SKILL.md`. Its English description advertises creating and repairing parse-safe diagrams, and its optional hint describes the diagram goal/source and constraints. Keep the established conservative syntax rules in the skill body; the catalog advertises only metadata. Use existing manual preload, model `load_skill`, preview and load KPI paths without registering a Mermaid tool. Remove the old SDK file, global prompt bundle and runtime injection. The shared Markdown resource loaders remain available to agent authors. Frontend rendering/sanitization and static test-agent renderer fixtures remain unchanged. Deployments with skills disabled no longer receive Mermaid instructions; deployments using a custom directory must include this skill themselves. Loaded historical messages retain the normal continuity contract.

Catalog guidance and the shared loaded-message wrapper explicitly distinguish Markdown procedures from executable tools: loading never registers a function, catalog names must not be converted into invented tool calls, and `argument-hint` is user-input guidance rather than a JSON schema. The agent follows the procedure itself and uses the declared tools for necessary actions/reference reads. This reduces model ambiguity without rewriting provider tool calls or guaranteeing model compliance; existing tool validation still rejects unknown names.

### 3. Share narrow loading tools across the runtimes

Expose `load_skill(name)` and `read_skill_file(name, path)` to ReAct from one shared service and tool factory. Arguments contain only the skill name and a skill-relative path; paths, snapshot revision, identity and origin come from bound server context. Return bounded UTF-8 content with skill attribution, and a clear error for unknown names or forbidden references. No writes, execution or arbitrary absolute-path reads are exposed.

Bind ReAct tools through the existing common runtime tool path. Deep parent and native children omit this tool factory and use the mounted native filesystem alongside upstream skills middleware. Check tool-name collisions before compilation and include the names in the effective tool set used by limits/HITL. Use existing traces, authorization checks, timers and history flow rather than a second tool runner. ReAct retains confined tool access without a general filesystem.

### 3a. Use the native Deep filesystem and skills constructor

Mount `/skills/` in the existing `CompositeBackend` using `FilesystemBackend(root_dir=skills.directory, virtual_mode=True)`. Preserve scratchpad, `/.deep/`, artifact routing and quotas, and compose without mutating capability backends. Keep the small route-collision check and first-match deny rule for `/skills` and `/skills/**`; capability filesystem writes, including system-origin writes, must not modify this mounted directory. FilesystemBackend itself remains the unmodified upstream implementation; production files/volumes are read-only.

Pass `skills=["/skills/"]` directly to `create_deep_agent` and to the explicit general-purpose child whenever a directory is configured. Do not add SkillsMiddleware to Fred's frame or render a second catalog. An enabled empty directory still mounts and lets upstream handle discovery. Parent and child share the same backend, including filesystem tools and capability ports. ReAct keeps its existing loading tools and middleware. Native reads use physical directory names, pagination/search and upstream path confinement; supported file types and discovery diagnostics are upstream-owned rather than Fred's snapshot filtering.

Keep the existing observation of successful native reads for truthful skill-load events/KPI and escaping at the model boundary. Origin describes who requested the skill: match the current RuntimeContext.skill name to attribute a successful parent/child instruction read to the user; other names and later turns without a selection remain agent-origin. Same-exchange web HITL resumes restore the original name-only selection from that exchange's user-message metadata; fresh turns omit it. Do not parse arbitrary slash mentions, consult other historical exchanges, or preload bodies to infer origin. Reference/continuation/failure/selection-only paths remain uncounted. Attribute successful native instruction reads by their mounted skill path, including skills added after startup, without depending on the web/ReAct catalog or retaining a duplicate text snapshot just for Deep. Continuation/reference/error/replay windows do not count; stored reference excerpts still drive previews. Web previews retain the startup service. Deep selection does not read the snapshot or inject instruction messages: preserve canonical user text and let native discovery/read_file load instructions. ReAct selection/preload is unchanged; resumes do not repeat ReAct preloads.

### 4. Route explicit web selection as typed runtime input

Add an optional typed skill invocation collection to the runtime request/context contract, separate from prompt-only `TurnCommand`. The frontend sends the selected name and the trailing request when present, never the skill body or a host path. A bare `/skill` offers guidance without a turn. `/skill <name>` is valid: preserve that literal user command as turn text rather than inventing a request. The loaded procedure uses relevant conversation inputs or asks for missing information even if its hint suggests arguments.

Expose an authenticated pod metadata endpoint and a team/managed-instance-scoped product endpoint that resolves only that instance's configured runtime source. Use existing team-use authorization, workload credentials and runtime URL construction. Return names/descriptions, optional advisory argument hints and a snapshot revision/support marker, not bodies or host paths. Fetch this catalog on selected-agent changes rather than adding a lookup to every normal model call. Older/non-supporting runtimes return unavailable metadata; the composer disables skill submission, and ordinary chat remains usable.

For ReAct, after managed authorization and before the first model call, resolve an explicit name against the current snapshot and run the same loading service with trusted `origin=user`. Feed the resolved instructions into the normal checkpoint/message flow as a marked skill-instruction message alongside the user's request. The message states that the runtime already loaded the complete procedure; shared catalog/tool guidance asks the model to use available instructions directly and load only when they are absent from context. This also applies to retained tool results and does not prohibit reloading after trimming. It is not a synthetic model tool call. Unknown/unavailable selections fail before inference; frontend cache freshness is not authoritative. HITL/interruption resumption must not repeat this preload or duplicate its attribution.

For Deep, retain the name-only selection and canonical invocation text without resolving the body from the snapshot or invoking preload_skill. Upstream discovery presents metadata, and the model loads instructions/references with native read_file. A user selection does not guarantee a load before inference; actual reads use user origin when the skill name matches the current typed user selection, otherwise agent origin. Disabled skills and Graph selection remain unsupported.

Alternative: expand `SKILL.md` in the browser like prompt text. Rejected because the serving pod owns the files, the browser could forge the body and frontend substitution would not share the automatic loading path.

### 5. Reserve `/skill` and reuse composer interaction

The canonical draft is `/name`, retained at its actual position in the user's plain text. The root slash menu lists runtime skills beside inline prompt commands; direct prefixes filter skills at the caret before, after or within existing text. Completion replaces only the active query range, appends or reuses a space, restores the caret and never sends. Exact catalog names followed by whitespace are recognized on typing and paste. Undelimited prefixes remain editable, but a bare exact name is valid on submit. Unknown names and URL/path fragments stay plain text. A complete slash-name followed by whitespace imports a skill even for homonyms; explicitly selecting the prompt row preserves prompt dispatch.

The chat opts into a CodeMirror plain-text surface using existing frontend dependencies. Replace decorations render the selected invocation as the existing platform icon and full name (without a visible slash); the underlying document always contains `/name`, so selection-copy, cut, paste, undo and line layout share one state owner. The decoration is not atomic: editing one name character removes recognition. Ordinary RichInputField consumers retain their native textarea. The token scrolls and wraps with the text; an empty request shows the advisory argument hint without inserting it into the document. No request-position schema is added.

Submit sends the entire canonical text plus an ordered collection of name-only skill descriptors. Historical singular descriptors remain readable. Sent and reopened attributed user messages render the token at its stored position; old request-only turns gain a leading canonical token, and historical `/skill name` sentinels normalize for copy/edit. Unattributed messages remain ordinary text. Current catalog metadata is required for draft import; User-message extras.skill_invocations stores the name-only selections (with legacy singular compatibility) for history badges independently of loading; legacy ReAct user-origin loads remain a fallback. Deep does not fabricate load attribution from a selection. Preview stays read-only and completion/paste never invokes a provider. Typed legacy `/skill name` remains a compatibility submit path; all new completions and copies use `/name`.

The legacy `/skill` dispatcher remains reserved for compatibility. Reserve the exact prompt command `skill` in create/update/import assignment and surface a localized reserved-name error. Existing homonyms remain readable/editable through the library, are omitted from command suggestions and can be renamed through the normal prompt editor. Updates preserving an existing legacy command may retain it until renamed; new assignment/import must reject it. No automatic database rename or new schema is required. `/skill` takes precedence even when a legacy homonym exists; other prompt commands and old history remain unchanged.

### 5b. Restore personal and team prompt commands for ReAct

The developer requests only prompts carrying a `/name` command, not every library entry. Current slash resolution already lists the chat team's commands; the missing source is the caller's personal command library. Use the existing managed template `category`, derived from the runtime's `ExecutionCategory`, joined through the current instance's `template_id`, to enable this addition only when the resolved category is `react`. Unknown/loading categories and non-ReAct agents retain the current menu; do not infer category from titles, inheritance or skill support. No new API field is needed.

Reuse the generated uncapped `prompt-commands` query once for the chat team and, for ReAct team chats, once for the personal team resolved by bootstrap. A personal chat queries one library only. Read `currentData` for scope-sensitive results; skip unavailable personal identity rather than guessing an owning team. Keep server membership/personal isolation checks and `/skill` reservation unchanged. Do not combine libraries server-side or fetch all prompt bodies.

Represent a menu entry's kind and owning prompt team explicitly in the composer. Display platform skills, personal prompt commands and team prompt commands with visible and accessible source labels. Keep a prompt's source plus id through prefetch, menu completion and subsequent submission; a command string alone is insufficient when two libraries have the same command. An explicit row always dispatches that exact prompt. For a typed prompt command without an explicit row, preserve the chat team's precedence and use the personal command only if absent there. Preserve the existing complete-delimited-skill precedence; an explicitly selected prompt homonym remains a prompt. Team/instance/source changes invalidate choices and stale async completions. Retain a completed invalidated prompt choice as unavailable until the command is edited or reselected, rather than reinterpreting it as a typed homonym. An unselected personal fallback requires a resolved team catalog to establish absence there; explicitly selected personal prompts do not wait for that catalog.

Skills continue to complete their canonical invocation without sending, then submit name-only runtime selections. The collection and prompt composition decisions below extend the original singular wire field and ReAct preload. Prompts continue to fetch their full text from the owning team's existing detail route and submit text plus the existing `TurnCommand`, preserving trailing text and exact `prompt_id` in history. Neither path converts the other kind into a tool or skill. No new runtime loader, middleware, persistence schema or abstraction is required. Keep the side-panel library import flow unchanged.

### 5c. Preserve multiple explicit skills and an inline prompt

Use `RuntimeContext.skills` for ordered name-only selections. Keep legacy `skill` input readable at one normalization boundary; reject simultaneous singular and plural input rather than silently dropping either. Deduplicate names in first-occurrence order. Keep each original invocation occurrence in the canonical text and decorate every occurrence independently. No client body/path, skill execution ordering, extra tools or middleware are introduced.

The developer's 2026-10-09 correction requires both selection orders for every available prompt: prompt then skills, or skills then prompt. Reuse the inline completion/resolution path across managed execution families. `includePersonalCommands` controls the additional ReAct library only; it must not gate placement or decoration of commands already in the current library. Deep native loading and scope/ownership rules remain intact.

The composer must keep an inline prompt choice's owning team/id independently from selected skill ranges. Completing another skill edits only the active command range, preserving all previous choices and request text. Prompt homonyms explicitly selected from the menu remain prompts at that range; existing typed skill precedence applies elsewhere. Scope invalidation and stale async guards remain. CodeMirror stores choice kind/owner with native undo effects; restoring text also restores identity, without a parallel draft history. Delimiter-based recognition is recorded immediately, so a pending catalog refresh cannot silently drop a selected skill. At submission, resolve the single inline prompt using the existing authorized detail route, preserve surrounding canonical request text on its respective side, and send its existing `TurnCommand` together with all skill selections. A failed prompt resolution must send neither a prompt nor a skills-only fallback.

Admission validates every fresh ReAct selection before inference; the existing loader then supplies all distinct procedures through normal checkpoint messages, with separate load ids/events/KPI. Resume must not repeat preload. Deep continues to receive canonical user text and native upstream skills configuration without Fred preload: an actual native read of any currently selected name receives user origin, including child reads; other reads retain agent origin.

Persist the collection in user-message `metadata.extras.skill_invocations`. Optimistic history, reopen, copy/edit, restart and same-exchange HITL restore all names; new turns do not inherit them. Read legacy singular metadata and existing legacy ReAct attribution without inventing selections from arbitrary historic text. Prompt and skill presentation must coexist in mixed turns. `command.draft_text` and `draft_command_offset` preserve surrounding text and distinguish the selected prompt occurrence from skill homonyms for history/copy/edit; neither affects model instructions. Regenerate runtime OpenAPI and frontend clients from source; no database migration is needed.

### 5a. Preview skill instructions in the existing right-hand panel

Keep the inline label visually discreet, complete and free of removal controls.
Make its icon/name one keyboard-accessible button wherever explicit selection is
shown: the composer and sent or reopened user turns. Clicking only opens a
preview; it does not dispatch a turn, load the skill into model context, change
the draft or select a different skill. Editing one invocation character removes recognition. Skill completion replaces only the active slash range and preserves its position and surrounding text. The plain-text editor lays out the decorated name with the request and scrolls it normally; sent inline labels derive their baseline from the name, independently of the icon. Visible badges omit the slash. CodeMirror copies the underlying slash invocation; the existing delegated message-list copy handler restores the slash for complete selected skill labels within one attributed user bubble. Partial names and cross-turn selections retain native copy behavior. The existing file-paste listener owns file-preferring clipboard data in capture phase before the editor, preserving selected draft text when attaching screenshots.

Use `ChatSidePanel` and the existing exclusive `activePushDrawer` slot. A
presentational skill-detail panel has a large neutral `Skill: <name>` header
without an icon, `Description:` followed by its text, optional argument hint,
then a divider and Markdown instructions using the shared sanitized renderer
and design tokens, without a redundant content heading. Activating the same
skill toggles the preview closed; another skill replaces it. The empty composer
request uses the selected metadata argument hint as its placeholder, falling
back to the generic optional-request prompt when the hint is absent. Display
metadata separately rather than as raw YAML.
Show loading, unavailable/error and retry states without stale instructions.
Closing, Escape and keyboard interaction follow the existing panel conventions.
Local reference links remain readable file labels rather than navigating to
unrelated application routes. Successful `read_skill_file` trace steps also open
the returned reference text as described below.

Add a separate typed `SkillDetail` in fred-sdk containing `skill: SkillSummary`,
`revision` and `content` (the complete bounded startup-snapshot `SKILL.md`).
`GET /agents/skills/{skill_name}?agent_instance_id=...&team_id=...` reuses catalog
caller authorization, managed-instance resolution and source isolation before
reading the selected validated name. It reads the immutable snapshot in memory,
accepts no file path and performs no inference or filesystem scan. The product
proxy is `GET /control-plane/v1/teams/{team_id}/agent-instances/{agent_instance_id}/skills/{skill_name}`,
under the same team-use authorization and selected runtime source. Keep the
existing catalog schema and metadata-only behavior intact. Unknown/missing or
unsupported resources yield a clear unavailable response; no alternative runtime
is queried. No new storage, permissions, configuration or third-party dependency
is introduced. Regenerate both OpenAPI clients from source contracts.

Frontend request identity includes team, instance and skill name; only fetch on
preview and refresh when opened so runtime restarts are reflected. A late result
from a different skill, team or instance cannot replace the visible selection.
Clear the panel on relevant conversation/agent changes using the existing drawer
lifecycle. Preview reads the current runtime snapshot even for historical
messages: stored attribution does not retain the original skill body. Per the
developer’s presentation refinement, no runtime-version label is exposed in
the user UI. Do not imply reconstruction of previously loaded instructions.
Preview remains available independently of a turn's send/stream state.

### 6. Preserve messages and add truthful load attribution

Persist loaded instruction/reference text through the existing conversation checkpoint path. Keep normal history limits and allow reloading after input trimming; do not introduce an active-skill field, permanent mode, task-completion detector or blanket reinjection of every previously loaded body. Guidance ties procedural use to the current request, allowing clarifications and combinations while unrelated requests can use other skills.

Add a small typed load-attribution envelope containing skill name, snapshot/content identity, invocation origin and existing exchange/agent identifiers. Carry it through the common runtime event/history projection. Automatic loads remain real tool calls; ReAct explicit preload produces a genuine runtime load step without claiming the model emitted a call. The frontend renders one compact step, localizes the user/agent origin, attributes child loads through the existing child context and rehydrates history without reading the current skill file. Use existing event identifiers to avoid duplicate steps during replay/resume.

### 7. Validate with the `compte-rendu` workflow

All bundled skill instructions and resources are written in English; generated answers follow the requested language. Preserve the existing `compte-rendu` identifier and reference path. The skill reads provided notes and the relative Markdown link to `references/modele-compte-rendu.md`, then identifies decisions, actions, owners and deadlines. Missing facts are explicitly unspecified. A document-reading agent exercises the workflow with an attachment; an agent without the required reader explains the missing input. Use deterministic model/tool doubles for offline orchestration assertions and a manual web check for actual model selection and useful output; Markdown instruction following is not a deterministic executable pipeline. Bundle focused research, summary, comparison and verification workflows for quality/reliability; each handles absent input without fabrication. Skill files link references and state when to read them; runtime-specific guidance maps those links to ReAct `read_skill_file(name, path)` or Deep native `read_file` under `/skills/<name>/`, instead of duplicating tool signatures in each skill.

### 8. Preview the reference actually read

Recognize the platform `read_skill_file` call through the existing trace utility
boundary and localize its label in both languages. For a completed successful
call, resolve the skill name and relative path from its validated tool arguments
and the text from its stored tool result. Route activation through the managed
page's existing exclusive push-panel state, replacing any skill preview or other
push panel. Reuse `ChatSidePanel` and sanitized Markdown rendering, with a clear
file title and skill attribution; show plain text safely when appropriate.

Store the trace entry's stable identity and resolve it from live conversation
messages, rather than retaining an unrelated result after conversation changes.
The reference preview reads the actual result already delivered to the model,
including after reopening history. It neither fetches a new current-snapshot
file nor calls a model/tool. Pending, failed or unavailable results keep their
existing trace-detail/error behavior. Do not introduce a file-path API or make
Markdown reference links fetch arbitrary paths. Activating the same file again
closes its preview; another file or the skill name replaces it.

### 9. Count successful loads and expose one scoped usage preset

Emit `agent.skill_loaded_total` once at the shared successful loader boundary,
used by ReAct explicit preload and automatic parent/child tools. Pass the existing
bound KPI writer/context through those callers. Use trusted `skill_name` and
`skill_origin` (`user` or `agent`) dimensions plus existing team/session/exchange
and managed-instance attribution. A child choice belongs in the model column;
its parent's forwarded status must not emit another count. Emit after successful
content resolution, never from trace rendering, preview reads or status replay.
Resume without a new load does not count; an actual repeated successful load
does count. Reusing retained instructions on later messages without a load is
not observable as a new invocation and is not counted.

Use the existing queue/fail-open KPI path: no new direct OpenSearch request,
filesystem read or await in the loader. Do not record instructions, requests or
reference text in KPI dimensions. Add keyword mappings for `skill_name` and
`skill_origin`; current `ensure_ready()` already repairs additive mappings via
`ensure_index_mapping`, so no separate mapping-repair implementation is needed.
Keep the Prometheus allow-list unchanged; this feature's per-skill breakdown
uses the structured KPI store.

Register `skill_usage` and self-scoped `user_skill_usage` presets sharing one aggregation with a typed response containing skill name,
user count, model count and total for the requested UTC interval. Aggregate
successful-load events by skill and origin in one OpenSearch query, applying
`dims.team_id` when requested. Reuse the preset router's `KpiScope` authorization:
team `can_read_members`, platform `can_observe_platform`. Personal queries filter
`dims.user_id` from the authenticated user, with no caller-supplied user ID or
team filter, like existing personal usage presets. Return the top 100 names
by total with deterministic tie order, zero for an absent origin and an explicit
truncation indicator if more names exist. Historical names remain visible even
if removed from the current catalog. No backfill from conversation history.

Regenerate the control-plane client and add its short hook alias. Reuse the
existing table, card/section, date selector and number-formatting primitives in
a shared skill-usage presentation in one subsection matching the selected
space: personal counts only in personal `TeamUsagePage`, team counts only in
collaborative `TeamUsagePage`, and platform counts in
`AnalyticsPage`. Columns are Skill / User / Model / Total, sortable by each
count. Use existing team visibility/query-skip rules and five-minute cache policy;
preserve loading, empty, error and refresh behavior. State that counts are
successful loads and that data starts when instrumentation is deployed.

## Risks / Trade-offs

- Retained instructions may influence an unrelated request → scope guidance and explicit reloading, with no promise of perfect model adherence or unlimited context retention.
- A restart can leave old body messages beside a new catalog → keep historical content intact, refresh metadata and attach the new content identity to each new load.
- Startup snapshots consume memory → bounded per-file and aggregate bytes; a few dozen skills, no per-model-call I/O. Size defaults must fit Fred's existing input budgets and be documented/tested.
- A rolling deployment can temporarily serve different snapshots → the serving pod resolves names against its current snapshot; all replicas should deploy the same files. The menu revision is informational, not a version pin: a still-valid name loads the serving pod's version, and an unavailable ReAct name fails before inference. Deep delegates availability and loading to native discovery/model reads. Each load records the version actually used.
- Prefix reservation changes a valid legacy command → explicit developer approval, editable legacy prompts and a migration note; test create/update/import and composer together.
- Default upstream text/state semantics differ from Fred → disable default append, use public upstream surfaces, and test restored checkpoints and prompt-tag boundaries.

## Migration Plan

1. Record the confirmed scope extension against #2711 and publish an English migration note. Inventory and rename legacy prompt commands named `skill` before rolling out the reserved dispatcher; prompts remain available in the library meanwhile.
2. Deliver additive SDK/runtime/product contracts and generated clients before enabling the web entry. Deploy the same validated directory to all participating ReAct/Deep pods and advertise support only where installed/configured.
3. Package the skills with `fred-runtime`, then update `apps/fred-agents` configuration examples, chart values/templates and generated schemas together for optional read-only activation. Verify images consume the runtime package resources without an application-owned copy; do not require operator edits to private overlays or introduce tables.
4. Restart pods to publish the new snapshot; validate explicit and automatic `compte-rendu` use, child loading, history rehydration and disabled/unavailable states in web chat.
5. Roll back by removing directory activation and restoring the previous web/backend deployment together. Retain historical skill messages/attribution; do not erase conversations or silently rename prompt commands.
