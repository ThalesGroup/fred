---
schema: 1
title: "Enable shared platform skills for managed ReAct and Deep agents"
impact: minor
configuration: production
configuration_reason: "Optional skills.directory selects packaged resources or a read-only project directory; chart defaults remain disabled."
---

## Applicability

Fred deployments upgrading the runtime, control plane and frontend together.
Without skills configuration, agents no longer receive the former automatically
injected Mermaid syntax rules. Mermaid rendering remains available in chat.
The `/skill` composer command is reserved on every deployment.

## Prerequisites

Use matching runtime/SDK/control-plane/frontend versions. For a project directory,
provide UTF-8 SKILL.md procedures with name/description YAML metadata and bounded
text references. Every replica must receive the same resources.

## Configuration

Optional activation: set `applications.fred-agents.configuration.skills.directory: package`
in chart values to use the English-written quality/reliability skills shipped
inside fred-runtime: `compte-rendu` (meeting minutes), `grounded-research`,
`summarize-document`, `compare-options`, `verify-answer` and `mermaid` (diagrams). Responses follow
the requested language.
For custom skills, mount a trusted directory read-only and use its absolute pod
path. Relative paths resolve against the configuration file parent. Omit skills
(or leave chart `skills: null`) to disable. No IAM grants or secrets are added.
Application development configuration examples explicitly enable `package`.
For a custom directory, include a `mermaid/SKILL.md` if its diagram guidance is
needed; the removed SDK resource is no longer an automatic fallback.

## Upgrade

Deploy the control plane, runtime and frontend with the normal procedure. Older
runtime catalog routes are shown as unsupported during a rolling upgrade.
To activate or change resources, drain active turns and restart all relevant
agent pod replicas. Avoid mixed snapshots: use identical config/resources on
all replicas before resuming traffic. Invalid entries are omitted with diagnostic
folder names. Existing checkpoints retain loaded procedure messages; the advertised
catalog and new loads use the current snapshot on their next turn, without
resetting conversations. Native Deep discovery metadata keeps its upstream per-thread cache. Deep reads
the physical configured folder through FilesystemBackend and native `skills=`;
web metadata, previews and ReAct explicit preload still use the startup snapshot.
Native file edits may become visible before restart. Keep all replicas on the
same read-only files and restart after deployment to refresh the web catalog.

Existing prompts using command `skill` remain library-readable and editable but
lose that slash shortcut. Rename the command to restore it; new assignments,
imports and promotions with `skill` return a reserved-command conflict.

## ReAct personal and team prompt commands (2026-10-09)

The frontend additionally offers commanded personal prompts alongside the chat
team's commands and platform skills for ReAct templates. It uses the existing
runtime-derived template category and authorized prompt routes; no operator
configuration or schema migration is required. Personal chats list one prompt
library; Deep and other execution families keep their current prompt sources.
Verify the three source labels in a ReAct team chat and select each of two
homonymous personal/team commands: the exact selected prompt text must run.
Without an explicit row, a typed prompt command prefers the chat team's match.
Prompt/skill homonyms remain independently selectable; `/skill` stays reserved.
Prompts share the platform skills' two-line menu layout, with a distinct icon
in a blue tile. Completed prompt commands use an inline blue icon/name;
hover reveals their title, source and description. Verify completion,
copying `/command`, editing and undo preserve the selected prompt's identity.

## Multiple selections and inline prompts

Deploy the regenerated runtime API client with the runtime/SDK update, then
restart the agent pods. New turns use name-only `runtime_context.skills`; legacy
singular input/history stays supported, while supplying both forms is rejected.
No SQL migration or new skill middleware is required. ReAct loads all selected
skills before inference; Deep retains native progressive loading.

Verify two different skills, repeated skill names, independent deletion and copy,
one personal or team prompt with both skills, and text before/after each token.
Reopen history and resume the same interrupted exchange; all selections must
remain. A fresh turn must not inherit them. Invalid ReAct selections fail the
whole request. Available prompt commands complete inline before or after skills
in every managed execution family; only ReAct adds a separate personal library
to team chats. Check keyboard and click completion in both themes, and verify
the blue prompt icon/name in both the draft and reopened history.

## Validation

Select a managed ReAct or Deep instance. Verify its `/skill` menu lists only its
runtime catalog and displays advisory `argument-hint` values when supplied.
Typing `/` also lists the skills directly; a prefix such as `/comp` filters their
names. Selecting one attaches it without sending or replacing existing notes.
There is no standalone `/skill` menu row; the typed command remains compatible.
Skills have a dedicated platform pictogram and an origin hint. Hover the selected
or sent name to see its current catalog description when available.
Send `/skill compte-rendu` alone and verify the agent uses existing meeting
notes or asks for them. Hints never block submission. Then send the command plus notes containing a decision and
an action without a deadline: ReAct preloads the selected instructions and emits
a user-origin load step before inference. Deep receives the native catalog and
user request; only an actual successful instruction read emits a load step.
Check that absent fields remain unspecified in the requested language, and
record any model-following limitation rather than equating selection with loading. On an ordinary relevant request the
model can load the same skill automatically. Check that the
loaded context identifies the skill as procedural instructions, not a function,
and its hint as user-input guidance rather than tool parameters. Verify the agent
reads references through `read_skill_file` (ReAct) or `read_file` on the mounted
`/skills/<name>/` paths (Deep), rather than inventing a skill-named tool.
Deep mounts the physical configured folder at `/skills/`, preserving its
physical subdirectories. Use well-formed skills with matching folder/frontmatter
names; native discovery and file types are governed by DeepAgents. Deep no longer registers Fred
`load_skill` or `read_skill_file`; ReAct retains both. Explicit ReAct selections
still preload internally before inference. Deep selections stay ordinary user
text: native discovery and model-driven `read_file` calls load the instructions,
without Fred preload or snapshot body validation. Deep selection alone emits no
load event/KPI. Actual native instruction reads use user origin for the current
any explicitly selected name and agent origin for other skills, including child
reads. This records who requested the skill; read_file is still model-driven. Name-only
selection metadata preserves the badge and preview in reopened Deep history
without implying that the skill was loaded. Existing preloaded messages in old
conversation checkpoints are not removed; use a new conversation to inspect the
native path after restarting the runtime. The mount supports listing
and searching. Parent/child permissions and capability ports deny writes, including
at `/skills`; the deployed folder must be read-only on disk. The production image
protects its packaged runtime source tree with root ownership and read-only modes;
external skill mounts must provide equivalent read-only access. Native discovery
warnings omit file contents, including malformed YAML source text. The upstream backend
is used directly and script execution stays unavailable. Deep native reads see
current disk files; restart remains required to refresh web and ReAct snapshots.
Native reads of `SKILL.md` from offset zero count actual skill use, with user
origin for the current selected name and agent origin otherwise;
reference/pagination reads do not. Click a native reference trace row to inspect
its returned excerpt in the shared panel.
Reopen the chat and check the
compact origin step and the inline skill name in the user message remain.
The composer shows the full selected name inline with the request, without a
removal button; editing an invocation character removes its recognition without
deleting surrounding text. Removing only request text preserves an intact selected
skill, including when a prompt has the same name. Verify unknown ReAct selection fails before inference
and unavailable tools are explained without fabricated results.
Click the inline name in the composer and a stored user message: the right-hand
panel shows metadata and formatted instructions, leaving the request unchanged
and making no model call. Clicking the same skill again closes the panel. The
empty request uses the skill’s optional argument hint as a placeholder. Runtime
version details remain internal; reopened messages preview current instructions. Deploy matching
runtime, control-plane and frontend versions for the detail route; an older runtime
shows an unavailable preview while ordinary chat remains usable.

## Skill usage analytics (2026-10-07)

Deploy matching runtime, control-plane and frontend versions and restart serving
processes. The existing additive KPI index repair installs `skill_name` and
`skill_origin` keyword dimensions on startup; no SQL migration is needed.
Counts begin with instrumentation deployment; old conversations are not backfilled.
If skill events were already recorded before the mapping upgrade, their fields
can exist in `_source` while remaining unsearchable (`dynamic: false`). After
startup mapping repair, reindex only those existing events in place using
`POST <configured-kpi-index>/_update_by_query?refresh=true` with the body:

```json
{ "query": { "term": { "metric.name": "agent.skill_loaded_total" } } }
```

This preserves recorded names, origins, owners and timestamps, without reading
conversation history or creating additional load events. Verify the response
has no failures/version conflicts and that scoped skill totals match recorded
loads. This one-time operation is unnecessary if instrumentation and mappings
were deployed together.
Verify user-selected and model-selected successful loads in the selected team/date
range, in platform analytics and in the personal usage subsection. Personal
counts use the authenticated conversation owner across all teams. Each space
shows one matching skill subsection: personal, selected team or platform. Team
space must not also show the personal skill subsection. The
user/model columns identify who selected the skill. Reopening history, reference reads and HITL resume
must not increase counts. Actual reloads count again. Existing queue/storage loss
behavior makes these operational analytics best-effort.

Click a successful reference row: the same right panel must show the stored file,
retain its width, and close on a second activation without changing the draft.

## Rollback

Disable `skills`, then drain/restart the pods to remove the catalog and loading
tools. Use normal application rollback for a full revert; no database migration
is introduced. Disabling does not erase already-loaded checkpoint context or
stored history. Start a fresh conversation if older instructions must be excluded.

## Limitations

V1 supports a few dozen shared procedures and confined text references. Web/ReAct resources
refresh at restart while Deep native reads use current disk contents; skills do not install tools, execute scripts, or grant
permissions. Selection/following by the model is probabilistic. Graph agents and
a dedicated terminal CLI are outside this feature.
