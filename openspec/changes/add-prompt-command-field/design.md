## Context

See proposal.md — Why. The behaviour contract is in
`specs/prompt-commands/spec.md`; this document covers only how it is reached.

Three facts about the existing code shape the approach:

- `PromptRow` (`models/prompt_models.py`, table `prompt`) already carries
  `UniqueConstraint("team_id", "name", name="uq_prompt_team_name")`. The
  command needs its own constraint; it cannot ride on that one.
- `MarketplacePromptSummary` and `MarketplacePromptDetail` **inherit** from
  `PromptSummary` and `PromptDetail`, so adding the field to the team
  projections exposes it in the marketplace ones too. Here that is wanted: the
  import reads the command from those payloads.
- `import_published_prompt_into_team` already resolves a name collision by
  suffixing: `_next_imported_name` walks `{base}_imported-N` until the name is
  free in the target team, trimming the base to 230 characters to stay inside
  the column. The command gets the same treatment, so this slice adds a
  sibling helper rather than a new mechanism.

The backend's Alembic head is `b88202b8451e` at the time of writing.

## Goals / Non-Goals

**Goals:**

- Uniqueness guaranteed by storage, so no concurrent pair of writes can cross it.
- An import that never fails, and never has to be explained, because of a command.
- No persistent "broken" prompt anywhere in the model.

**Non-Goals:**

- Any composer behaviour. Nothing in this slice reads a command at runtime.
- A skills table. The namespace requirement is discharged by where uniqueness
  lives, not by new machinery.
- Backfilling commands for existing prompts. They stay without one.
- Fixing which teams the destination picker offers. `EDITOR_RELATIONS` in
  `ImportPromptDialog.tsx` and `MarketplacePrompts.tsx` counts `team_admin` as
  an editor, but `schema.fga` reads `define can_update_resources: team_editor`
  and the import endpoint requires exactly that permission — so an admin-only
  team is offered and then refused per target. A real bug, unrelated to
  commands, and its own change.

## Decisions

**Enforce uniqueness in the database.** A partial unique index on
`(team_id, command)` where `command IS NOT NULL`: any number of prompts may
have no command, a present one is unique per team. A service-only check races
under concurrent writes, and the constraint is what makes the guarantee true
rather than usually true. It also stays the backstop for the import path
below, where two concurrent imports into one team could otherwise pick the
same free suffix.

Alternative rejected: a plain unique constraint on `(team_id, command)`.
PostgreSQL treats NULLs as distinct so it would happen to work, but it states
the wrong intent and breaks the day someone stores `""` instead of NULL.

**Resolve an import collision by suffixing, not by refusing.** The copy takes
the first free `{base}-N` starting at `N=2`. A prompt whose command is free
keeps it unchanged — unlike the name, which is always suffixed even on a first
import, because a command is meant to be typed and `summary` is worth keeping
when nothing claims it.

This mirrors `_next_imported_name` closely enough that the helper should sit
next to it and read the same way. Two differences to keep straight: the
command suffix is `-N` (a name uses `_imported-N`, which is not a legal
command), and it only applies on collision.

Alternative rejected (chosen earlier in this change's design, then dropped):
blocking a colliding team in the destination picker. It kept every command
author-chosen, but it cost a per-team command lookup before the picker could
render, a blocked row with an error indicator and an accessible explanation
naming the offending prompt, and a dead end for a user who only wanted the
prompt's text. Suffixing removes all of it and matches what the name already
does — a user who sees `summary-2` understands it without being taught.

Alternative rejected (earlier still): allowing duplicates and computing
ownership by first-come precedence. It bought a smoother import at the cost of
the storage guarantee, a derived-ownership rule, a persistent conflict state,
a flag on every listing payload and an error badge on library tiles.

**Leave the typed path refusing.** Suffixing is right for a copy the user did
not author; it is wrong for a command someone is typing right now. A create or
update carrying a taken command still gets a 409 naming the field, and the
form shows "Label de commande déjà pris par un autre prompt d'équipe".
Silently turning what they typed into `summary-2` would hand them a command
they never chose.

**Cap the command at 64 characters, and trim the base before suffixing.**
`_next_imported_name` reserves room inside the 255-character name column the
same way. 64 is generous for something meant to be typed after a `/` and
leaves the suffix room without arithmetic at the call site.

**Show the author's team as selected and locked.** It already holds the
prompt, so an empty disabled checkbox states the opposite of the truth. The
`Checkbox` atom is a native input, so `checked={isOrigin || selected.has(id)}`
alongside the existing `disabled={isOrigin}` is the whole change — a disabled
input fires no `onChange`, so `selected` cannot be reached through it. No
overlay: a decorative tick drawn over a real unchecked input leaves assistive
technology reading the input, which still says unchecked.

Implementation trap worth pinning with a test: `selected` is the set the
confirm handler submits. The author's team must be *rendered* checked without
*being* in that set, or the import will target the team that already owns the
prompt.

**Store the absence of a command as NULL, and normalise empty to NULL at the
edge.** Two representations of "no command" (`NULL` and `""`) would make every
later query ask about both. The request schema coerces empty or
whitespace-only input to `None` before validation; from there only `NULL`
reaches the column.

**Validate with a pattern on the request schemas, and reject.**
`^[a-z0-9_-]{1,64}$` on `CreatePromptRequest` and `UpdatePromptRequest`, which
gives a 422 naming the field for free. The API never repairs input: a caller
sending `Résumé` gets an error, not `resume`.

The input field is where the user is helped instead. It folds an uppercase
keystroke to lowercase as it is typed and refuses every other disallowed
character, so the rejection path is a backstop for non-browser callers rather
than something a person meets. Folding in the field is visible the instant it
happens; folding on the server would hand someone a command they never chose.

**Raise a distinct store-level error for a command conflict.** `PromptStore`
already raises `PromptAlreadyExistsError` for a name collision. A sibling
error for the command lets the API answer 409 with the offending field named,
which the form needs to highlight the right input. Catching a generic
integrity error and guessing which constraint fired would mean parsing the
constraint name out of the driver's message.

**Copy the command on import.** One more field in
`import_published_prompt_into_team`'s explicit list. This is the opposite
treatment from `category_id`, which that function deliberately omits — a
category is an id pointing at a row the destination team does not have, while
a command is a plain string meaning the same thing everywhere. Worth a comment
at the call site so the apparent inconsistency is not "fixed" later.

## Risks / Trade-offs

**An imported command can drift from what the author chose**, and a team that
imports the same prompt twice ends up with `summary-2` and `summary-3`. → The
name already behaves this way (`_imported-1`, `_imported-2`), so the result is
consistent rather than surprising, and the destination team can rename the
command in the prompt form. Nothing breaks: each command still resolves to
exactly one prompt.

**A base command ending in a digit suffix compounds**: importing a prompt
whose command is `summary-2` into a team that holds it yields `summary-2-2`.
→ Ugly, correct, and rare. Special-casing it would mean parsing a trailing
number back out of a user-authored string, which misreads `plan-2024`.

**Two concurrent imports into one team can pick the same free suffix.** → The
partial unique index refuses the loser, surfaced as a per-team conflict
through the existing result array — the same shape as the name path's existing
race comment. The endpoint already dedupes repeated target ids within one
request, so this needs two separate requests to happen at all.

**A partial index is PostgreSQL-specific.** → The backend targets PostgreSQL
and every other prompt constraint already lives there. SQLite supports partial
indexes too, so the test suite is unaffected.

**Adding the field to `PromptSummary` widens every listing payload.** → One
short optional string per prompt, next to `text_preview`, `tags` and seven
counters.

**Nothing enforces the shared namespace yet**, because the other kind of
object does not exist. → Uniqueness lives on the team, so a second kind of
invocable object validates against the same scope when it arrives. Recorded in
the spec so it is not quietly re-scoped later.

## Migration Plan

One Alembic revision parented on the backend's current head (`b88202b8451e` at
time of writing — re-parent on the real head at implementation time, per the
repo's one-head rule):

1. Add the nullable `command` column.
2. Create the partial unique index on `(team_id, command)`.

No data migration: every existing row gets `NULL` and keeps working. Downgrade
drops the index then the column, losing authored commands — the expected cost
of reverting the feature, stated in the migration note.

Deployment order does not matter: an older frontend ignores an unknown field,
and a newer frontend against an older backend sends a field the API rejects as
unknown — the same failure shape as any other field addition.
