# Story 05 — Space-aware analyze endpoint + save processor folder resolution

**Area:** agentic-backend (controller + processor wiring)
**Depends on:** Story 01 (schema fields), Story 03 (resolve_and_validate_images + FolderResolver),
Story 04 (KfTagClient.resolve_folder)
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

Make the inline **analyze** endpoint and the **save** processor space-aware: both collect every
`folder` in the notes, resolve it against the current space (team or personal), and surface
`folder_not_found` / `image_key_invalid_location`, persisting the resolved `folder_tag_id` into the
schema on save.

## Analyze endpoint (`agent_controller.py`)

Current: `POST /agents/ppt-filler/analyze` accepts only `file` + authenticated `user`, returns
`200 { schema, errors }`.

Change:
- Accept an **optional `team_id`** (Form field alongside the multipart file, or query param —
  pick whichever is cleanest with `UploadFile`; a `Form(None)` field is simplest since the body is
  already multipart). The frontend will send it (Story 07).
- Build a `FolderResolver` backed by `KfTagClient`:
  - owner scope = `OwnerFilter.TEAM` + `team_id` when `team_id` is provided, else
    `OwnerFilter.PERSONAL` (user scope).
  - The KfTagClient needs an auth context. The analyze endpoint has the `access_token`
    (`Security(oauth2_scheme)`) — construct the client with it (mirror `_LazyWorkspaceAssetStore`
    / how `KfWorkspaceClient(access_token=...)` is built in the controller). NOTE: `KfTagClient`
    as drafted takes `agent=...`; add an `access_token=...` path or build it the same way
    `KfDocumentClient`/`KfWorkspaceClient` allow a token-only construction. Reuse
    `KfBaseClient`'s existing token-based constructor support.
- Pipeline: `result = parse(bytes)` → `result = await resolve_and_validate_images(bytes, result,
  resolver)` → return `200 { schema, errors }` (schema now carries `type`/`folder`/`folder_tag_id`,
  errors now include the image codes). Still 200 even with errors.
- `PptFillerAnalyzeResponse` already serializes the schema via the parser models — since `KeyField`
  gained fields (Story 01), they flow through automatically. Verify the response model still
  validates.

Keep the existing non-pptx → 400 behavior.

## Save processor (`ppt_filler_processor.py`)

Current `process(self, params, *, agent_id, store)` re-parses uploaded bytes and persists the
schema, failing 422 on parse errors.

Change:
- The processor must resolve folders within the **agent's space**. It needs the owner scope
  (team_id) and an auth context for KF. Extend the `ToolkitAssetProcessor.process` signature OR
  pass scope another way:
  - **Recommended:** extend the generic seam minimally. Add optional kwargs to `process`:
    `process(self, params, *, agent_id, store, team_id=None, folder_resolver=None)`. Update the
    abstract base (`toolkit_asset_processor.py`) and the generic hook in
    `agent_service._run_toolkit_asset_processors` to pass `team_id=agent_settings.team_id` and a
    constructed resolver. Keep it backward compatible (defaults None) so other providers are
    unaffected.
  - The resolver in the save path must use the SAME auth as the asset store. The store is built
    from the request `access_token` (`_build_asset_store`). Build the resolver from the same token
    (extend `_build_asset_store` to also return/construct a resolver, or add a parallel
    `_build_folder_resolver(access_token, team_id)` in the controller and thread it through
    `AgentService.update_agent` / `create_*` into `_run_toolkit_asset_processors`).
- On upload bytes present: parse → resolve_and_validate_images(bytes, result, resolver) → if any
  errors (parse OR image) → raise `ToolkitAssetValidationError(errors)` (→422). Else upload blob,
  persist schema **with folder_tag_id filled in**, strip the upload field (unchanged invariant).
- States 2 (no-op pass-through) and 3 (asset required reject) unchanged.

> The save path is the source of truth (RFC): a saved agent must never reference a non-existent
> folder. So `folder_not_found` at save time is a hard 422, same as a parse error.

## Frontend contract

The analyze request gains optional `team_id`. Story 07 sends it. The OpenAPI regen (Story 07)
picks up the new request field + schema fields.

## Tests

- **Analyze (controller smoke)**: extend `agentic_backend/tests/test_ppt_filler_analyze_controller.py`.
  The existing tests have no KF backend; inject/fake the resolver. Easiest: patch the resolver
  factory the endpoint uses so it returns a fake (known folders). Assert:
  - a deck with an image key whose folder is known → 200, schema key has `type:"image"` and a
    `folder_tag_id`, no `folder_not_found`.
  - a deck with an image key whose folder is unknown → 200 with `folder_not_found` (slide, key).
  - team_id is accepted and forwarded to the resolver with TEAM scope (assert via the fake).
  - existing text-only tests still pass (no resolver calls, no new errors).
- **Processor**: extend `agentic_backend/tests/test_ppt_filler_processor.py`. Pass a fake resolver
  + team_id. Assert:
  - valid image template (folder resolves) → schema persisted with `folder_tag_id`, bytes stripped.
  - unknown folder → `ToolkitAssetValidationError` carrying `folder_not_found`; nothing uploaded.
  - personal vs team scope honored (resolver receives the right owner_filter/team_id).
  - existing text-template processor tests still pass.

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- Existing analyze + processor + save-controller tests still pass.
- Committed with `feat(ppt-filler): make analyze and save space-aware for image folders`.
</content>
