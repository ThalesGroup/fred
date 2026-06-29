# PPT Filler — Image Support — Story Breakdown

Decomposition of [`../PPT-FILLER-IMAGES-RFC.md`](../PPT-FILLER-IMAGES-RFC.md) into independently
implementable stories. Each story is a self-contained markdown spec handed to one sub-agent.
All work lands on branch **`image-support-in-ppt-filler`** (commit per story).

## Dependency order (implement top to bottom)

| # | Story | Area | Depends on |
|---|-------|------|------------|
| 1 | [`story-01-parser-metadata.md`](./story-01-parser-metadata.md) | Backend — notes metadata parsing + schema fields | — |
| 2 | [`story-02-image-anchor-traversal.md`](./story-02-image-anchor-traversal.md) | Backend — shape-walking geometry traversal | — |
| 3 | [`story-03-folder-resolution-validation.md`](./story-03-folder-resolution-validation.md) | Backend — folder→tag resolution seam + new error codes | 1 |
| 4 | [`story-04-kf-client-methods.md`](./story-04-kf-client-methods.md) | Backend — KF tag-resolution + raw-bytes client methods | — |
| 5 | [`story-05-analyze-save-space-aware.md`](./story-05-analyze-save-space-aware.md) | Backend — space-aware analyze endpoint + save processor | 1,3,4 |
| 6 | [`story-06-fill-tool-images.md`](./story-06-fill-tool-images.md) | Backend — fill tool image branch | 1,2,4 |
| 7 | [`story-07-frontend.md`](./story-07-frontend.md) | Frontend — form, i18n, OpenAPI regen | 5 |
| 8 | [`story-08-help-docs.md`](./story-08-help-docs.md) | Frontend — help-page docs (authoring + errors) | 1,3 |

Stories 1, 2, 4 have no dependencies and can run in parallel first.
Stories 3, 6 depend on 1 (+ 2/4). Story 5 is the integration point. 7/8 are frontend.

## Shared contract (read before any story)

The per-key schema gains three fields (RFC "Schema shape"):

- `type`: `"text"` | `"image"` (default `"text"` — backward compatible)
- `folder`: the author's folder string (display/messages); only for image keys
- `folder_tag_id`: the resolved DOCUMENT tag id; only for image keys after resolution

New error codes (all reuse the `{slide, key, code, message}` contract):

- `unknown_metadata`, `unknown_type`, `duplicated_metadata`, `image_without_folder`,
  `empty_folder`, `folder_without_image_type`, `folder_not_found`, `image_key_invalid_location`

Image keys also reuse `key_without_description` and `described_but_not_in_slide` unchanged.

## Conventions every story must follow

- Run `make code-quality` and `make test` in each touched project before committing.
- Keep default tests offline & fixture-driven (decks built in-test with python-pptx).
- Commit on `image-support-in-ppt-filler` with a `feat(ppt-filler):` / `test(ppt-filler):` message.
  Do NOT mention Claude in commit messages.
- Keep scope minimal; reuse existing conventions and helpers.
</content>
</invoke>
