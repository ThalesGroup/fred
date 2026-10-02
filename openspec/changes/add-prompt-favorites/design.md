## Context

Prompts live in the control-plane `prompt` table (`prompt_id` string PK, `team_id`). The personal space is an ordinary team, `personal-{uid}`. The list route `GET /teams/{team_id}/prompts` returns `PromptSummary` and requires `CAN_USE_TEAM_AGENTS`; the chat panel reads `GET /teams/{team_id}/prompts/context` (`ContextPromptSummary`) for each tab. Leaving and removing a member share one path, `teams/service.py::remove_team_member`. Account deletion (`users/service.py::delete_user`) currently purges no per-user database rows.

## Goals / Non-Goals

**Goals:** Per-user favorites on library prompts, a filter on them in both surfaces, and no orphaned personal data.

**Non-Goals:** Sorting favorites first, favorites in the Marketplace or the `/` command picker, sharing favorites, or a favorites count anywhere.

## Decisions

- **Storage.** Table `prompt_favorite (user_id String, prompt_id String FK → prompt.prompt_id ON DELETE CASCADE, created_at)`, primary key `(user_id, prompt_id)`, index on `user_id`. A favorite exists or it does not; there is no "unfavorited" row.
- **API.** `PUT /teams/{team_id}/prompts/{prompt_id}/favorite` and `DELETE` on the same path, both idempotent, `204`. Permission `CAN_USE_TEAM_AGENTS`, the same as reading the prompt, so read-only members can favorite. The prompt must belong to the team (`404` otherwise).
- **Read model.** `PromptSummary` and `ContextPromptSummary` gain `is_favorite: bool`, computed for the caller with one lookup per list request (the caller's favorites among the returned ids), not one per prompt.
- **Cleanup.** Prompt deletion relies on the foreign-key cascade. `remove_team_member` deletes the removed user's favorites on that team's prompts in one statement (`prompt_id IN (SELECT prompt_id FROM prompt WHERE team_id = :team)`). `delete_user` deletes all of the user's favorites. The favorite store joins `TeamServiceDependencies` and the users service dependencies.
- **Tile.** `PromptCard` takes `isFavorite` and `onToggleFavorite`; the star renders only when `onToggleFavorite` is passed, so the Marketplace and the `/` picker do not show it. The toggle is optimistic and rolls back on error with a toast.
- **Filter chip.** `FilterChips` has no icon slot and `Chip` is not interactive, so a small shared `FavoritesFilterChip` (toggle button, `aria-pressed`) serves both surfaces. It takes the size of its neighbours: the `FilterChips` chips on the Prompts page, the `xs` search field in the chat panel.
- **Prompts page.** The chip renders first in the filter row, outside the `categories.length > 0` guard, so it shows even without categories. Filtering is the AND of favorites and the active category.
- **Chat panel.** The search field and the chip share a row, the chip after the field; the category `Select` stays below, unchanged. The chip is therefore always present, with or without categories. The filter state is per panel and resets with the tab, like the category.

## Risks / Trade-offs

- A user's favorites on a team they left are deleted, so rejoining starts from none. Accepted: it was asked for.
- `delete_user` gains a database dependency it did not have; the Keycloak deletion stays the last step so a database failure does not leave a deleted account with live data.
