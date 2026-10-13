## Context

See proposal.md for motivation. Current state, read from the code:

- **One prompt per message, in the composer.** In `useComposerCommands.ts`,
  `promptChoice` is the first prompt choice (`matchedChoices.find`), the menu
  drops the two prompt sources once a prompt choice exists elsewhere
  (`!promptChoice || commandRange?.start === promptChoice.from`),
  `selectedPrompt` is one object, and `submit` resolves one range and hands it
  to `run`, which reads one prompt and sends
  `[before, text, after].filter(Boolean).join("\n\n")`. A second prompt name
  typed by hand stays in `after` and reaches the agent as the text `/name`.
- **One descriptor.** `run` builds one `TurnCommand` (`command`,
  `appended_text`, `prompt_id`, `prompt_name`, `draft_text`,
  `draft_command_offset`), declared in
  `libs/fred-sdk/fred_sdk/contracts/context.py` and carried as
  `RuntimeContext.command`.
- **The path of the descriptor does not cross the control plane.** The browser
  posts `RuntimeExecuteRequest` to the runtime pod; `to_legacy_context()` dumps
  the validated `RuntimeContext` (`model_dump(exclude_none=True)`); the three
  history write sites call `_turn_command(ctx)` (`agent_app.py`), which
  validates the dict as fred-core's `CommandDescriptor` and drops it whole when
  malformed; `make_user_text` puts it on `ChatMetadata.command`; the Postgres
  store writes it into `session_history.metadata_json`. History is read from
  the pod too (`GET /agents/sessions/{session_id}/messages`,
  `response_model=list[ChatMessage]`). `CONTROL-PLANE-PRODUCT-CONTRACT.md`
  says the control plane must not proxy or cache message content, and
  `apps/control-plane-backend/openapi.json` holds neither model.
- **The stored text is the sent text, unchanged.** `_write_turn_history`
  receives `request.message` and passes it to `make_user_text` as is.
- **Display.** `UserMessage` finds one prompt token in `draft_text` at
  `draft_command_offset`; `ManagedChatPage.openCommandPrompt` gives the panel
  the whole stored text under `prompt_name`, so for `/summary the report` the
  words "the report" appear under the prompt's name. `useComposerRecall` and
  `dismiss` restore one prompt choice. `useChatSse` copies
  `runtimeContext.command` onto the optimistic row. The first turn's title is
  `prompt_name` (or `/command`) plus `appended_text` (`useManagedChat.ts`).
- **Limits.** The runtime caps a message at `max_chat_input_chars` (default
  5000 code points); the client checks the assembled text of a command turn
  against it before sending. There is no cap on the number of skills in a
  message: `RuntimeContext.skills` is only de-duplicated by name, and
  `MAX_SKILLS = 64` bounds the pod's catalog, not a turn. No field of
  `TurnCommand` has a length limit.
- **Use counters.** Running a command does not call
  `POST /teams/{team_id}/prompts/{prompt_id}/use`. Its only callers are the
  copy action of the prompt view dialog and the prompt picker of the agent
  form; the control plane also counts the first attachment of a prompt to a
  conversation.
- **Error wording.** `runErrorStale` and `runErrorDetail` say "this command"
  and name nothing.

## Goals / Non-Goals

**Goals:**

- Several prompt commands in one message, with the single-prompt wire text and
  every stored conversation unchanged.
- One additive list on the descriptor, so that "the turn's own text is the
  record" still holds: the list points into the stored text, it copies none of
  it.
- Each layer correct on its own: the contract lands and is invisible until the
  client sends the list.

**Non-Goals:**

- Skill behaviour, skill precedence and the typed-name rules are not changed.
- No server-side resolution of prompts, no prompt versioning, no new endpoint.
- No change to the extra-field policy of existing models.
- No new CSS custom property and no new component: the badge, the token and
  the panel are the existing ones.

## Decisions

### 1. A new change, not an extension of `section-composer-command-menu`

That change is frontend only ("no API, data, configuration or migration
change"), is built (35 of its 37 tasks are ticked) and has its own
verification record. This one crosses fred-sdk, fred-core, fred-runtime and the frontend,
amends a frozen contract document and has a deployment order. Keeping them
apart keeps each proposal true and each task list binary. Both link issue
#3073 and ship in the same pull request, as the owner decided.

Alternative: extend the in-flight change. Rejected: its proposal, impact and
migration statements would all become false, and its ticked tasks would sit
next to a contract change that is not started.

### 2. The contract field

In `libs/fred-sdk/fred_sdk/contracts/context.py`:

```python
MAX_TURN_PROMPTS = 16

class TurnCommandPrompt(BaseModel):
    command: str = Field(min_length=1)
    prompt_id: Optional[str] = None
    prompt_name: Optional[str] = None
    draft_offset: int = Field(ge=0)
    text_offset: int = Field(ge=0)
    text_length: int = Field(ge=1)

class TurnCommand(BaseModel):
    ...  # the six existing fields, unchanged
    prompts: Optional[list[TurnCommandPrompt]] = Field(
        default=None, min_length=1, max_length=MAX_TURN_PROMPTS
    )
```

In `libs/fred-core/fred_core/history/history_schema.py`, the mirror, as
`CommandDescriptor` already mirrors `TurnCommand` (fred-core cannot import
fred-sdk):

```python
class CommandPromptDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")
    # same six fields and bounds

class CommandDescriptor(BaseModel):
    ...
    prompts: Optional[List[CommandPromptDescriptor]] = Field(
        default=None, min_length=1, max_length=16
    )
```

- One entry per prompt command **occurrence**, sorted by `draft_offset`.
- `draft_offset`: index of the `/` of the command in `draft_text`.
  `text_offset` and `text_length`: where that prompt's text sits in the turn's
  stored text. All three are JavaScript string indices (UTF-16 code units),
  like the existing `draft_command_offset`. The runtime only checks they are
  not negative: a Python `len()` counts code points and would disagree on any
  prompt holding an emoji.
- The single fields keep their meaning and describe the first entry:
  `command`, `prompt_id`, `prompt_name`, `draft_command_offset`.
  `appended_text` is the user's own text (every segment outside a prompt,
  joined by a blank line), which is what it already is for one prompt with
  text on both sides. `draft_text` is the typed line.
- New clients send `prompts` for every command turn, including a single
  prompt, so the panel fix applies to all new turns.
- Strings get no length bound, like their existing siblings: a rejected
  display field fails the whole turn with a 422, and the prompt name and
  command are already bounded where they are created.

**Why 16.** No per-message cap exists to copy (see Context). A bound is still
wanted for two reasons: the list is client-supplied JSON stored on every such
row, and each distinct prompt is one read on the control plane when the
message is sent. 16 is far above real use and far below what the 5000
character message limit would allow by itself. It is one constant per side;
changing it is a one-line edit plus the spec sentence.

Alternative: parallel arrays, or a list of full descriptors replacing the
single fields. Rejected: the first is easy to get out of step, the second
breaks every reader that exists today.

Alternative: store each prompt's text in its entry. Rejected: it duplicates
the turn's content in its metadata and gives two records of what was sent.

### 3. Extra-field policy on each hop

| Hop | Model | Policy | Effect for `prompts` |
| --- | --- | --- | --- |
| Browser to pod | `RuntimeExecuteRequest`, `RuntimeContext`, `TurnCommand` (fred-sdk) | pydantic default, unknown keys **ignored** | a pod whose fred-sdk predates the field drops it silently; no 422 |
| Request to internal context | `to_legacy_context()` dump | known fields only | carries `prompts` only when fred-sdk knows it |
| Internal context to turn | `_turn_command` validates `CommandDescriptor` (fred-core) | `extra="allow"` | new fred-core validates the list; a malformed descriptor is dropped whole and the turn is stored as plain text |
| Turn to store | `ChatMetadata` (`extra="allow"`) into `session_history.metadata_json` | JSON as written | no schema change |
| Store to read API | `ChatMetadata.model_validate`, then `response_model=list[ChatMessage]` | `extra="allow"` both ways | a pod with an older fred-core still serves a stored list; a list that fails validation resets that row's metadata to empty (existing fallback) |
| Pod to browser | generated `CommandDescriptor` type, which has an index signature | unknown keys kept | an older bundle ignores the list |

No model on the path is `extra="forbid"`. The statement in
`add-command-turn-rendering/design.md` that an older runtime "rejects [the
field] as unknown" does not match the code: it is ignored.

The policy of existing models is left as it is. Making `TurnCommand`
`extra="allow"` would let a future key pass through a pod that does not know
it, but it cannot help this rollout (old pods are already built) and it is a
separate contract decision.

### 4. Mixed versions and the safe order

The carrier is fred-sdk's `TurnCommand`: a pod stores the list only when its
fred-sdk declares it.

- **New frontend, older runtime pod** (fred-agents not yet upgraded, or an
  agent pod built on an older fred-runtime): the request is accepted, the agent
  receives the full assembled text of every prompt, and the answer is right.
  The live message shows every badge, because the optimistic row is built in
  the browser. The stored descriptor has only the single fields, so **after a
  reload** the message shows the first prompt as a badge and the others as the
  `/name` the user typed, its panel shows the whole sent text, and recalling it
  restores only the first prompt by id (the others are re-resolved by name,
  team first). Rows written in that window stay that way. Nothing errors and
  no text is lost.
- **Older frontend, new runtime pod**: nothing sends the list; nothing
  changes. An older bundle reading a row that has the list ignores it and
  renders the first prompt, as above.
- **Runtime rolled back after new rows were written**: `extra="allow"` on
  `ChatMetadata` and `CommandDescriptor` keeps serving the stored list.

Safe order: runtime pods first (fred-agents and every other pod built on
fred-runtime), then the frontend. The reverse order is safe for the agent and
for data; its only cost is the reload rendering described above, for the turns
sent in between.

### 5. No database migration

The descriptor is JSON inside `session_history.metadata_json`
(`libs/fred-core/fred_core/history/history_models.py`). No column, index or
Alembic revision changes.

### 6. Generated files and the commands

`TurnCommand` and `CommandDescriptor` are in the runtime OpenAPI only.
Regenerate, with direct commands (a `make` target would wipe the Vite dev
server in use):

```bash
cd libs/fred-runtime && .venv/bin/python scripts/generate_openapi.py
cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json
```

These are the two steps of `make update-runtime-api`. They rewrite
`libs/fred-runtime/openapi.json`, which is ignored by git like every
`openapi.json`, and `apps/frontend/src/slices/runtime/runtimeOpenApi.ts`,
which is the only generated file committed; neither is edited by hand. `controlPlaneOpenApi.ts` is not regenerated: the control plane exposes
neither model. CI's OpenAPI drift job runs for the runtime, control-plane and
knowledge-flow clients whenever fred-core changes, so the task list checks
that the other two specs come out unchanged.

### 7. Frozen contract documents

- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: section 8.98 introduced
  the descriptor. Section 8 is a dated changelog, so the change is a new entry,
  `### 8.112 Several prompt commands on a user turn (<date>)`, stating the
  field, the meaning of the single fields with several prompts, the offset
  unit, the cap, the ignore-and-degrade behaviour of an older pod and the
  order. 8.98 gets one pointing sentence, not a rewrite.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`: no entry. It does not
  re-export the history model: section 2.2 leaves runtime history messages and
  `RuntimeExecuteRequest` to fred-runtime, section 2.3 says the control plane
  must not own the history payloads, and it forbids proxying message content.

### 8. Frontend

- **One place assembles and one place reads.** Two pure functions join
  `utils/skillInvocation.ts`, which already rebuilds a line from a descriptor:
  one takes the typed line and the resolved prompts in order and returns the
  text to send with its `TurnCommand`; one takes a stored descriptor and its
  text and returns the list when it fits the turn (non-empty, sorted, slices
  inside the text and not overlapping, `/command` found at each
  `draft_offset`), or nothing. Everything that displays or recalls goes
  through the second, so the fallback to the single fields is one code path.
- **Wire text.** Segments of user text (trimmed) and prompt texts (trimmed),
  in order, empty ones dropped, joined by a blank line. For one prompt this is
  byte for byte what is sent today; a test pins it.
- **Hook** (`useComposerCommands.ts`). Prompt choices become a list:
  `selectedPrompt` becomes `selectedPrompts`, the remembered hand-typed token
  becomes a list, the menu filter loses the condition that hid prompts, and
  the menu stays closed on any rendered prompt token. `submit` collects every
  prompt range (picked ones by id and owning team, typed ones by name with the
  existing team-then-personal rule and pending-catalog guard), checks the cap,
  reads each distinct prompt once in parallel, then sends or reports the first
  failing command. `run`'s single-range signature goes away.
  `onResolveError` gains the command name.
- **Composer tokens** (`InlineSkillInput.tsx`, `RichInputField.tsx`).
  `promptToken` becomes `promptTokens`. Each widget carries its prompt
  identity and calls one stable page callback with it, so tokens are not
  rebuilt on a keystroke.
- **Sent message** (`UserMessage.tsx`, `CommandTurn.tsx`, `UserTurn.tsx`,
  `ConversationThread.tsx`). One prompt badge per usable entry; `CommandTurn`
  takes the command to show instead of reading the single field; the open
  callback carries the entry's index. The branches for turns without
  `draft_text` stay as they are.
- **Panel** (`ManagedChatPage.tsx`). For a usable entry the panel receives
  that entry's name, command and `text.slice(text_offset, text_offset +
  text_length)`. Without a usable list it receives the whole text, as today.
  `CommandPromptPanel` itself does not change.
- **Recall** (`useComposerRecall.ts`, `dismiss`). One restored prompt choice
  per usable entry; the recall identity includes the entries' ids and offsets.
- **Locales** (fr and en). `runErrorStale` and `runErrorDetail` take
  `{{command}}`; `runErrorTooMany` is added with `{{limit}}`. The cap is a
  constant next to the two helpers, with a comment naming the contract
  constant it mirrors.

### 9. Owner decisions

The owner confirmed the three defaults as written (2026-10-13). Each is one
requirement in the delta spec and one place in the code.

| Point | Decision | If the answer changes later |
| --- | --- | --- |
| (a) Same command twice in one message | allowed; each occurrence expands, the prompt is read once | refuse on submit: one check in `submit`, one locale key, replace the requirement "The same prompt command may appear more than once in a message" |
| (b) Which prompt names the conversation | the first one, then the user's own text, as today | change the title source in `useManagedChat.ts` (one expression) and the requirement "The first prompt command names the conversation" |
| (c) Usage counting | unchanged: running a command counts nothing today, and still counts nothing | call the existing `/use` mutation once per distinct prompt after a successful send: one task, and replace the requirement "Running prompt commands leaves prompt use counters unchanged" |

### 10. Relation to in-flight changes

`section-composer-command-menu` is archived first; this change adds
requirements to `platform-agent-skills` and modifies none, so its delta
validates today and applies cleanly afterwards. Three statements become
outdated and are superseded by the first requirement of this delta; they are
to be reworded when the surrounding requirement is next touched, not here:

- main spec, "Explicit skill selections compose within one turn", scenario
  "Combine an inline prompt with platform skills in either order" (one inline
  prompt);
- main spec, same requirement, scenario "Recall retains selected prompt and
  skill identities" ("selected prompt id and offset", singular);
- `add-command-turn-rendering`, "Opening a command turn SHALL show the text
  that was sent": still true for the stored text as the source, but the panel
  now shows one prompt's part of it.

### 11. Verification commands

Python, in each of `libs/fred-sdk`, `libs/fred-core`, `libs/fred-runtime`
(CI runs import order and type check as separate jobs):

```bash
VIRTUAL_ENV= .venv/bin/pytest -q -p no:cacheprovider -m "not integration" --disable-socket --allow-unix-socket
.venv/bin/ruff check .
.venv/bin/ruff check --select I .
.venv/bin/ruff format --check .
.venv/bin/basedpyright --baseline-file .baseline/basedpyright-baseline.json
```

Frontend, from `apps/frontend`, with Node from fnm on the `PATH`:

```bash
npx --no-install tsc --noEmit -p .
npx --no-install eslint <touched files>
npx --no-install prettier --check <touched files>
npx --no-install vitest run <touched test files>
```

Checks that are `make` targets elsewhere, as direct commands (`uv` is not on
the `PATH` here, so the project's own interpreter is used; all three were run for the contract
part, see verification.md):

```bash
# unchanged-spec check for the two other generated clients
cd apps/control-plane-backend && .venv/bin/python ../../scripts/generate_openapi.py control_plane_backend
cd apps/knowledge-flow-backend && .venv/bin/python ../../scripts/generate_openapi.py knowledge_flow_backend
# migration note check, from the repository root
apps/control-plane-backend/.venv/bin/python scripts/migration_guides.py check-pr --base origin/swift --worktree
```

### 12. Documentation, migration note, performance review

- `docs/swift/ux/COMPONENT-UX.md`, section `CommandMenu`: "A single prompt
  and several skills share the turn" and the panel sentence are rewritten.
- Help Center `features/commands.md`, fr and en: "You can place one prompt
  command and several platform skills" becomes several of each; the example
  shows two prompts; "A button on that message opens the text that was
  actually sent" becomes one label per command, each opening its own prompt
  text; the error and limit are mentioned in one sentence.
- Migration note: one note per pull request, so
  `docs/swift/ops/migrations/3073-composer-command-menu-sections.md` is
  updated, and its impact goes from `none` to `minor`.
  `MIGRATION-GUIDES.md` asks "a special deployment/restart order to follow?"
  and classes as `minor` an optional action needed "even just to enable the
  improvement" (its re-ingestion example). Here a recommended order exists,
  and an agent pod built on an older fred-runtime must be rebuilt to get the
  full rendering. `no_action_reason` is removed; Upgrade gives the order,
  Limitations gives the reload rendering of section 4. If the reviewer reads
  the degradation as too slight to count, `none` with the same Limitations
  text is the fallback; the decision is asked in the pull request.
- `fred-performance-reviewer`: required by CLAUDE.md, since the change is on
  the per-request path: `RuntimeContext` validation of every execute request
  (`TurnCommand`, `context.py` lines 405-418) and `_turn_command`
  (`agent_app.py` lines 2917-2932, called at 3801, 6247 and 6353, in the
  history write that runs after the stream). Expected finding: a bounded list
  of at most 16 small models, no I/O, no LLM or tool call site touched. On the
  client, the send now waits for up to 16 parallel prompt reads instead of
  one.

### 13. What building the contract part showed

- `agent_app.py` needed no change: `_turn_command` validates the whole
  descriptor, so the list is stored when valid and the descriptor is dropped
  when the list is not.
- The fred-core constant is `MAX_COMMAND_PROMPTS`, next to the model; fred-sdk
  has `MAX_TURN_PROMPTS`. A fred-runtime test holds them together.
- The list never reaches the agent: the `RuntimeContext` the pod rebuilds for
  the run does not copy `command`.
- The control-plane and knowledge-flow clients come out byte for byte the same
  after regeneration.

### 14. What building the frontend part showed

- The helpers are `assemblePromptTurn` and `usablePromptList` in
  `utils/skillInvocation.ts`, with the client cap `MAX_TURN_PROMPTS` next to
  them. The reader also refuses a list longer than the cap and one whose turn
  has no `draft_text`.
- `CommandTurn` keeps its `command` prop and accepts either the descriptor or
  one entry of its list (both have `command`), so no existing call or test
  changed. Its click no longer hands the mouse event to the opener.
- `onResolveError(reason, command)`: `reason` gains `tooMany`, whose `command`
  is the first one past the cap. The page builds the three toasts.
- Composer tokens: `InlineSkillInput` takes `promptTokens` and one
  `onOpenPrompt` callback; a token carries `promptId` and `promptTeamId`, and
  the widget hands the opener its identity (ids, name, command), never a
  position, since a widget outlives the edits made before it.
- The remembered hand-typed tokens are mapped through each edit at render
  time (common prefix and suffix of the previous and current draft), so a
  token left at the very end of the line survives text inserted before it.
- No existing case of `useComposerCommands.test.tsx` asserted that the menu
  hides prompts after a first one: the 121 cases pass with a rename
  (`selectedPrompt` to `selectedPrompts`), the command name added to seven
  error assertions and the list added to two exact descriptors.
- `useManagedChat.ts` needed no change: the limit already measures the text
  it is given and the title already reads the single fields, which describe
  the first prompt. `useChatSse.ts` and `toThreadMessages.ts` needed none
  either.

Divergences from the artifacts as first written:

- Delta spec, scenario "Team catalog still loading": it said "a picked team
  prompt". A team prompt cannot be resolved while the team catalog has not
  answered, so that message is held back on the team command first. The
  scenario now says "a picked personal prompt", which is the case the guard
  exists for; the rule itself is unchanged.
- A behaviour change that follows from the first requirement and is worth
  stating: a prompt name typed by hand next to a picked prompt used to be
  sent as the text `/name`; it now expands like any other typed prompt name.
- A typed name that is both a prompt and a skill, left undelimited at the very
  end of the line, is a prompt (the existing rule, now applied to each token).
  Before, with another prompt earlier in the line, it travelled as a skill.
- The read of `fred-performance-reviewer` that section 12 expected for the
  client is covered by a test, not by a run of the skill, which reviews the
  runtime: every read starts before any is awaited, one per distinct prompt.

## Risks / Trade-offs

- [Offsets are only right if the stored text is the sent text] → it is today
  (`request.message` is stored as is); a runtime test pins it, and the reader
  ignores a list that does not fit and falls back to the single fields.
- [The hook is dense: about 680 lines and 90 tests built on one prompt] → the
  assemble and read logic moves to two pure functions tested alone; the hook
  keeps the selection and menu state. Still the largest and riskiest part.
- [The pull request grows from frontend only (53 files) to three Python
  libraries and a frozen contract] → the contract lands as its own commits,
  before any frontend change; CI then also runs quality, tests and OpenAPI
  drift for every module depending on fred-core and fred-sdk.
- [Rows written through an older pod keep the degraded rendering for good] →
  stated in the migration note; avoided by the order.
- [A user can no longer see their own words in the panel] → intended; they
  are in the bubble.
- [Each distinct prompt is one more read on send] → reads run in parallel and
  the focused menu row is already prefetched; capped at 16.
- [The two constants (fred-sdk, fred-core) and the client one can drift] → a
  fred-runtime test builds a 16-entry and a 17-entry descriptor through both
  models; the client constant names its source in a comment.
- [A hand-typed name that is also a skill still becomes a skill] → unchanged
  rule, restated in the delta; the menu is the way to choose the prompt.

## Migration Plan

1. Merge and release as usual; no data migration.
2. Deploy runtime pods first (fred-agents and any other pod built on
   fred-runtime), then the frontend.
3. Rollback: the normal one. A rolled-back pod keeps serving stored lists; a
   rolled-back frontend ignores them.
