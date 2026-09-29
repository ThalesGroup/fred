## Why

A team's prompts are reachable only through the prompt-library side panel: open
it, find the prompt, insert it, send it. `PROMPT-COMMAND-TRIGGER-RFC.md` closes
that gap with a `/` trigger in the composer, and the trigger needs something to
match against.

This change delivers only that foundation — the field, its rules, and its
editing surface. It ships useful on its own (a team can author and see its
commands) and it unblocks the composer slice, which is where the keystroke
lives.

## What Changes

- A prompt gains an optional `command`: the string that will run it from the
  composer. It is **not** the prompt's name — `name` is display text that
  allows spaces and mixed case, and an autocompletion cannot tell where a
  multi-word token ends.
- Accepted form: lowercase ASCII letters, digits, `-` and `_`, up to 64
  characters. No whitespace, no accented characters. The input field prevents
  anything else from being typed — folding an uppercase keystroke to lowercase
  as it happens — and the API rejects a non-conforming value rather than
  repairing it.
- Unique per team, **guaranteed by the database**. The existing
  `uq_prompt_team_name` covers `name` only.
- Uniqueness is reserved across one namespace per team, shared with the future
  team-scoped custom skills (RFC §2.6). Nothing about skills is built here; the
  decision is recorded so commands authored now do not have to be renamed
  later.
- The prompt create/edit surface gains the field, with its own validation
  message. Typing a command another prompt of the team already holds is
  refused, with the conflict shown on that field.
- An import **keeps** the command, and resolves a collision the way the
  prompt's name already does: the copy takes the first free `-N` variant,
  starting at `-2`. An import is therefore never refused, never blocked, and
  never needs explaining because of a command — choosing destinations is
  unaffected by what commands each team holds.
- The prompt's own team renders **selected and locked** in the destination
  picker rather than as an empty disabled checkbox, which states the opposite
  of the truth. It is never submitted as a target.

Not breaking: the column is nullable, a prompt without a command behaves
exactly as today, and every existing prompt keeps working untouched.

## Capabilities

### New Capabilities

- `prompt-commands`: a team prompt can carry a command that identifies it for
  invocation from the chat composer — its accepted form, its uniqueness within
  a team, and how it behaves when a prompt is published or imported. Later
  slices of the RFC extend this same capability with the composer trigger and
  the transcript rendering.

### Modified Capabilities

None. No capability spec exists yet for the prompt library
(`openspec/specs/` holds `deep-agent-todo-panel`,
`frontend-application-hosting`, `frontend-package-archives` and
`platform-announcements`), so there is no existing requirement to amend.

## Impact

**Backend — `apps/control-plane-backend`**

- `models/prompt_models.py`: `PromptRow` gains a nullable `command` column and
  a partial unique index on `(team_id, command)` where `command IS NOT NULL`.
- One Alembic revision, parented on the current head of the backend's own
  history.
- `product/schemas.py`: `CreatePromptRequest` and `UpdatePromptRequest` gain
  the field with its validation; `PromptSummary` and `PromptDetail` expose it,
  and `MarketplacePromptSummary`/`MarketplacePromptDetail` inherit it — which
  is what lets an import read the command.
- `prompts/store.py`: `PromptRecord` carries the field; the store refuses a
  duplicate with its own error, distinct from the name conflict.
- `product/service.py`: `import_published_prompt_into_team` copies the
  command, picking the first free `-N` variant through a helper sibling to the
  existing `_next_imported_name`.

**Frontend — `apps/frontend`**

- `controlPlaneOpenApi.ts` regenerated in the same change
  (`make update-control-plane-api`), per the generated-client rule.
- `PromptsPage.tsx`: the create/edit form gains the field, with input
  filtering and the conflict message. The page already owns the POST and PUT
  mutations.
- `ImportPromptDialog.tsx`: the author's team rendered selected and locked.
  Nothing else — the picker does not consult commands at all.
- Translations for the label, helper text and conflict message, `fr` and `en`.

**Out of scope for this slice**

The `/` trigger, the command menu, the transcript component, and the Help
Center pages. They belong to the slices that make the field user-visible in
the chat; documenting a field nobody can use yet would be premature.

Also out of scope, and its own change: `EDITOR_RELATIONS` in
`ImportPromptDialog.tsx` and `MarketplacePrompts.tsx` treats `team_admin` as
an editor, while the import endpoint requires `can_update_resources`, which
`schema.fga` grants to `team_editor` alone. Admin-only teams are offered and
then refused per target. A live authorization bug, unrelated to commands.
