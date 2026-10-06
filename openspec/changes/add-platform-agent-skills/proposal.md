## Why

Fred agents cannot currently discover or load platform-owned `SKILL.md` workflows, and users cannot invoke them from managed web chat. Provide one shared implementation for ReAct, DeepAgent and Deep children, reusing the installed DeepAgents skills middleware.

Tracking: [#2711](https://github.com/ThalesGroup/fred/issues/2711). The developer-confirmed scope extends that issue's original ReAct-only, model-facing slice to DeepAgent and explicit web invocation. Its prompt-layering and confined-read requirements remain applicable.

## What Changes

- Store platform-distributed skills and their references under `libs/fred-runtime/fred_runtime/skills/` and include them as `fred-runtime` package data. Discover them from the configured read-only directory in agent pods. Publish a validated startup snapshot; additions and edits take effect after pod restart. Design for a few dozen skills.
- Put each valid skill's name and description inside the system prompt's existing `<tools>` block. Every ReAct agent, DeepAgent and Deep child in a deployment with this directory configured can use the same catalog, without per-agent selection.
- Provide shared tools to load a skill and read its UTF-8 reference files. Reuse DeepAgents `SkillsMiddleware` discovery and state handling, with Fred-specific prompt placement and narrow file access; do not install a general filesystem or shell on ReAct agents.
- Add autocompleted `/skill <name> <request>` invocation to the web composer. Resolve the selected skill on the server and load it before the first model call.
- **BREAKING:** reserve the `skill` composer command for platform skill dispatch. Refuse new prompt commands named `skill`; existing homonyms remain available in the prompt library and must be renamed to restore command invocation. Other prompt commands remain unchanged. This compatibility choice was explicitly confirmed by the developer.
- Allow automatic selection, multiple skills per request and normal tool-loop iteration. Retain loaded instructions in conversation history under the existing history-budget rules; apply them according to the current request, without a persistent active-skill mode.
- Show a compact skill-load step with the name and user/agent origin. Skip invalid skills with diagnostics, reject unavailable explicit invocations clearly, and explain unavailable tool-dependent steps while completing the feasible work.
- Ship `compte-rendu` and a reference template as the first platform skill and end-to-end acceptance example.

## Capabilities

### New Capabilities

- `platform-agent-skills`: deployment-owned skill discovery, confined reads, shared agent loading, web invocation, contextual continuity and load visibility.

### Modified Capabilities

None of the current durable specs is modified. The new capability owns the reserved platform dispatcher; update the existing prompt contract and help to explain its effect on prompt commands. The active prompt-command changes remain the source for their existing requirements.

## Impact

- `libs/fred-runtime`: packaged `fred_runtime/skills/` instructions/references, package-data distribution, pod configuration/bootstrap, a shared skill catalog/backend and loading tools, ReAct/Deep middleware assembly, authenticated catalog access, execution/history attribution and offline tests.
- `libs/fred-sdk`: additive typed catalog, invocation and load-attribution contracts where required by the existing runtime interfaces.
- `apps/control-plane-backend`: resolve catalog metadata through the configured runtime source for the selected managed agent, using the existing routing and team authorization boundary; enforce the reserved prompt command in create/update/import paths. No skill files or skill CRUD storage here.
- `apps/frontend`: generated API clients, composer command hook/menu, managed execution payload and compact activity rendering; English/French help and labels.
- `apps/fred-agents`, deployment chart values/schemas and images: consume the skills distributed by `fred-runtime` and configure optional read-only activation; do not own or duplicate the skill files. No new third-party dependency or database migration is planned.
- Existing runtime/product contracts, prompt assembly guidance, web usage guidance and an English operator migration note describing optional activation and renaming any legacy `skill` prompt command.

## Non-Goals

User/team-authored skills, uploads or skill editing, script execution, automatic permission/tool provisioning, persistent skill modes, dedicated CLI commands, Graph-agent integration, catalog search infrastructure and isolated skill sub-agents.
