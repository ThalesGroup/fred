# Prompt Command Trigger RFC — running a library prompt from the composer with `/`

**Status:** Design agreed 2026-09-28; nothing left open. To be built as
OpenSpec changes — this file is the umbrella for work too broad for one slice,
and should thin as each slice leaves it, then be archived.
**ID:** `PROMPT-CMD-01` (informal label, no registry)
**Author:** Maxime
**Date:** 2026-09-28
**Area:** `control-plane-backend` (prompt model), `frontend` (composer)
**Current design:** [`PROMPTS.md`](../design/PROMPTS.md)

Scoped to what is still open. The prompt library itself is shipped and
documented; this RFC covers only the new command field and the composer
trigger that consumes it.

---

## 1. Problem

A team's prompts are reachable only through the prompt-library side panel: open
the panel, find the prompt, insert it, send it. That is four deliberate actions for
something a user may want a dozen times a day, and it pulls their attention out
of the composer they were typing in.

Every tool this audience already uses — Slack, Discord, Notion, Claude Code —
solves this with a typed trigger and an autocompleting menu. Fred's composer
binds no trigger character at all today (`RichInputField` is a plain
`textarea`), so the convention is available to take.

---

## 2. Proposal

### 2.1 A `command` field on a prompt

Prompt creation and editing gain one field, labelled "Commande". The user types
the string that will trigger the prompt.

It is **not** the prompt's name. `PromptRow.name` is display text: it allows
spaces and mixed case, and an autocompletion has no way to know where a
multi-word token ends. `command` is a separate slug:

- lowercase ASCII letters, digits and `-`; no whitespace, **no accented
  characters**. A French team will be tempted by `/résumé`, but accepting it
  drags accent folding and case folding into the uniqueness rule for a gain
  the user never sees — they type the command, they do not read it.
- optional — a prompt without a command stays panel-only
- unique per team, enforced by its own constraint. The existing
  `uq_prompt_team_name` covers `name`, not this.

### 2.2 The `/` trigger

Typing `/` as the **first character of an empty composer** opens a menu above
the composer. Subsequent characters filter it. Selecting an entry runs the
prompt behind the command (§2.4).

First position only, for v1: a trigger that fires anywhere turns `/tmp/log` and
"et/ou" into spurious menus. Slack takes the same restriction, so the behaviour
is already familiar. Widening it later is additive; narrowing it would be a
regression.

`/` rather than the alternatives:

| Candidate | Rejected because |
| --- | --- |
| `#` | opens a markdown heading — false triggers on pasted formatted text |
| `>` | markdown blockquote, same failure |
| `@` | means "designate an entity" to every user. Reserve it for mentioning documents, agents or teammates. |
| `:` | single unshifted AZERTY key, but collides with `:emoji:` and "Note :" |
| `!` | cheapest AZERTY keystroke (unshifted), but carries no command meaning and opens markdown image syntax `![…]` |

`/` costs Shift+`:` on AZERTY, which is acceptable, and it is the one character
this audience already reads as "run something".

### 2.3 A menu built for two sections

The menu renders sections, not one flat list. v1 ships a single **Prompts**
section; a **Skills** section is the intended second one.

The skills concerned are **not** the platform skills of #2711. Those are
model-facing: the middleware advertises them in the system prompt and the model
decides when to open one — a user never launches them, and they must stay that
way. The second section is for the future team-scoped custom skills, which
will be authored and owned by teams exactly as prompts are.

Nothing about that future is built here. What this RFC asks for is that the
menu be a sectioned list from day one, so adding the second section is a new
entry rather than a rewrite.

### 2.4 Keyboard model

The menu opens with its **best match focused**. From there:

| Input | Effect |
| --- | --- |
| `Tab` | completes the focused command in the text field, closes the menu, and appends a trailing space |
| `Enter` | runs the focused command straight away |
| Click on an entry | same as `Tab` |

And once the menu is shut on a completed command (`/revue `), `Enter` runs it
too. So a command resolves on submit as well as from the menu: `Tab` then
`Enter` and `Enter` alone reach the same place, which is what a user who
completed with `Tab` and pressed `Enter` will expect. The literal text `/revue`
is never sent.

The split matters: `Tab` is typing assistance for someone unsure of the
spelling, `Enter` is the shortcut for someone who knows exactly what they want.
Keeping them distinct means the fast path stays one keystroke without making
the assisted path commit to anything.

The trailing space `Tab` appends is deliberate. It leaves the caret where an
argument would go — arguments are a non-goal here (§5), but the keystroke
should not have to change the day they arrive.

**Running a command sends the prompt behind it to the agent.** The prompt's
text never passes through the composer, and the user does not see it appear.

That is the whole value of the trigger: the prompt is a known, settled piece of
text, and re-reading it before every send is friction, not safety. A user who
does want to read or adapt it has the prompt-library panel on the right, which
already inserts editable text. The two paths stay distinct on purpose — `/`
fires, the panel edits — and neither has to compromise for the other.

**Text typed after the command is appended to the prompt.** A library prompt
ending in a colon is meant to be continued: *"Résume le document et ensuite
rédige une synthèse de :"* plus `/summary 33 lignes` sends the prompt followed
by `33 lignes`.

This is free-text continuation, not parameters: nothing is parsed, named or
validated, and the prompt author carries the burden of writing text that reads
well when something is appended. Named arguments stay a non-goal (§5); this
rule only says what the trailing words already mean.

### 2.5 How the turn reads in the conversation

The prompt never passes through the composer, so the transcript needs its own
answer: a dedicated component renders the turn as **the command**, with the
appended text (§2.4) beside it. Clicking it opens the prompt that was actually
sent, in a panel. The chat body never shows the prompt text.

The mechanism follows the shape a turn already has. A stored user turn is:

```
parts_json     [{"type": "text", "text": "…"}]     the content
metadata_json  {"sources": [], "ui_parts": []}     side data, not rendered
```

So:

- **`parts_json` holds the full assembled text** — the prompt plus anything the
  user appended. This is not a choice. That history is replayed to the model on
  every later turn: a turn holding only `/summary 33 lignes` would leave the
  model reading a command it knows nothing about, and the conversation would
  stop making sense from the second turn on.
- **`metadata_json` gains the command descriptor** — the command, the appended
  text, the prompt id and its name. It is side data the renderer reads and no
  one displays raw.
- **The transcript renderer** sees that descriptor and draws the command
  component *instead of* the text part. The panel then shows the text it
  already holds in `parts_json`.

Nothing is duplicated: the text is stored once, in the only place it had to be
anyway, and the descriptor merely says "render this one differently". A client
that does not know the new keys renders the turn as plain text — degraded, not
broken.

This also settles the staleness problem. `prompt.text` is overwritten on edit
and the repository keeps no version history — `prompt.version` is a counter on
the live row, there is no history table — so resolving `prompt_id` at display
time would show a conversation asking something it never asked, and nothing at
all once the prompt is deleted. Reading the turn's own content avoids that
entirely. (`session_context_prompts` references prompts by id with no copy;
that is a precedent for referencing live session state, not a model for a
historical record.)

### 2.6 One namespace per team, decided now

A prompt command `/revue` and a future team skill named `revue` would collide.
The collision surfaces only when custom skills ship, but by then teams will
have authored commands that cannot be renamed without breaking their users'
habits.

Proposal: **commands and future team skills share one namespace per team**, and
uniqueness is validated across both. While only prompts exist, that is a
same-table constraint; when custom skills arrive, their creation validates
against existing prompt commands and vice versa.

The alternative — a distinguishing prefix per kind (`/p:revue`, `/s:revue`) —
is rejected: it makes the user spell out an implementation detail, and the two
kinds are meant to feel like one palette.

---

### 2.7 Making the trigger discoverable

A trigger nobody knows about is a feature nobody uses, and nothing on screen
says `/` does anything. The composer carries **no placeholder at all** today,
so there is nothing to preserve and the rule is ours to set:

> **While the composer is empty**, focused or not, it reads *"Posez votre
> question, ou tapez / pour une commande"*. It disappears only once the user
> starts typing.

Ordinary placeholder behaviour, in other words. The hint is on screen when the
user arrives and stays until they actually write something, so it does not
depend on where the focus happens to be.

One caveat to carry into implementation: a placeholder is not an accessible
instruction. It is not reliably announced, and it disappears on the first
keystroke. Screen-reader users need the same hint on the field's accessible
description, not only in the placeholder.

The **Help Center pages (fr and en) are updated in the same change**. This is
not specific to this feature: a user-visible feature that needs any learning
at all ships with its Help Center entry, or it ships unusable for everyone who
was not in the room when it was designed.

### 2.8 Visual direction

Design-system tokens only — no raw colour, no arbitrary pixel value, no new
token invented for this work. Where a look already exists, reuse it rather
than re-deriving one.

**The command menu** takes the home-page spotlight's results container
(`HomeSearch.module.scss`), which already dresses exactly this kind of
floating list:

| | Spotlight today | Command menu |
| --- | --- | --- |
| Fill | `--surface-container-high` | same |
| Border | `1px solid --outline-muted` | same |
| Elevation | `--elevation-2` | same |
| Radius | `--radius-m` (16px) | **`--radius-s` (8px)** — tighter, it sits against the composer rather than floating free |
| Section title | `--on-surface-muted` | same |
| Row hover | `--state-on-surface-hover` | same |
| Row radius | `--radius-s` | same |

One section for now, titled **"Prompts de la bibliothèque"**. The heading
renders even with a single section: it is what makes the second one (§2.3) an
addition rather than a visual change.

**The placeholder** is `--on-surface-muted`.

**The command component in the transcript** (§2.5) sits inside the user
bubble, which `MessageBubble.module.css` fills with `--secondary-container`
over `--on-secondary-container`. It must read as part of that bubble, not as a
card dropped onto it:

- no fill of its own — the bubble's `--secondary-container` shows through
- a subtle `1px solid --outline-muted` outline to mark it as actionable
- `--radius-xs` (4px), well inside the bubble's own `--radius-m` (16px) — a
  clearly tighter corner, so the component reads as nested rather than as a
  second bubble
- hover through `--state-on-secondary-container-hover`, the state layer built
  from the bubble's own content colour. Not a generic surface tone: a state
  layer must be mixed from the majority content colour of the surface it sits
  on, which here is `--on-secondary-container`.

---

## 3. Impact on existing contracts

- `PromptRow` gains a nullable `command` column plus a per-team unique
  constraint. One Alembic revision, re-parented on the current `swift` head.
- The product contract's prompt payloads gain the field; the generated frontend
  client is regenerated in the same change
  (`make update-control-plane-api`).
- `RichInputField` gains an optional trigger seam. It is a shared molecule —
  the search bar and other hosts must keep their current behaviour, so the
  trigger is opt-in per host, not built into the textarea.
- The user turn's `metadata_json` gains a command descriptor (§2.5). Its
  `parts_json` keeps the assembled text, exactly as any other turn, so an
  unaware reader renders it as plain text — additive, not breaking.
- The chat transcript gains one component for a command turn, and it is the
  only place that reads the descriptor.
- No runtime, agent or capability change. Resolving a command is a composer
  action; the turn that follows is an ordinary turn — the agent receives the
  assembled text and knows nothing about commands.

---

## 4. Non-goals

- Making platform skills (#2711) user-invocable. They are model-facing by
  design and stay that way.
- Building team custom skills, or their section of the menu.
- Named or structured parameters (`/revue doc=42`). Trailing text is plain
  continuation (§2.4); parsing it is a separate design.
- Personal (non-team) commands, beyond what the reserved `personal` team
  already gives every user.
