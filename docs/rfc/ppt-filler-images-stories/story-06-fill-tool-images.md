# Story 06 — Fill tool image branch

**Area:** agentic-backend (chat-time fill tool)
**Depends on:** Story 01 (schema `type`/`folder`/`folder_tag_id`), Story 02 (image anchors),
Story 04 (`fetch_raw_content`)
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

At chat time, let the agent place a chosen image into an image `{{key}}`'s shape box, remove
unfilled image slots, and fail loudly on a bad image pick (hard) vs. proceed-and-explain on a
missing folder (soft). Text keys behave exactly as today.

## File

- `agentic-backend/agentic_backend/integrations/ppt_filler/toolkit.py` (edit `build_ppt_filler_tools`)
- `agentic-backend/tests/test_ppt_filler_toolkit.py` (extend)

## Args schema changes (`_build_args_schema`)

Today every leaf is a **required** `str`. Change:

- **All leaf keys become OPTIONAL** (RFC: leaf keys become optional). Default `None`.
- For an **image** key, the leaf's description must instruct the agent to:
  - browse its folder by `folder_tag_id` with the existing `list_document_tree` tool
    (mention the folder string for human context),
  - pick the document that fits and pass that **document id** as the key's value,
  - if the folder is missing/empty, do its best and explain to the user that an owner/editor must
    fix the folder.
  Include the `folder_tag_id` in the description text so the agent has the id to browse.
- For a **text** key, keep today's behavior (description = note description; optional string).

The per-slide grouping (`slide_<n>`) and `output_file_name` stay as they are.

## Fill behavior

Iterate slides as today. For each slide, separate text vs image keys using the persisted
`SlideSchema.keys[*].type`:

- **Text keys**: fill via the existing `replace_keys_on_slide` (an omitted text key → empty string,
  as today).
- **Image keys**: use `list_image_anchors_on_slide` (Story 02) to find each anchor for that key on
  the slide.
  - If the agent **provided a document id** for the key:
    - fetch original bytes via `KfDocumentClient.fetch_raw_content(document_uid=<id>)`.
    - If the fetch fails OR the bytes are not a usable image (python-pptx
      `add_picture` raises, or PIL/`UnidentifiedImageError`): **HARD fail** the whole fill
      (return `is_error=True` with a message telling the agent to re-pick). This is the agent's
      correctable mistake.
    - Else, for EACH anchor of that key on the slide:
      - compute a fit-inside box: scale the image to fit within (anchor.width, anchor.height)
        preserving aspect ratio, centered within the box. Use the image's pixel dimensions
        (via `PIL.Image.open` on the bytes) to get the aspect ratio; convert to EMU.
      - `slide.shapes.add_picture(io.BytesIO(bytes), left, top, width, height)` at the centered,
        fit-inside geometry.
      - remove the placeholder shape (the anchor's `shape`): `shp = anchor.shape;
        shp._element.getparent().remove(shp._element)`.
    - An image key in a **table cell** anchor (`invalid_location=True`) must be refused at fill —
      this should not happen for a saved agent (save rejects it), but guard: skip/hard-fail with a
      clear message rather than crash.
  - If the agent **omitted** the key (None): remove every placeholder shape for that key on the
    slide (so no empty box remains). Do NOT insert a picture.

Keep the kept-notes stripping (`apply_kept_notes_to_slide`) and the upload→LinkPart output exactly
as today.

> Centering math: given image aspect `ar = img_w/img_h` and box `(W,H)`:
> if `W/H > ar`: fit height → `h=H, w=H*ar, top=box_top, left=box_left+(W-w)/2`
> else: fit width → `w=W, h=W/ar, left=box_left, top=box_top+(H-h)/2`.

## Soft vs hard (RFC chat-time policy)

- **Missing folder** (folder tag no longer resolves): SOFT. The agent is told via the tool/key
  description to proceed and explain. Nothing special at fill time — the agent simply won't pass a
  doc id (or passes one it found elsewhere). No hard failure for "folder gone".
- **Bad document id** (cannot fetch / not an image): HARD. Fail the fill so the agent re-picks.

## Tests (fake the document fetch)

Extend `test_ppt_filler_toolkit.py`. Build a small in-test deck + a `PptFillerParams` whose schema
marks a key `type:"image"` with a `folder_tag_id`. Monkeypatch / inject a fake
`fetch_raw_content` returning a tiny valid PNG (generate one in-test with PIL, e.g. a 10x10 red
square) and the workspace upload. Assert:

- providing a doc id for an image key → the placeholder shape is removed and a picture is added;
  re-opening the saved deck shows a picture and no `{{key}}` text. (Assert via python-pptx: the
  output has a picture shape and `list_keys_on_slide` is empty.)
- fit-inside, aspect-preserving geometry: picture width/height ≤ box, aspect ratio preserved
  (allow rounding tolerance).
- image key in TWO shapes → a picture inserted in both; both placeholders removed.
- omitted image key → placeholder shape removed, NO picture added.
- bad image bytes (fake fetch returns `b"not an image"`) → fill returns `is_error=True` (hard
  fail), no silent drop.
- text keys still fill as before (round-trip text path unchanged).

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- Existing fill/toolkit tests still pass.
- Committed with `feat(ppt-filler): place chosen images and remove unused image slots`.
</content>
