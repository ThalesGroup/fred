# Story 07 — Frontend: form sends space context, renders new errors, OpenAPI regen

**Area:** frontend
**Depends on:** Story 05 (analyze endpoint accepts team_id, schema carries new fields + new error
codes exist server-side)
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

The agent-creation PPT Filler form sends the current space context (optional team id) to analyze,
and renders the new image error codes the same way it renders the existing two (group by code, then
slide; i18n by code, fall back to server message). Regenerate OpenAPI types.

## Files

- `frontend/src/rework/components/pages/TeamAgentsPage/AgentCreateEditModal/PptFillerForm/PptFillerForm.tsx`
- `frontend/src/slices/agentic/agenticApiEnhancements.ts` (multipart override — add team_id)
- `frontend/src/components/agentHub/toolParams/toolParamsRegistry.tsx` (pass `teamId` through —
  it already accepts a `teamId` arg in `render`; PptFillerForm must destructure it)
- `frontend/src/locales/en/translation.json` and `frontend/src/locales/fr/translation.json`
  (new error-code headings)
- `frontend/src/slices/agentic/agenticOpenApi.ts` (REGENERATED — do not hand-edit)

## Steps

1. **Regenerate OpenAPI types** AFTER the backend stories land:
   - From `frontend/`: `make update-agentic-api` (runs `cd ../agentic-backend && make
     generate-openapi` then the RTK codegen). This refreshes `KeyField` (now has `type`,
     `folder`, `folder_tag_id`), `PptFillerParams`, and the analyze request type (now has
     optional `team_id`).
   - If `make generate-openapi` can't run in this environment, regenerate from a freshly built
     `agentic-backend/openapi.json`; if that's also unavailable, hand-add the minimal type deltas
     and leave a TODO comment, and note it in the commit.

2. **Pass `teamId` into the form**: `toolParamsRegistry`'s `render(params, onChange, teamId)`
   already forwards `teamId`. Update `PptFillerForm`'s props (`ToolParamsProps<T>` already includes
   optional `teamId`) to destructure `teamId` and use it.

3. **Send `team_id` to analyze**: in `agenticApiEnhancements.ts`, the multipart override appends
   `file` to `FormData`. Add the team id when present: append `team_id` to the same `FormData`
   (matches the backend `Form(None)` field from Story 05). Thread `teamId` from the form's
   `analyze({...})` call into the query arg (extend the enhanced mutation's arg shape to carry an
   optional `teamId`).

4. **Render new error codes**: extend `ERROR_CODE_HEADING_I18N` in `PptFillerForm.tsx` with the new
   codes → i18n heading keys:
   - `unknown_metadata`, `unknown_type`, `duplicated_metadata`, `image_without_folder`,
     `empty_folder`, `folder_without_image_type`, `folder_not_found`, `image_key_invalid_location`.
   The existing `groupErrors()` (group by code, then slide, collect keys) needs no change — it's
   already code-agnostic. The existing fallback (server `message` for unmapped codes) covers any
   gap, but add all eight so messages are localized.

5. **i18n catalog**: add headings under
   `agentTuning.fields.ppt_filler.errors.<code>.heading` in BOTH `en` and `fr`. Suggested English:
   - `unknown_metadata`: "Unknown metadata keyword (use only `type` or `folder`):"
   - `unknown_type`: "Unknown type value (use `text` or `image`):"
   - `duplicated_metadata`: "Metadata declared twice in one key block:"
   - `image_without_folder`: "Image keys missing a folder:"
   - `empty_folder`: "Folder value is empty:"
   - `folder_without_image_type`: "A folder was set on a non-image key:"
   - `folder_not_found`: "Folder not found in your space:"
   - `image_key_invalid_location`: "Move these image keys into a text box or rectangle (a table
     cell cannot hold an image):"
   Provide natural French equivalents.

6. Optionally surface `type`/`folder` in the per-slide schema preview (e.g. an "image" chip + the
   folder next to image keys). Keep minimal; not required for correctness.

## Tests / checks

- `make lint` / typecheck in `frontend/` (use the project's existing target, e.g. `make
  code-quality` or `npm run lint` + `tsc`). Ensure no type errors from the regenerated types.
- The frontend has limited unit coverage for this form; rely on type-checking + the E2E browser
  pass (separate). Do not invent a heavy test harness.

## Done when

- Frontend builds / typechecks; new error codes render with localized headings; analyze sends
  `team_id` when the agent is team-scoped.
- Committed with `feat(ppt-filler): send space context and render image errors in the form`.
</content>
