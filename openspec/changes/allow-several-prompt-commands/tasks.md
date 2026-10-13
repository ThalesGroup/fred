Sizes are honest guesses for one focused session each: S under an hour,
M one to three hours, L half a day or more. The contract and runtime part
(groups 1 to 3) lands first, as its own commits; the frontend (groups 4 to 7)
starts only when group 3 is green. Commands are in design.md, section 11; no
`make` target is run.

## 0. Owner confirmation

- [x] 0.1 (S) Get the owner's answer on the three defaults of design.md section 9 (same command twice, which prompt names the conversation, usage counting) and on the cap of 16; verify the three matching requirements of the delta spec and the table of section 9 say what was decided, and `openspec validate allow-several-prompt-commands --strict` passes

## 1. Contract: fred-sdk

- [x] 1.1 (S) In `libs/fred-sdk/fred_sdk/contracts/context.py`, add `MAX_TURN_PROMPTS`, `TurnCommandPrompt` and `TurnCommand.prompts` as in design.md section 2; verify with new cases in `libs/fred-sdk/tests/test_context.py`: a descriptor without `prompts` validates as before, one with 1 and with 16 entries validates and survives `model_dump(exclude_none=True)`, 17 entries, an empty list, a negative offset and a zero `text_length` are refused, an unknown key inside an entry is ignored
- [x] 1.2 (S) Run the five Python commands of design.md section 11 in `libs/fred-sdk`; verify all pass, with the type check reporting no new error against the baseline

## 2. Contract: fred-core

- [x] 2.1 (S) In `libs/fred-core/fred_core/history/history_schema.py`, add `CommandPromptDescriptor` (`extra="allow"`) and `CommandDescriptor.prompts` with the same bounds; verify with new cases in `libs/fred-core/fred_core/tests/history/test_history_schema.py`: `ChatMetadata` round-trips a descriptor with two entries through `model_dump(mode="json")` and `model_validate`, a row without `prompts` is unchanged, an unknown key in an entry is kept
- [x] 2.2 (S) Add a store-level case next to `test_history_store_ui_parts_round_trip.py`: a user row saved with a two-entry descriptor is read back with the same entries, and a row whose stored list has 17 entries is read back with empty metadata and no exception (the existing fallback); verify the file passes
- [x] 2.3 (S) Run the five Python commands in `libs/fred-core`; verify all pass

## 3. Runtime, generated files, contract document

- [x] 3.1 (S) Extend `libs/fred-runtime/tests/test_turn_command_descriptor.py`: a dumped `RuntimeContext` whose command lists two prompts gives a `CommandDescriptor` with the same two entries and the single fields of the first; a context dict whose list is malformed or has 17 entries gives no descriptor; a 16-entry and a 17-entry list get the same verdict from `TurnCommand` and from `CommandDescriptor` (the two caps cannot drift); verify the file passes with no change to `agent_app.py`, or record in design.md why a change was needed
- [x] 3.2 (S) Add a case proving the stored user text is the request text unchanged when a descriptor is present (leading and trailing characters, an emoji), so the offsets stay valid; verify it passes
- [x] 3.3 (S) Regenerate `libs/fred-runtime/openapi.json` and `apps/frontend/src/slices/runtime/runtimeOpenApi.ts` with the two commands of design.md section 6; verify the diff holds only `TurnCommandPrompt`, `CommandPromptDescriptor` and the two `prompts` fields, and that `npx --no-install tsc --noEmit -p .` passes in `apps/frontend`
- [x] 3.4 (S) Check the other two generated clients are unaffected: regenerate the control-plane and knowledge-flow specs with the two direct commands of design.md section 11 and verify `git status` shows no change in `apps/control-plane-backend/openapi.json`, `apps/knowledge-flow-backend/openapi.json` and their two client files
- [x] 3.5 (S) Run the five Python commands in `libs/fred-runtime`; verify all pass
- [x] 3.6 (S) Add `### 8.112 Several prompt commands on a user turn (<date>)` to `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` and one pointing sentence in 8.98, as described in design.md section 7; verify the entry states the field, the single fields' meaning, the offset unit, the cap, the behaviour of an older pod and the order, and that no other section is rewritten
- [x] 3.7 (S) Run the `fred-performance-reviewer` skill on the fred-sdk, fred-core and fred-runtime diff; verify its report is recorded in this change's `verification.md` and every finding is fixed or answered
- [x] 3.8 (S) Commit groups 1 to 3 as `feat(#3073): list every prompt command on the turn descriptor` (contract, tests, generated files, contract document); verify `git log` shows no frontend source file other than `runtimeOpenApi.ts` in it

## 4. Frontend: assemble and read

- [x] 4.1 (M) In `apps/frontend/src/rework/utils/skillInvocation.ts`, add the function that builds the text to send and its `TurnCommand` from the typed line and the resolved prompts, the function that returns a stored descriptor's usable list or nothing, and the client cap constant; verify with a new `skillInvocation.test.ts`: one prompt gives byte for byte today's text and single fields, two prompts and a repeated one give the expected text, offsets and `appended_text`, offsets are right with an emoji in a prompt, and a list that is empty, unsorted, overlapping, out of the text or not matching `draft_text` is refused
- [x] 4.2 (S) In `locales/fr/translation.json` and `locales/en/translation.json`, give `chatbot.commandMenu.runErrorStale` and `runErrorDetail` a `{{command}}` and add `runErrorTooMany` with `{{limit}}`; verify both files hold the same keys and no other key changes

## 5. Frontend: composer

- [x] 5.1 (L) In `useComposerCommands.ts`, turn the single prompt choice into a list: `selectedPrompts`, the remembered hand-typed tokens, the menu filter (prompts always offered), the closed menu on any rendered prompt token, and `dismiss` restoring one choice per usable entry; verify with new and updated cases in `useComposerCommands.test.tsx` for the first and sixth requirements of the delta (menu after a first prompt, two tokens from two libraries, removing one keeps the other, two typed names, typed homonym, typed skill homonym), and that the existing single-prompt cases still pass unchanged or with a mechanical rename only
- [x] 5.2 (L) In the same hook, replace `run` and the single-range part of `submit`: collect every prompt range, apply the cap, read each distinct prompt once in parallel, send through the function of 4.1 or report the first failing command with its name; verify with cases for the second requirement of the delta (order, prompts with skills, one stale, one unreadable, pending team catalog, repeated command read once, 17 commands) and that no partial or skills-only turn is ever sent on a failure
- [x] 5.3 (M) In `InlineSkillInput.tsx` and `RichInputField.tsx`, replace `promptToken` by `promptTokens`, each widget carrying its prompt identity and calling one stable callback; in `ManagedChatPage.tsx`, pass the list, open the preview of the activated token and pass the command name to the run-error toasts; verify with `InlineSkillInput.test.tsx` (two prompt tokens, each atomic, each with its own hint and label) and `ManagedChatPage.test.tsx` (preview of the second token, toggle, error naming the command, the limit message)
- [x] 5.4 (S) Check the length limit in `useManagedChat.ts` still measures the assembled text of a multi-prompt turn and that the title of a first turn uses the first prompt; verify with two cases in `useManagedChat.test.tsx`

## 6. Frontend: sent message, panel, recall

- [x] 6.1 (M) In `UserMessage.tsx`, `CommandTurn.tsx`, `UserTurn.tsx` and `ConversationThread.tsx`, render one prompt badge per usable entry and pass the entry's index when one is opened; keep the branches for turns without `draft_text`; verify with `UserTurn.test.tsx` and `CommandTurn.test.tsx`: two badges at their positions with skills, copy gives the typed line, a turn with the single fields only renders exactly as before (existing cases untouched), a turn whose list does not fit renders from the single fields
- [x] 6.2 (S) In `ManagedChatPage.tsx`, give the panel the activated entry's name, command and slice of the stored text, and the whole text when there is no usable list; verify with `ManagedChatPage.test.tsx`: the panel of the second badge shows only its prompt text, a single new-style prompt no longer shows the user's words, an old turn shows the whole text
- [x] 6.3 (M) In `useComposerRecall.ts`, include the entries' ids and offsets in the recall identity; verify with `useComposerRecall.test.tsx`: two prompts restored with their ids, same line with different prompts recalled separately, an old single-prompt turn recalled as before, and with `toThreadMessages.test.ts` that the list reaches the thread message from history and from the optimistic row
- [x] 6.4 (S) Run `tsc`, `eslint` and `prettier --check` on every touched file and `vitest run` on every touched test file; verify all pass and record the counts in `verification.md`

## 7. Docs and close-out

- [x] 7.1 (S) Update `docs/swift/ux/COMPONENT-UX.md` (section `CommandMenu`: several prompts per turn, one badge each, the panel shows one prompt's text); verify no sentence there still says a single prompt
- [x] 7.2 (S) Update Help Center `features/commands.md` in fr and en as listed in design.md section 12, in the non-technical wording of the page; verify both languages say the same and neither says "one prompt command"
- [x] 7.3 (S) Update `docs/swift/ops/migrations/3073-composer-command-menu-sections.md`: impact `minor`, `no_action_reason` removed, the order in Upgrade, the reload rendering in Limitations, a multi-prompt step in Validation; verify with the migration check command of design.md section 11, run directly and not through its `make` target
- [x] 7.4 (S) Reconcile this change with what was built: record exact verification evidence in `verification.md`, note any divergence in design.md, and list in the pull request the open questions for the reviewer (cap of 16, migration impact `minor` or `none`); verify `openspec validate allow-several-prompt-commands --strict` passes
- [ ] 7.5 (M) Owner check in the app, in Firefox and Chrome, fr and en: two and three prompts picked from both sections, the same one twice, prompts mixed with skills, typed names, each composer preview, send, badges, each panel, reload, recall, copy, a deleted prompt among several, the limit, an old conversation, and a new conversation's title; verify each point is ticked in `verification.md`
- [ ] 7.6 (S) After the merge, archive `section-composer-command-menu` first, then this change; verify `openspec validate --specs --strict` passes after each archive

## 8. Independent review fixes

- [x] 8.1 (M) Report the editor's exact edits (`onDraftEdit`) and map choices and remembered tokens through them, keeping the text diff as the fallback; verify with `useComposerCommands.test.tsx` ("deleting one of two tokens with the same name") and `InlineSkillInput.test.tsx`
- [x] 8.2 (S) Read every prompt fresh on submit; verify with `useComposerCommands.test.tsx` ("sends the prompt as its library holds it now")
- [x] 8.3 (S) Commit the remembered hand-typed tokens in an effect instead of during render; verify the existing hand-typed token cases still pass
- [x] 8.4 (S) Add the missing coverage: null entry, CRLF, the token rule, and the execute endpoint refusing 17 entries; verify with `skillInvocation.test.ts` and `libs/fred-runtime/tests/test_agent_app.py`
- [x] 8.5 (S) Record the fixes, the extra reads and the known limitations in design.md (sections 15 and 16) and verification.md; verify `openspec validate allow-several-prompt-commands --strict`
