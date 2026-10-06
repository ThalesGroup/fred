## Context

See `proposal.md` for motivation and the confirmed extension of #2711. The relevant existing seams are:

- `react/middleware/frame.py` and `deep/deep_runtime.py` both assemble LangChain middleware. Deep currently passes no `skills=` to `create_deep_agent`; its children have an explicit middleware/tool configuration.
- The installed `deepagents.middleware.skills.SkillsMiddleware` parses and validates metadata through a `BackendProtocol`, caches it in agent state and supports disabling its default system-prompt append. It provides no loading tool. Its default prompt asks for general `read_file` and script execution, so it is unsuitable unchanged.
- `react/react_prompting.py:compose_system_prompt` owns the four-block assembly shared by both runtimes. Catalogs belong in `<tools>`; `escape_reserved_prompt_tags` is the existing content-boundary helper.
- `react/react_tool_resolution.py` normalizes common ReAct/Deep tools; `react/react_tool_binding.py`, `ToolObservabilityMiddleware` and the shared transport own tool traces/events. Existing checkpoint hygiene trims model input without rewriting persisted history.
- `useComposerCommands.ts` already supports `/`, prefix filtering, keyboard completion and prompt-command submission. `RuntimeContext.command`/`TurnCommand` is prompt attribution only, not a trusted skill-selection channel.
- Control-plane resolves managed instances to configured runtime sources. It must not read pod-local files or aggregate an unrelated pod's catalog. Prompt writes currently permit the name `skill`.

The active prompt-command changes explicitly excluded user-invocable platform skills. They remain historical scope statements; the developer has now approved this new feature and the reservation of `/skill`.

## Goals / Non-Goals

**Goals:** one pod-owned read-only source, one catalog/loading implementation shared by both agent engines and their native Deep children, and a typed web selection that deterministically loads before inference. Reuse upstream parsing and Fred's prompt, event, authorization and history seams.

**Non-Goals:** see `proposal.md`. In particular, this is platform middleware plus shared tools, not an agent-selected capability package; per-agent enablement and Graph integration are excluded. No new permission grant follows from loading a skill.

## Decisions

### 1. Build a bounded immutable snapshot at pod startup

Add optional skill-directory configuration to `AgentPodConfig` and carry a pod-lifetime catalog/service through `RuntimeConfig`/`RuntimeServices`. Store the platform-owned instruction files and references under `libs/fred-runtime/fred_runtime/skills/`, with the example in `skills/compte-rendu/`. This is package data, distinct from the Python middleware/service implementation. `apps/fred-agents` consumes the runtime package and does not own or duplicate these files.

Include all declared skill Markdown/reference files in the `fred-runtime` wheel and source distribution; the current `pyproject.toml` only explicitly declares migration templates as package data. Resolve the packaged directory from the installed runtime package, not a repository-relative path or the shell's working directory. Resolve other configured relative deployment paths against the project/configuration root. An enabled deployment can select the packaged directory through the optional configuration; installing the package alone does not activate skills. Image and volume deployments retain the same read-only snapshot contract. Verify discovery/reference reads from a built, installed distribution outside the checkout, since editable monorepo installs can hide omitted package data.

Enumerate only skill subdirectories and approved UTF-8 instruction/reference files. Canonicalize and confine paths before copying bytes into a bounded immutable backend implementing the required `BackendProtocol` read operations. Reject writes and exclude unreadable, oversized or escaping entries. Run the upstream public discovery hook against that backend once at bootstrap, reuse its validated `SkillMetadata`, and reject duplicate names instead of adopting upstream's last-wins merge. Publish the files and metadata together. No filesystem scans or blocking disk reads belong in model-call hooks.

A thin Fred `SkillsMiddleware` adapter uses that snapshot state, refreshes catalog metadata when a restored checkpoint belongs to a different pod-startup revision, and disables upstream's unwrapped prompt append. This reuses discovery/validation without copying the upstream parser or relying on its private helpers. Preserve the current dependency; compatibility tests cover the public hook and backend interface.

Alternative: a live `FilesystemBackend` on every turn. Rejected because file edits would affect bodies/references before the agreed restart and checkpoint metadata could become stale. Alternatives using a wiki, knowledge library or conversation workspace require ownership/lifecycle contracts outside this slice.

### 2. Keep catalog rendering within the existing prompt hierarchy

Render validated names/descriptions and short Fred loading guidance through the shared prompt composer into `<tools>`, before its closing tag. Use the existing reserved-tag escaping for metadata and for any skill text added to a model message. Do not add the default upstream skills section after `<agent_instructions>` or advertise an execution tool. Full bodies and references enter conversation messages only when loaded.

Build the catalog fragment once for the snapshot and reuse it in each compiled agent's system prompt. With no valid skills, omit the middleware/tools/fragment entirely and preserve the no-skills prompt bytes. Platform instructions retain precedence; skills describe procedures, not new authority.

### 3. Share narrow loading tools across the runtimes

Expose `load_skill(name)` and `read_skill_file(name, path)` from one shared service and tool factory. Arguments contain only the skill name and a skill-relative path; paths, snapshot revision, identity and origin come from bound server context. Return bounded UTF-8 content with skill attribution, and a clear error for unknown names or forbidden references. No writes, execution or arbitrary absolute-path reads are exposed.

Bind tools through the existing common runtime tool path and supply the same factory/middleware to the Deep parent and explicit child configuration. Check tool-name collisions before compilation and include the names in the effective tool set used by limits/HITL. Use existing traces, authorization checks, timers and history flow rather than a second tool runner. Deep retains its conversation filesystem independently; skills require no new composite filesystem mount or general ReAct filesystem access.

Metadata such as `allowed-tools` can be parsed for compatibility but must not be presented as enforced policy or used to provision tools. Runtime guidance tells the agent to use its actual tools, perform feasible independent steps and report missing inputs/actions.

### 4. Route explicit web selection as typed runtime input

Add an optional typed skill invocation to the runtime request/context contract, separate from prompt-only `TurnCommand`. The frontend sends the selected name and user's trailing request, not the skill body or a host path. A bare `/skill` offers suggestions; a named skill with no request asks the user to supply a request rather than starting an empty turn.

Expose an authenticated pod metadata endpoint and a team/managed-instance-scoped product endpoint that resolves only that instance's configured runtime source. Use existing team-use authorization, workload credentials and runtime URL construction. Return names/descriptions and a snapshot revision/support marker, not bodies or host paths. Fetch this catalog on selected-agent changes rather than adding a lookup to every normal model call. Older/non-supporting runtimes return unavailable metadata; the composer disables skill submission, and ordinary chat remains usable.

After managed authorization and before the first model call, resolve an explicit name against the current snapshot and run the same loading service with trusted `origin=user`. Feed the resolved instructions into the normal checkpoint/message flow as a marked skill-instruction message alongside the user's request. It is not a synthetic model tool call. Unknown/unavailable selections fail before inference; frontend cache freshness is not authoritative. HITL/interruption resumption must not repeat this preload or duplicate its attribution.

Alternative: expand `SKILL.md` in the browser like prompt text. Rejected because the serving pod owns the files, the browser could forge the body and frontend substitution would not share the automatic loading path.

### 5. Reserve `/skill` and reuse composer interaction

Extend `useComposerCommands`/`CommandMenu` with a skill-dispatch branch: `/skill` selects the skill section, the next token filters/completes names, and following text is the ordinary request. Preserve arrow-key navigation, Tab completion, Enter submission and Escape dismissal; keep the caret in the composer. Discard stale asynchronous catalog responses after agent/team switches.

The developer chose this syntax over collision-free `/skill:<name>`. Reserve the exact prompt command `skill` in create/update/import assignment and surface a localized reserved-name error. Existing homonyms remain readable/editable through the library, are omitted from command suggestions and can be renamed through the normal prompt editor. Updates preserving an existing legacy command may retain it until renamed; new assignment/import must reject it. No automatic database rename or new schema is required. `/skill` takes precedence even when a legacy homonym exists; other prompt commands and old history remain unchanged.

### 6. Preserve messages and add truthful load attribution

Persist loaded instruction/reference text through the existing conversation checkpoint path. Keep normal history limits and allow reloading after input trimming; do not introduce an active-skill field, permanent mode, task-completion detector or blanket reinjection of every previously loaded body. Guidance ties procedural use to the current request, allowing clarifications and combinations while unrelated requests can use other skills.

Add a small typed load-attribution envelope containing skill name, snapshot/content identity, invocation origin and existing exchange/agent identifiers. Carry it through the common runtime event/history projection. Automatic loads remain real tool calls; explicit preload produces a genuine runtime load step without claiming the model emitted a call. The frontend renders one compact step, localizes the user/agent origin, attributes child loads through the existing child context and rehydrates history without reading the current skill file. Use existing event identifiers to avoid duplicate steps during replay/resume.

### 7. Validate with the `compte-rendu` workflow

The skill reads provided notes and `references/modele-compte-rendu.md`, then identifies decisions, actions, owners and deadlines. Missing facts are explicitly unspecified. A document-reading agent exercises the workflow with an attachment; an agent without the required reader explains the missing input. Use deterministic model/tool doubles for offline orchestration assertions and a manual web check for actual model selection and useful output; Markdown instruction following is not a deterministic executable pipeline.

## Risks / Trade-offs

- Retained instructions may influence an unrelated request → scope guidance and explicit reloading, with no promise of perfect model adherence or unlimited context retention.
- A restart can leave old body messages beside a new catalog → keep historical content intact, refresh metadata and attach the new content identity to each new load.
- Startup snapshots consume memory → bounded per-file and aggregate bytes; a few dozen skills, no per-model-call I/O. Size defaults must fit Fred's existing input budgets and be documented/tested.
- A rolling deployment can temporarily serve different snapshots → the serving pod resolves names against its current snapshot; all replicas should deploy the same files. The menu revision is informational, not a version pin: a still-valid name loads the serving pod's version, and an unavailable name fails before inference. Each load records the version actually used.
- Prefix reservation changes a valid legacy command → explicit developer approval, editable legacy prompts and a migration note; test create/update/import and composer together.
- Default upstream text/state semantics differ from Fred → disable default append, use public upstream surfaces, and test restored checkpoints and prompt-tag boundaries.

## Migration Plan

1. Record the confirmed scope extension against #2711 and publish an English migration note. Inventory and rename legacy prompt commands named `skill` before rolling out the reserved dispatcher; prompts remain available in the library meanwhile.
2. Deliver additive SDK/runtime/product contracts and generated clients before enabling the web entry. Deploy the same validated directory to all participating ReAct/Deep pods and advertise support only where installed/configured.
3. Package the skills with `fred-runtime`, then update `apps/fred-agents` configuration examples, chart values/templates and generated schemas together for optional read-only activation. Verify images consume the runtime package resources without an application-owned copy; do not require operator edits to private overlays or introduce tables.
4. Restart pods to publish the new snapshot; validate explicit and automatic `compte-rendu` use, child loading, history rehydration and disabled/unavailable states in web chat.
5. Roll back by removing directory activation and restoring the previous web/backend deployment together. Retain historical skill messages/attribution; do not erase conversations or silently rename prompt commands.
