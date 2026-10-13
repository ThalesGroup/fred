## Contract and runtime part (groups 1 to 3, task 7.3)

Run on 2026-10-13, branch `feat/composer-command-menu-sections`, with each
project's own `.venv` and no `make` target. The frontend behaviour (groups 4 to
6) was built afterwards; its evidence is in the second part of this file.

### Python

Commands, in each project: `VIRTUAL_ENV= .venv/bin/pytest -q -p no:cacheprovider
-m "not integration" --disable-socket --allow-unix-socket`, `.venv/bin/ruff
check .`, `.venv/bin/ruff check --select I .`, `.venv/bin/ruff format --check
.`, `.venv/bin/basedpyright --baseline-file .baseline/basedpyright-baseline.json`.

| Project | pytest | ruff check | import order | format | basedpyright |
| --- | --- | --- | --- | --- | --- |
| `libs/fred-sdk` | 647 passed, 3 skipped | passed | passed | 97 files formatted | 0 errors, 0 warnings |
| `libs/fred-core` | 1267 passed, 1 skipped, 42 deselected | passed | passed | 284 files formatted | 0 errors, 0 warnings |
| `libs/fred-runtime` | 2115 passed, 11 skipped, 22 deselected | passed | passed | 262 files formatted | 0 errors, 5 warnings |

The 5 basedpyright warnings of fred-runtime are in files this change does not
touch (none in `tests/test_turn_command_descriptor.py`).

Tests added: 13 cases in `libs/fred-sdk/tests/test_context.py` (5 functions,
two parametrised), 4 in `fred_core/tests/history/test_history_schema.py`, 2 in
`fred_core/tests/history/test_history_store_ui_parts_round_trip.py`, 4 in
`libs/fred-runtime/tests/test_turn_command_descriptor.py`.

Proven by tests:

- a descriptor without `prompts` validates and dumps as before, on both models;
- 1 and 16 entries validate and survive `RuntimeContext.model_dump(exclude_none=True)`;
- an empty list, 17 entries, a negative offset, a zero `text_length`, an empty
  command, an entry without its positions and a non-list are refused by
  `RuntimeContext`;
- an unknown key inside an entry is ignored by fred-sdk and kept by fred-core;
- offsets are not measured against any text;
- a two-entry descriptor round-trips through `ChatMetadata` and through a
  save and read of the history store;
- a stored list over the bound reads back with empty metadata, no exception,
  and the turn's text intact;
- a dumped `RuntimeContext` listing two prompts gives a `CommandDescriptor`
  with the same entries and the single fields of the first;
- a malformed or 17-entry list on the internal context drops the whole
  descriptor;
- `TurnCommand` and `CommandDescriptor` give the same verdict on 16 and on 17
  entries;
- `_write_turn_history` stores the request text unchanged (surrounding
  whitespace, an emoji, accents) next to a descriptor that lists a prompt.

`agent_app.py` is unchanged.

### Generated files

| Command | Result |
| --- | --- |
| `cd libs/fred-runtime && .venv/bin/python scripts/generate_openapi.py` | `openapi.json` rewritten (ignored by git) |
| `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json` | `runtimeOpenApi.ts`: 19 lines added, none removed |
| `cd apps/control-plane-backend && .venv/bin/python ../../scripts/generate_openapi.py control_plane_backend`, then codegen with `controlPlaneOpenApiConfig.json` | `controlPlaneOpenApi.ts` unchanged |
| `cd apps/knowledge-flow-backend && .venv/bin/python ../../scripts/generate_openapi.py knowledge_flow_backend`, then codegen with `knowledgeFlowOpenApiConfig.json` | `knowledgeFlowOpenApi.ts` unchanged |

The `runtimeOpenApi.ts` diff holds only the two new types
(`TurnCommandPrompt`, `CommandPromptDescriptor`) and the two `prompts` fields.
No unrelated drift appeared in any of the three clients.

### Frontend, after the regeneration

| Check | Result |
| --- | --- |
| `npx --no-install tsc --noEmit -p .` | exit 0 |
| `npx --no-install prettier --check src/slices/runtime/runtimeOpenApi.ts` | formatted |
| `npx --no-install vitest run` (full suite) | 3985 tests passed, 7 skipped |

### Other checks

| Check | Result |
| --- | --- |
| `apps/control-plane-backend/.venv/bin/python scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 new declaration |
| `openspec validate allow-several-prompt-commands --strict` | valid |

### Performance review (`fred-performance-reviewer` procedure, read-only)

Scope: the fred-sdk, fred-core and fred-runtime diff. Classification of the
touched paths: per-request validation and the per-turn history write
(category "per-turn orchestration"); no LLM call site, no tool invocation, no
KPI or log emission, no shared client, cache or module-level state.

Path walked:

1. FastAPI validates `RuntimeExecuteRequest`, so `TurnCommand`
   (`libs/fred-sdk/fred_sdk/contracts/context.py:424`) and at most 16
   `TurnCommandPrompt` (`:409`, bound at `:440`). Six scalar fields each, no
   validator function, no I/O. A longer list is refused there with a 422,
   before any work.
2. `to_legacy_context()` dumps the context into the internal request
   (`libs/fred-runtime/fred_runtime/app/agent_app.py:1280`): at most 16 small
   dicts more.
3. The `RuntimeContext` the pod rebuilds for the run
   (`agent_app.py:4579` onwards) does not copy `command`, so the list never
   reaches the agent loop, a model call or a tool call.
4. `_turn_command` (`agent_app.py:2917`, called at `:3801`, `:6247` and
   `:6353`) validates `CommandDescriptor`
   (`libs/fred-core/fred_core/history/history_schema.py:413`). Synchronous,
   CPU only, bounded by the same 16; at `:3801` it runs after the stream has
   been sent to the client.
5. The existing asynchronous history save writes the descriptor inside
   `metadata_json`; the row grows by a few kilobytes at most. The read path
   validates it with the `ChatMetadata` validation it already ran per row.

Invariants checked: no blocking I/O added inside a coroutine; no sequential
awaits added; no new metric, label, timer, logger or sink
(`PROMETHEUS_ALLOWED_LABELS` untouched); no outbound call, so no timeout to
bound; no new in-memory state, so nothing pod-local to declare; the added CPU
work is a bounded pydantic validation of scalars.

Findings: none. Confirmed from the code, not load-tested, and a load test
would not be informative for a bounded validation of this size.

To review when the frontend part is built (not in this diff): the send then
waits for one prompt read per distinct prompt, up to 16, which must run in
parallel and not one after the other.

### Not verified (contract part)

- No end-to-end run against the local services: no turn was sent with a
  `prompts` list (still true after the frontend part, see below).
- The behaviour of a pod on an older fred-sdk is read from the models' extra
  policy and from the unknown-key test, not exercised against an old build.
- The tests and quality checks of the other projects that depend on fred-core
  and fred-sdk (control-plane, knowledge-flow, fred-agents, capabilities) were
  not run; the change is additive and none of them reads the descriptor.

## Frontend part (groups 4 to 6, tasks 7.1, 7.2, 7.4)

Run on 2026-10-13, same branch, from `apps/frontend` with Node from fnm on the
`PATH`, no `make` target.

| Check | Result |
| --- | --- |
| `npx --no-install tsc --noEmit -p .` | exit 0 |
| `npx --no-install eslint` on the 19 touched `.ts`/`.tsx` files | exit 0, no warning |
| `npx --no-install prettier --check` on the touched `.ts`, `.tsx`, `.json` files and the two Help Center pages | all formatted |
| `npx --no-install vitest run` on the 9 touched test files and the 2 Help Center test files | 11 files, 412 tests passed |
| `npx --no-install vitest run` (full suite) | 330 files passed, 1 skipped; 4051 tests passed, 7 skipped (3985 before this part) |
| `openspec validate allow-several-prompt-commands --strict` | valid |
| `openspec validate section-composer-command-menu --strict` | valid |
| `apps/control-plane-backend/.venv/bin/python scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 new declaration |

Tests added: 23 in the new `utils/skillInvocation.test.ts`; 19 in
`useComposerCommands.test.tsx`; 8 in `ManagedChatPage.test.tsx`; 6 in
`UserTurn.test.tsx`; 2 in `CommandTurn.test.tsx`; 3 in
`useComposerRecall.test.tsx`; 2 in `toThreadMessages.test.ts`; 2 in
`useManagedChat.test.tsx`; 1 in `InlineSkillInput.test.tsx`.

Proven by tests, by requirement of the delta spec:

- **Several prompt commands in the composer.** After a first prompt token the
  menu lists the team's and the personal prompts and the skills; two tokens
  picked from two libraries keep their own library, and one Backspace on the
  first leaves the second with its library; two tokens in the editor are each
  one block with their own hint and label, each opens its own preview, and
  typing after or between them rebuilds neither; the page previews the
  activated token and closes on a second click; 17 prompt commands send
  nothing and report the limit, 16 are sent.
- **Expansion on send.** Two prompts expand in the order of the line with the
  user's text on its side of each; the reads start together and answers
  arriving out of order do not change the text; prompts and a skill travel in
  one turn; a 404 on one prompt, a 500 on one prompt and an empty prompt each
  hold the whole message back, with no command turn, no skills-only turn and
  no ordinary send, the draft unchanged, and the error naming that command;
  with two failures the first command of the line is reported, not the first
  failure in time; the page's toast carries the command name, and the limit
  for the cap; the length limit is measured on the assembled text.
- **Descriptor.** One prompt gives byte for byte the text and the single
  fields sent before (four line shapes compared with the former formula); two
  prompts and a repeated one give the expected text, offsets and
  `appended_text`; offsets are string indices with an emoji in the line and in
  the prompts; the list reaches the thread message from history and from the
  optimistic row.
- **Sent message and panel.** Two badges at their positions with a skill
  badge and no prompt text; each badge opens with its own index; copy, edit
  and selection give the typed line; the same command twice shows two badges;
  the panel of the second badge shows its name, command and text only, and
  the library is not read; a single listed prompt no longer shows the user's
  words; a turn with the single fields only, and a turn whose list does not
  fit its text, render one badge and open the whole text. The reader refuses
  a list that is empty, not a list, unsorted, overlapping, at the same
  position twice, outside the text, with an empty slice, a negative or
  non-integer position, a command not at its position or not the one typed
  there, an empty command, more than 16 entries, or no stored typed line.
- **Recall.** Both prompts restored as choices with their ids and libraries,
  and read from their own libraries on an unchanged submit; a prompt whose id
  is gone holds the message back and is named, with no fallback to a prompt of
  the same command; the same line with different prompts stays recallable
  twice and a true repetition collapses; a turn without the list restores its
  single prompt.
- **Hand-typed names.** Three typed occurrences resolve one by one, the team
  first, the personal one when the team has none, one read per distinct
  prompt; a picked personal homonym and the same name typed run two different
  prompts; a typed personal-only name next to a picked personal prompt waits
  for the team's catalog and runs once it has answered that it holds no such
  command (rewritten after the independent review, it expected an error); a typed name that is also a skill stays a skill next to a prompt,
  and becomes a prompt, and no longer a skill, when its prompt row is picked;
  hand-typed tokens survive deleting the text after them and an edit before
  them.
- **Same command twice.** Two tokens, two expansions, two entries, one read.
- **Title.** A first message `/summary /tone the Q3 report` names the
  conversation `Weekly review — the Q3 report`.
- **Older turns.** The existing single-prompt cases of `UserTurn.test.tsx`,
  `CommandTurn.test.tsx`, `useComposerRecall.test.tsx` and
  `ManagedChatPage.test.tsx` pass unchanged, apart from the page test's
  composer mock (token list) and the seven error assertions of the hook file
  that now also expect the command name.

Client performance point left open by the contract part: confirmed by the test
"starts every read before waiting for any of them" (both reads are issued
before the first answer) and by "expands the same command at each occurrence
and reads its prompt once". Since the independent review `fetchPrompt` is
called without `preferCacheValue` on submit: see the performance note below.

### Independent review fixes

Run after the fixes, on the branch tip. From `apps/frontend`:
`npx --no-install tsc --noEmit -p .` clean; eslint and prettier clean on the
changed files; `npx --no-install vitest run`: 331 files passed, 1 skipped;
4092 tests passed, 7 skipped. From `libs/fred-runtime`: `VIRTUAL_ENV=
.venv/bin/pytest -q -p no:cacheprovider -m "not integration" --disable-socket
--allow-unix-socket`: 2116 passed, 11 skipped, 22 deselected; `ruff check .`,
`ruff check --select I .`, `ruff format --check .` clean; `basedpyright
--baseline-file .baseline/basedpyright-baseline.json`: 0 errors, 5 warnings,
baseline unchanged. `scripts/migration_guides.py check-pr --base origin/swift
--worktree`: valid, 1 new declaration. `openspec validate
allow-several-prompt-commands --strict` valid.

- **Same-named tokens** (`useComposerCommands.test.tsx`, "deleting one of two
  tokens with the same name"): in `/summary /summary x` and `a /summary
  /summary x` with the team's prompt first and the personal one second,
  Backspace after the first leaves the personal prompt, on the token and on
  the sent descriptor; Delete on the second leaves the team's; undo gives
  both back and redo removes the same one; in `/review /review x`, a picked
  prompt then a picked skill, removing the prompt leaves the skill, which is
  what is sent. All four failed before the fix (the survivor was the team's
  prompt, or the prompt instead of the skill).
- **Exact edits** (`InlineSkillInput.test.tsx`): one transaction with two
  changes reports two spans, in the positions of the text before, and before
  `onChange`.
- **Fresh read** (`useComposerCommands.test.tsx`): a prompt whose prefetched
  detail differs from the server's answer is sent with the server's text; the
  submit call carries `preferCacheValue: false`. Four existing assertions on
  that argument follow.
- **Coverage added** (`skillInvocation.test.ts`): a list holding a null entry
  or a string is refused; a prompt text with CRLF line breaks keeps them and
  its slice reads back, with a CRLF before the token in the typed line; every
  delimited `/name` is found and nothing inside a path. Overlapping entries,
  out-of-order entries, `text_length` 0 and an emoji before a token were
  already covered. "Rows of a catalog that answered are shown while another
  loads" was already pinned by the loading case.
- **Endpoint limit** (`libs/fred-runtime/tests/test_agent_app.py`,
  `test_a_turn_listing_more_prompt_commands_than_the_limit_is_refused`): the
  execute endpoint answers 422 for 17 entries and 200 for 16. The harness
  already existed in that file.

Performance note. Submit now issues one request per distinct prompt even when
its detail was prefetched: at most 16, started together, as before for a
prompt that was typed or not focused in the menu. The prefetch on focus is
kept, so a picked prompt costs two reads over its life instead of one. A
submit that has to wait for a catalog adds no request of its own for one in
flight (the query's `refetch()` joins it) and one request for a catalog that
had failed. Nothing here is on the runtime's turn path.

Known limitations, not fixed (design.md, section 16): edits made while the
submit's reads are in flight are not sent; searching inside names opens the
menu on more ordinary prose, where Enter inserts and Esc closes; the three
older unarchived changes still state superseded requirements under another
capability and need the reviewer's or the owner's decision before any archive.

### Not verified

- Nothing was looked at in a browser: no rendering, no real keyboard, no
  Firefox or Chrome check, no fr or en reading of the toasts in place. Task
  7.5 is the owner's.
- No turn was sent to a running runtime: the 422 for a malformed list, the
  stored row and the reload are covered on the Python side and by client
  tests on hand-built descriptors, not end to end.
- "Running prompt commands leaves prompt use counters unchanged" is true by
  construction (the send path calls no `/use` mutation, as before) and has no
  test of its own.
- "A reader that ignores the list" and "a runtime that does not know the
  list" are covered through the same fallback (a descriptor with the single
  fields only renders one badge), not against an older bundle or pod.

### Questions for the reviewer

No pull request is open yet; these go in its description when it is.

- Is 16 the right cap on prompt commands per message?
- Migration impact: `minor` (a recommended deployment order exists) or `none`
  with the same Limitations text?

### Owner check (task 7.5)

Done by the owner on 2026-10-13 in the running app, in Firefox: the whole
feature, including several prompts per message, reload, recall, the
stale-command error and the four scenarios of "Independent review fixes".
Result as reported by the owner: all good. The confirmation was given for the
feature as a whole; the points below are ticked on that basis, not from a
point-by-point report.

- [x] Two and three prompts picked from both sections
- [ ] The same prompt twice: covered by tests, not reported as tried by the owner
- [ ] Prompts mixed with skills: covered by tests, not reported as tried by the owner
- [ ] Typed names: covered by tests, not reported as tried by the owner
- [x] Each composer preview
- [x] Send, badges, each panel
- [x] Reload
- [x] Recall
- [ ] Copy: covered by tests, not reported as tried by the owner
- [x] A deleted prompt among several
- [ ] The limit: covered by tests, not reported as tried by the owner
- [ ] An old conversation: covered by tests, not reported as tried by the owner
- [ ] A new conversation's title: covered by tests, not reported as tried by the owner
- [x] Firefox
- [ ] Chrome: not confirmed by the owner

Not verified: Chrome; whether both fr and en were read in place was not
reported. "Not verified" above ("nothing was looked at in a browser", "no turn
was sent to a running runtime") was written before this check and stands for
the assistant's own evidence.

Seen on the dev stack: a message with several prompts sent through a runtime
that does not know the list keeps only its first badge after a reload, with
no error.

Accepted as is by the owner:

- Cosmetic: the caret can look slightly off right before a token that is the
  first element of the field.
- To be watched if it is ever met in real use: when a command catalog is down
  and the retry on submit also fails, a message holding a hand-typed word
  shaped like `/name` is held back with the "could not be read" toast, even
  when that word was ordinary text. No change is planned.

### Final run after the rebase (both changes, before archiving)

Run on 2026-10-13 after a conflict-free rebase onto `origin/swift` (ee8330219),
with the commands of the first section and no `make` target.

| Project | pytest | ruff check | import order | format | basedpyright |
| --- | --- | --- | --- | --- | --- |
| `libs/fred-sdk` | 647 passed, 3 skipped | passed | passed | 97 files formatted | 0 errors, 0 warnings |
| `libs/fred-core` | 1267 passed, 1 skipped, 42 deselected | passed | passed | 284 files formatted | 0 errors, 0 warnings |
| `libs/fred-runtime` | 2119 passed, 11 skipped, 22 deselected | passed | passed | 262 files formatted | 0 errors, 5 warnings (untouched files) |
| `apps/control-plane-backend` | 1780 passed, 9 skipped, 11 deselected | passed | passed | 407 files formatted | 0 errors, 0 warnings |
| `apps/knowledge-flow-backend` | 1454 passed, 45 deselected | passed | passed | 461 files formatted | 0 errors, 0 warnings |
| `apps/fred-agents` | 132 passed, 6 xfailed | passed | passed | 54 files formatted | 0 errors, 0 warnings |

Generated clients: the three specs and the three clients were regenerated with
the direct commands of "Generated files"; `runtimeOpenApi.ts`,
`controlPlaneOpenApi.ts` and `knowledgeFlowOpenApi.ts` came out unchanged.

Frontend, from `apps/frontend`: `tsc --noEmit -p .` exit 0; eslint clean on
the 28 changed `.ts`/`.tsx` files; `prettier --check` clean on the 39
changed files; `vitest run`: 331 files passed, 1 skipped; 4092 tests passed,
7 skipped. `scripts/migration_guides.py check-pr --base origin/swift
--worktree`: valid, 1 new declaration. Both changes valid with `--strict`
before their archive.

After the two archives, `openspec validate --all --strict`: 72 passed, 2
failed (`add-agent-initiated-human-questions` and the spec
`frontend-surface-scale`); both fail the same way on `origin/swift`.
