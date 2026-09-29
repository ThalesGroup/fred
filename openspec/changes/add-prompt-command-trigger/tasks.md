## 1. The trigger seam

- [x] 1.1 Add an opt-in trigger prop to `RichInputField` reporting when `/` is
      typed as the first character of an empty value, when the query after it
      changes, and when it is deleted away; verify tests cover the trigger at
      position zero (reported), a `/` inside text (not reported), typing after
      it (query updates), and deleting back past it (closed).
- [x] 1.2 Add the placeholder — shown whenever the value is empty, focused or
      not — and carry the same sentence on the field's accessible
      description; verify tests assert it is present unfocused, present
      focused, gone after one keystroke, and reachable on the accessible
      description.
- [x] 1.3 Keep every existing `RichInputField` behaviour untouched when the
      trigger prop is absent; verify the existing suite passes unchanged and
      a test asserts `/` at position zero does nothing without the prop.

## 2. The menu

- [x] 2.1 Build the menu as a sectioned list with one section titled for the
      prompt library, offering only the active team's prompts that carry a
      command, filtered by the typed query; verify tests cover the heading
      rendering with a single section, prompts without a command being
      excluded, and filtering.
- [x] 2.2 Dress it from `HomeSearch.module.scss` — `--surface-container-high`,
      `1px solid --outline-muted`, `--elevation-2`, `--on-surface-muted`
      heading, `--state-on-surface-hover` rows, `--radius-s` rows, and
      `--radius-s` on the container itself; verify a review confirms no raw
      colour, no arbitrary pixel value and no new token.
- [x] 2.3 Implement the keyboard model on the textarea: best match focused on
      open, `Down`/`Up` walking every entry in visual order and wrapping,
      re-filtering re-focusing the best match, `Tab` completing with a
      trailing space, `Enter` running, `Esc` closing and keeping the text,
      pointer activation behaving as `Tab`; verify one test per row of that
      list.
- [x] 2.4 Keep the caret in the composer and convey the focused entry through
      the textarea's active descendant; verify a test drives the whole menu by
      keyboard alone and asserts the textarea keeps focus throughout, and
      that `Esc` restores ordinary tabbing.
- [x] 2.5 Prefetch the focused entry's prompt detail as the focus moves;
      verify a test asserts the detail query fires for the focused entry and
      that moving the focus does not refetch an entry already cached.

## 3. Running a command

- [x] 3.1 Resolve the composer's first token against the active team's
      commands on submit, whatever the menu is doing; verify tests cover
      `Tab` then `Enter`, `Enter` from the menu, and submit with the menu
      closed, all reaching the same send.
- [x] 3.2 Send the prompt's text with any trailing text appended, and set the
      descriptor on the `runtimeContext`; verify a test asserts the request
      carries the assembled text as `input` and the descriptor as
      `runtime_context.command`, and that the composer never held the prompt
      text.
- [x] 3.3 Send an unmatched token as ordinary text with no descriptor; verify
      a test submits `/nosuchcommand` and asserts it is sent verbatim.
- [x] 3.4 Keep the callbacks handed to the menu and the composer stable across
      a keystroke render; verify a test asserts their identity holds, as
      `ConversationThread.rowCallbacks.test.tsx` does for the transcript —
      this is the third time this branch has hit that class of bug.

## 4. Documentation

- [x] 4.1 Write the Help Center pages in `fr` and `en` under
      `features/helpCenter/content/{fr,en}/`, covering authoring a command and
      running one from the chat; verify they follow the existing tone rules
      (no indexed/Prêt jargon, "instructions" not "system prompt", Corpus
      d'équipe only).
- [x] 4.2 Add the `fr` and `en` translations for the menu heading, the
      placeholder and the accessible description; verify no key resolves to
      its own name in either locale.
- [x] 4.3 Update `docs/swift/ux/COMPONENT-UX.md` with the menu and the
      composer placeholder; verify the entry states the trigger is
      first-position only.

## 5. Close-out

- [x] 5.1 Run `make code-quality` and `make test` in `apps/frontend`; verify
      both pass with no new warnings.
- [x] 5.2 Ask the developer to run `/code-review` on the diff and address the
      findings; verify none remains open. The assistant cannot invoke it.
- [x] 5.3 Fold `prompt-command-field.md` and `prompt-command-turn.md` into one
      note under `docs/swift/ops/migrations/` covering the whole feature, and
      delete the two: all three slices ship as a single PR, so operators read
      one note. Its impact is `minor` — the Alembic revision dominates. Verify
      `make migration-check` passes from the repository root and that no
      stale declaration is left behind.
- [x] 5.4 Record verification evidence here, then fold whatever the RFC still
      holds into the OpenSpec specs and archive
      `PROMPT-COMMAND-TRIGGER-RFC.md`; verify the RFC directory no longer
      carries an open prompt-command design.
- [ ] 5.5 Archive this change and the two before it once merged; verify
      `openspec/specs/prompt-commands/spec.md` carries the field, the turn and
      the trigger as one current capability spec.

## Verification evidence

**Frontend, and only the frontend.** `make code-quality` clean (tsc, prettier,
eslint). `make test` → **2949 passed, 7 skipped, 253 files** (25 new: 9 on the
trigger seam, 16 driving the whole menu). `make migration-check` valid from the
repository root, one declaration.

Every new test was falsified against the wrong behaviour before being trusted:
an unanchored trigger regex fails "reports nothing for a slash inside text"; a
non-wrapping `ArrowUp`, an `Esc` that does not close, and an `Enter` that
re-parses the typed token instead of running the focused entry each fail their
own test.

**Two deviations from the plan, both deliberate.**

`--elevation-2` (task 2.2, taken from `HomeSearch.module.scss`) **does not
exist** as a token — the spotlight reads it with a raw shadow fallback, which is
what actually renders there. The menu uses `--shadow-m` instead, the shared
menu grammar `MenuPopover` already defines for exactly this surface; every other
value in that task is as specified. Using the phantom token would have meant
shipping a raw colour behind a `var()` fallback.

Task 1.2 asks for a test that the placeholder is "gone after one keystroke".
That is the platform's own placeholder rule, not this code's behaviour, so the
test asserts what is ours: the attribute is set unconditionally rather than only
on focus, and the same sentence is durably announced on the accessible
description. The test says so in a comment.

**`/code-review`** (task 5.2) was run by the developer on the whole branch.
Four findings, all fixed, each with a test that fails against the previous code:

1. *The command list was capped.* The menu read `GET /teams/{id}/prompts`, which
   returns at most 100 rows ordered by `updated_at` — so in a large library a
   real command was missing from the menu **and** from the submit-time lookup,
   and the typed token went to the agent as literal text with no error. Fixed by
   its own uncapped surface, `GET /teams/{team_id}/prompt-commands`
   (`PromptCommandSummary`: five columns, no prompt text), with
   `list_commanded_by_team` on the store. Covered by
   `test_prompt_store_lists_every_command_past_the_listing_cap` (121 prompts,
   the command on the one the capped listing drops first) and
   `test_prompt_commands_endpoint_lists_only_invocable_prompts`. The new route
   also has its row in `authz-endpoint-matrix.yaml` (`can_use_team_agents`,
   approved) — `test_authz_endpoint_matrix` refuses any published route without
   one, and caught this before the branch was committed.
2. *Enter ran a command while sending was blocked.* The trigger was consulted
   before the `disabled`/`sendDisabled` guard, so an attachment still uploading
   or an over-limit draft let a command through into a send `sendTurn` then
   dropped with only a `console.debug`. The field now withholds Enter alone from
   the menu while sending is blocked — the arrows, `Tab` and `Esc` still work,
   and the menu needs to know nothing about uploads.
3. *Every `/summary` conversation got the same title.* `createSessionRow` was
   handed the assembled prompt body; nothing retitles a session afterwards. It
   now takes the command line the user actually typed.
4. *The character limit was measured on the wrong text.* `inputTooLong` counts
   the composer draft, which on a command is the short command line. The runtime
   does enforce the limit on `input`, so this was a round trip and a late toast
   rather than a true bypass — the command path now counts the assembled text
   before sending and says so immediately.

Two convention notes came with it. The issue numbers in new code are gone
(`ConversationThread.rowCallbacks.test.tsx`'s header, and a `(#2369)` on a
`useManagedChat.ts` line this diff rewrote). The other — the
`ImportPromptDialog` origin-team checkbox, which rode in with the field slice
and is unrelated to commands — is left in place deliberately: it was asked for
in the same breath as the import-collision design, extracting nine lines from a
commit fifteen deep would rewrite the whole branch, and splitting it into its
own PR would put two PRs on the same file. Stated rather than silently ignored.

**Where the design now lives.** `PROMPT-COMMAND-TRIGGER-RFC.md` is archived
(deleted, the convention this repository follows for a closed RFC): the prompt
side is folded into `PROMPTS.md` §3.2, the composer and transcript side into
`COMPONENT-UX.md`. The two per-slice migration notes are folded into one,
`prompt-commands.md`. The three changes' own artifacts still reference the RFC
by name — they are the record of why each slice was cut, not current guidance.
