## Why

Prompt libraries grow, and the prompts a user reaches for most get lost among the rest. Scrolling or searching for the same few prompts every time is friction, both on the Prompts page and in the chat's prompt panel.

Tracked by [GitHub issue #2901](https://github.com/ThalesGroup/fred/issues/2901).

## What Changes

- Each user can mark any prompt they can read as a favorite, in a team library or in their personal space. Favorites are personal: no one else sees them.
- Prompt tiles get a star button next to the more button: outline when not a favorite, filled in `warning` when it is.
- The Prompts page gets a "Favorites" chip, first in the filter row and always visible. It combines with the category filter. At rest it is neutral with a filled `warning` star; active, it fills with `warning` and its star and label turn `on-warning`.
- The chat's prompt panel gets the same chip, on the row of the search field, in both the Team and My space tabs.
- Favorites are stored in the control-plane database. They are removed with their prompt, when the user leaves or is removed from the prompt's team, and when the user's account is deleted.
- The Help Center Prompts page (fr and en) explains favorites.

## Capabilities

### New Capabilities

- `prompt-favorites`: marking library prompts as personal favorites and filtering on them.

### Modified Capabilities

None.

## Impact

- **Control plane**: new `prompt_favorite` table and Alembic migration; a favorite store; two routes (`PUT` / `DELETE /teams/{team_id}/prompts/{prompt_id}/favorite`); an `is_favorite` field on `PromptSummary` and `ContextPromptSummary`; cleanup in `remove_team_member` and `delete_user`.
- **Contract**: `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.6 Prompt library, plus a dated entry.
- **Frontend**: regenerated control-plane client; `PromptCard`; a shared favorites filter chip; `PromptsPage`; `PromptSelectionChatPanel`; translations; Help Center.
- No new dependency. Operator impact: a schema migration applied by the normal `db-upgrade`.
