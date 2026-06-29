# Story 03 — Folder-resolution seam + `folder_not_found` / `image_key_invalid_location`

**Area:** agentic-backend (parser/validator extension with an injectable resolver)
**Depends on:** Story 01 (metadata parsing + schema fields), Story 02 (image anchors)
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

Add the two **resolution/geometry-dependent** validations on top of Story 01's parser:

- `folder_not_found` — a non-empty `folder` that does not resolve to a folder in the current space.
- `image_key_invalid_location` — an image key in a shape that cannot hold a picture (table cell).

Both are driven through **injected seams** so the parser stays pure and offline-testable. The
actual Knowledge Flow lookup is Story 04; here we only define the seam and wire it into a
validate step that the analyze endpoint and save processor (Story 05) will call.

## Design

Story 01's `parse(pptx)` stays pure (no folder resolution). Add a thin **validation layer** that
takes a `ParseResult` (or re-parses) plus an injected folder resolver and an injected slide-anchor
source, and returns the augmented errors + the resolved `folder_tag_id` written back into the
schema.

Suggested API in a new module
`agentic_backend/integrations/ppt_filler/folder_resolution.py` (or extend `parser.py`):

```python
from typing import Protocol, Optional

class FolderResolver(Protocol):
    async def resolve(self, folder: str) -> Optional[str]:
        """Return the DOCUMENT tag id for `folder` (e.g. 'images/flags') in the current space,
        or None if it does not exist."""
        ...

CODE_FOLDER_NOT_FOUND = "folder_not_found"
CODE_IMAGE_KEY_INVALID_LOCATION = "image_key_invalid_location"

async def resolve_and_validate_images(
    pptx_source,                 # bytes | path
    parse_result,                # the Story-01 ParseResult (schema + base errors)
    resolver: FolderResolver,    # injected; fake in tests
) -> parse_result-like:
    """
    For every image key in the schema:
      - resolve its `folder` via `resolver`; on None → append folder_not_found (slide,key);
        on success → write folder_tag_id back into the KeyField.
      - check its anchor(s) via list_image_anchors_on_slide; if ANY anchor for that key on that
        slide has invalid_location=True → append image_key_invalid_location (slide, key).
    Returns the augmented result (same {schema, errors} contract).
    """
```

Notes:
- De-duplicate resolution: resolve each distinct `folder` string once per call (cache in a dict),
  not once per key — several keys may share a folder.
- `image_key_invalid_location` is per (slide, key): if a key is anchored in a valid shape AND a
  table cell, still report it (it's mislocated somewhere). Group keys by slide for the message,
  matching how the UI groups. The message (heading) should tell the author to move the key into a
  text box or rectangle.
- Resolution must be **async** (KF lookup in Story 04 is async). The analyze endpoint and save
  processor (Story 05) are already async.
- Only NON-EMPTY folders are resolved (empty/missing folder is already `image_without_folder`
  from Story 01 — do not double-report).
- Text keys are skipped entirely (no folder, no geometry constraint).

## Tests (offline, faked resolver)

In `agentic-backend/tests/` (new file `test_ppt_filler_folder_resolution.py` or extend the parser
test). Use a fake resolver, e.g.:

```python
class _FakeResolver:
    def __init__(self, known: dict[str, str]):  # full_path -> tag_id
        self.known = known
    async def resolve(self, folder: str):
        return self.known.get(folder)
```

Assert:

- existing folder → schema's image KeyField gets the expected `folder_tag_id`; no error.
- missing folder → `folder_not_found` with right slide + key; `folder_tag_id` stays None.
- two image keys sharing one folder → resolver called once (dedupe) and both keys get the id.
- image key in a table cell → `image_key_invalid_location` (slide, key). Build the deck with a
  `{{flag}}` in a table cell + notes declaring it `type: image, folder: images/flags`.
- empty/missing folder is NOT re-reported as folder_not_found (still just image_without_folder).
- team-vs-personal scope is the resolver's concern (the resolver is injected with a scope in
  Story 04/05); here just assert the resolver is called with the folder string.

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- Committed with `feat(ppt-filler): resolve folders and validate image locations`.
</content>
