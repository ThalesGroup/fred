## 1. The trigger seam

- [ ] 1.1 Add an opt-in trigger prop to `RichInputField` reporting when `/` is
      typed as the first character of an empty value, when the query after it
      changes, and when it is deleted away; verify tests cover the trigger at
      position zero (reported), a `/` inside text (not reported), typing after
      it (query updates), and deleting back past it (closed).
- [ ] 1.2 Add the placeholder — shown whenever the value is empty, focused or
      not — and carry the same sentence on the field's accessible
      description; verify tests assert it is present unfocused, present
      focused, gone after one keystroke, and reachable on the accessible
      description.
- [ ] 1.3 Keep every existing `RichInputField` behaviour untouched when the
      trigger prop is absent; verify the existing suite passes unchanged and
      a test asserts `/` at position zero does nothing without the prop.

## 2. The menu

- [ ] 2.1 Build the menu as a sectioned list with one section titled for the
      prompt library, offering only the active team's prompts that carry a
      command, filtered by the typed query; verify tests cover the heading
      rendering with a single section, prompts without a command being
      excluded, and filtering.
- [ ] 2.2 Dress it from `HomeSearch.module.scss` — `--surface-container-high`,
      `1px solid --outline-muted`, `--elevation-2`, `--on-surface-muted`
      heading, `--state-on-surface-hover` rows, `--radius-s` rows, and
      `--radius-s` on the container itself; verify a review confirms no raw
      colour, no arbitrary pixel value and no new token.
- [ ] 2.3 Implement the keyboard model on the textarea: best match focused on
      open, `Down`/`Up` walking every entry in visual order and wrapping,
      re-filtering re-focusing the best match, `Tab` completing with a
      trailing space, `Enter` running, `Esc` closing and keeping the text,
      pointer activation behaving as `Tab`; verify one test per row of that
      list.
- [ ] 2.4 Keep the caret in the composer and convey the focused entry through
      the textarea's active descendant; verify a test drives the whole menu by
      keyboard alone and asserts the textarea keeps focus throughout, and
      that `Esc` restores ordinary tabbing.
- [ ] 2.5 Prefetch the focused entry's prompt detail as the focus moves;
      verify a test asserts the detail query fires for the focused entry and
      that moving the focus does not refetch an entry already cached.

## 3. Running a command

- [ ] 3.1 Resolve the composer's first token against the active team's
      commands on submit, whatever the menu is doing; verify tests cover
      `Tab` then `Enter`, `Enter` from the menu, and submit with the menu
      closed, all reaching the same send.
- [ ] 3.2 Send the prompt's text with any trailing text appended, and set the
      descriptor on the `runtimeContext`; verify a test asserts the request
      carries the assembled text as `input` and the descriptor as
      `runtime_context.command`, and that the composer never held the prompt
      text.
- [ ] 3.3 Send an unmatched token as ordinary text with no descriptor; verify
      a test submits `/nosuchcommand` and asserts it is sent verbatim.
- [ ] 3.4 Keep the callbacks handed to the menu and the composer stable across
      a keystroke render; verify a test asserts their identity holds, as
      `ConversationThread.rowCallbacks.test.tsx` does for the transcript —
      this is the third time this branch has hit that class of bug.

## 4. Documentation

- [ ] 4.1 Write the Help Center pages in `fr` and `en` under
      `features/helpCenter/content/{fr,en}/`, covering authoring a command and
      running one from the chat; verify they follow the existing tone rules
      (no indexed/Prêt jargon, "instructions" not "system prompt", Corpus
      d'équipe only).
- [ ] 4.2 Add the `fr` and `en` translations for the menu heading, the
      placeholder and the accessible description; verify no key resolves to
      its own name in either locale.
- [ ] 4.3 Update `docs/swift/ux/COMPONENT-UX.md` with the menu and the
      composer placeholder; verify the entry states the trigger is
      first-position only.

## 5. Close-out

- [ ] 5.1 Run `make code-quality` and `make test` in `apps/frontend`; verify
      both pass with no new warnings.
- [ ] 5.2 Ask the developer to run `/code-review` on the diff and address the
      findings; verify none remains open. The assistant cannot invoke it.
- [ ] 5.3 Fold `prompt-command-field.md` and `prompt-command-turn.md` into one
      note under `docs/swift/ops/migrations/` covering the whole feature, and
      delete the two: all three slices ship as a single PR, so operators read
      one note. Its impact is `minor` — the Alembic revision dominates. Verify
      `make migration-check` passes from the repository root and that no
      stale declaration is left behind.
- [ ] 5.4 Record verification evidence here, then fold whatever the RFC still
      holds into the OpenSpec specs and archive
      `PROMPT-COMMAND-TRIGGER-RFC.md`; verify the RFC directory no longer
      carries an open prompt-command design.
- [ ] 5.5 Archive this change and the two before it once merged; verify
      `openspec/specs/prompt-commands/spec.md` carries the field, the turn and
      the trigger as one current capability spec.
