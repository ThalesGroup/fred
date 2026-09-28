## Why

Two slices have shipped: a prompt can carry a command (#2828), and a turn that
ran one is stored and rendered as that command (#2829). Nothing can run one.
This slice is the composer — the last of `PROMPT-COMMAND-TRIGGER-RFC.md`, and
the first that a user can see working.

Today a team's prompts are reachable only through the library side panel: open
it, find the prompt, insert it, send it. Four deliberate actions for something
a user may want a dozen times a day, each pulling them out of the composer
they were typing in.

## What Changes

- Typing `/` as the **first character of an empty composer** opens a menu
  above it. Subsequent characters filter it. First position only: a trigger
  that fires anywhere turns `/tmp/log` and "et/ou" into spurious menus.
- The menu is a **sectioned list from day one**, with one section today,
  "Prompts de la bibliothèque". Team-scoped custom skills are the intended
  second section; nothing about them is built here, but adding one must be a
  new entry rather than a rewrite.
- Keyboard: the best match is focused on open; `Down`/`Up` walk every entry in
  visual order and wrap; `Tab` completes and appends a trailing space; `Enter`
  runs; `Esc` closes and leaves the typed text alone; a click behaves like
  `Tab`. `Enter` on a completed command with the menu already closed runs it
  too.
- **Running a command sends the prompt behind it.** The prompt's text never
  passes through the composer and the user never sees it there. Text typed
  after the command is appended — free-text continuation, nothing parsed or
  validated.
- The composer gains a placeholder, shown whenever it is empty whether focused
  or not: "Posez votre question, ou tapez / pour une commande". A placeholder
  is not an accessible instruction, so the same hint goes on the field's
  accessible description.
- **Help Center pages, `fr` and `en`, ship in this change** — the slice that
  makes the feature reachable is the one that has to teach it.

## Capabilities

### Modified Capabilities

- `prompt-commands`: gains how a command is invoked from the composer. The two
  earlier slices are in flight as `add-prompt-command-field` (#2828) and
  `add-command-turn-rendering` (#2829); this change adds requirements to the
  same capability rather than opening a second one.

## Impact

**Frontend — `apps/frontend`, and only the frontend.**

No backend change: the field, the turn descriptor and the rendering all exist.
The composer sets `command` on the `RuntimeContext` it already sends, and the
turn renders itself.

- `RichInputField`: an opt-in trigger seam and the placeholder. It is a shared
  molecule, so the trigger is a prop, not built into the textarea — though it
  has exactly one host today (`ManagedChatPage`), so nothing existing is at
  risk.
- A command menu component, dressed from the home-page spotlight's results
  container (`HomeSearch.module.scss`) with a tighter `--radius-s`: it sits
  against the composer rather than floating free.
- `ManagedChatPage`: owns the menu's state and the run action, and already
  holds the `runtimeContext` the descriptor rides on.
- Help Center pages under
  `features/helpCenter/content/{fr,en}/`, and translations for the menu,
  the placeholder and the accessible description.

**Out of scope**

- Making platform skills (#2711) user-invocable. They are model-facing by
  design and stay that way.
- Building team custom skills or their menu section.
- Named or structured parameters (`/revue doc=42`). Trailing text is plain
  continuation; parsing it is a separate design.
