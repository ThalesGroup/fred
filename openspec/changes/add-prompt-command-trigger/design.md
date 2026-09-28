## Context

See proposal.md — Why. The behaviour contract is in
`specs/prompt-commands/spec.md`; this covers how it is reached and the one
thing that is not free.

What the code already gives:

- `RichInputField` is a plain auto-growing `textarea` with an optional
  `placeholder` prop and a `handleKeyDown` that sends on `Enter` without
  `Shift`. No trigger character, no menu, nothing to unpick.
- It has exactly **one host**, `ManagedChatPage`. The RFC worried about
  keeping a search bar's behaviour intact; that host does not exist, so the
  opt-in seam is for future hosts rather than for protecting a current one.
- `ManagedChatPage` already owns the `runtimeContext` a turn rides on, so
  setting `command` on it is where the state already lives.
- `HomeSearch.module.scss` already dresses a floating result list with the
  exact tokens the menu needs.

## Goals / Non-Goals

**Goals:**

- A trigger that never fires on ordinary text.
- A menu wholly operable from the keyboard, with the caret never leaving the
  composer.
- The prompt's text reaching the agent without ever appearing in the composer.

**Non-Goals:**

- Any backend change. The field, the descriptor and the rendering all shipped.
- Named parameters. Trailing text is plain continuation.
- Team custom skills or their section.
- Triggering anywhere but the first character.

## Decisions

**Fetch the prompt's text when the command runs, and prefetch the focused
one.** This is the one real cost in the slice. The listing endpoint returns
`text_preview`, not `text` (`PromptSummary`, deliberately — a library of long
prompts would make the listing huge), so running a command needs the detail
endpoint.

Fetching at run time puts one control-plane round trip in front of the send.
To keep it off the critical path in practice, the menu prefetches the focused
entry's detail as the focus moves: RTK Query caches it, so by the time the
user presses `Enter` the text is usually already there. The fetch still has to
be awaited before sending — the prefetch makes it fast, it does not make it
optional.

Alternative rejected: loading every prompt's full text when the chat opens.
It moves the cost to a place the user is already waiting and scales with the
team's library rather than with what they actually run.

Alternative rejected: sending the command and expanding it server-side. The
runtime knows nothing about prompts — they live in control-plane — and
teaching it would put a product lookup on the execution path.

**Keep the trigger a prop on `RichInputField`, not a behaviour of it.** One
host today, but the component is explicitly documented as usable as a plain
textarea or a search bar. A trigger baked in would surprise the next host.

**Model the composer as a combobox pointing at a listbox.** The caret must
stay in the textarea — that is what frees `Tab` to mean "complete" rather than
"move focus". So the menu is never focused; the focused entry is conveyed
through the textarea's own active-descendant, and every key is handled on the
textarea.

The consequence worth planning for: while the menu is open, `Tab` no longer
moves focus. `Esc` is the only way back to normal tabbing, so it must always
close the menu — a menu dismissable only by clicking away would trap a
keyboard user.

**Resolve the command on submit, not only from the menu.** `Tab` then `Enter`
and `Enter` alone must reach the same place. So the send path checks whether
the composer's first token matches a command of the active team, whatever the
menu is doing. A token that matches nothing is sent as typed — the user may
genuinely have meant to write `/nosuchcommand`.

**Take the spotlight's container, with a tighter radius.** Same fill
(`--surface-container-high`), border (`1px solid --outline-muted`), elevation
(`--elevation-2`), section title (`--on-surface-muted`), row hover
(`--state-on-surface-hover`) and row radius (`--radius-s`) as
`HomeSearch.module.scss`. The container's own radius drops from `--radius-m`
to `--radius-s`: it sits against the composer rather than floating free.
Design-system tokens only; no new token for this work.

**Put the placeholder on the field unconditionally.** Ordinary placeholder
behaviour — visible while empty, focused or not — which is also the accessible
default. The accessible description carries the same sentence because a
placeholder is neither reliably announced nor durable past the first
keystroke.

## Risks / Trade-offs

**One round trip before a command sends.** → Mitigated by prefetching the
focused entry, not eliminated. Worth measuring once it is in: if the prefetch
misses often, the fallback is prefetching the whole filtered set rather than
just the focused row.

**`Tab` changes meaning while the menu is open.** → Bounded: the menu only
opens on `/` at position zero, and `Esc` always closes it. Worth an explicit
keyboard-only test rather than trust.

**A stale menu can offer a command that no longer resolves.** → The submit
path re-checks against the current list, and an unmatched token is sent as
typed. Nothing errors.

**The command list is the active team's.** → A prompt of another team the user
belongs to is not offered, matching where the command was reserved. Switching
teams changes the menu, which is the same rule the prompt library already
follows.

**Prompt text can be long, and the user cannot see what they are sending.**
→ Deliberate, and the whole point of the trigger; the transcript's command
component opens the exact text that was sent, and the library panel remains
the place to read or adapt a prompt before sending.

## Migration Plan

No schema change, no data migration, no backend change. An older backend
serves everything this needs.

The Help Center pages ship here, which is the point in the sequence where the
feature becomes usable and therefore has to be teachable.
