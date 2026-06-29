# Story 02 — Image-anchor shape-walking traversal (geometry)

**Area:** agentic-backend (pure traversal, no I/O)
**Depends on:** nothing
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

The existing `traversal.py` flattens shapes to paragraphs and discards the containing shape, so
it cannot give an image its placement box. Add a **separate shape-walking traversal** that yields,
per `{{key}}` found in a shape's text, the **containing shape** and its **absolute geometry**
(left/top/width/height in EMU), plus a flag for shapes that cannot hold a picture (table cells).

This single utility drives BOTH the analyze-time `image_key_invalid_location` error (Story 03/05)
and the fill-time picture insertion (Story 06), so parse and fill can never diverge on geometry.

## File

- `agentic-backend/agentic_backend/integrations/ppt_filler/traversal.py` (add to it)
- `agentic-backend/tests/test_ppt_filler_anchors.py` (NEW file — do NOT edit
  `test_ppt_filler_parser.py`; another story owns it concurrently).

## What to add

A function that walks a slide's shapes (recursing into groups) and returns image-anchor records:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ImageAnchor:
    key: str               # the {{key}} found in this shape (stripped)
    left: int              # absolute EMU
    top: int               # absolute EMU
    width: int             # absolute EMU
    height: int            # absolute EMU
    shape: object          # the python-pptx shape (for fill-time removal/insertion)
    invalid_location: bool # True when the key sits in a table cell (cannot hold a picture)

def list_image_anchors_on_slide(slide) -> list[ImageAnchor]:
    ...
```

### Walking rules

Reuse `KEY_PATTERN` and the run-merging idea already in `traversal.py` (a key may be split across
runs; merge the runs of each paragraph before matching).

- **Top-level text box / autoshape** (`has_text_frame`, not a group, not a table): if its merged
  text contains `{{key}}`, yield an `ImageAnchor` with the shape's own `.left/.top/.width/.height`
  and `invalid_location=False`. One anchor per distinct key occurrence — if the same key appears
  in several shapes on the slide, yield one anchor per shape (the RFC: an image key in several
  shapes is filled in every shape).
- **Group children** (`shape_type == MSO_SHAPE_TYPE.GROUP`, i.e. has `.shapes` and not
  `has_text_frame`): recurse. A child's absolute geometry must be composed from the group
  transform. python-pptx exposes the group's child offset/extent via the group's
  `element` `chOff/chExt` and the group's own `off/ext`. Compute absolute coords:

  ```
  abs_left = group.left + (child.left - chOff_x) * (group.width  / chExt_cx)
  abs_top  = group.top  + (child.top  - chOff_y) * (group.height / chExt_cy)
  abs_w    = child.width  * (group.width  / chExt_cx)
  abs_h    = child.height * (group.height / chExt_cy)
  ```

  Nested groups compose multiplicatively — apply the transform at each level (carry an
  accumulated transform down the recursion). Read `chOff`/`chExt` from the group shape's XML
  (`grpSp/grpSpPr/xfrm` → `a:chOff`, `a:chExt`; offset `a:off`, extent `a:ext`). Guard against a
  zero child-extent (avoid div-by-zero → treat scale as 1.0).
- **Table cells** (`has_table`): a `{{key}}` inside any cell yields an `ImageAnchor` with
  `invalid_location=True`. Geometry is irrelevant (you may use the table shape's geometry or
  zeros); the flag is what matters. This drives `image_key_invalid_location` and is refused at
  fill.
- Any other shape (picture, media, chart, smartart) contributes no anchors (unchanged scope).

> Keep `list_keys_on_slide` and `replace_keys_on_slide` exactly as they are — they remain the
> TEXT round-trip seam. This new function is the IMAGE seam. They share the run-merging idiom but
> serve different outputs.

## Tests

Build decks in-test with python-pptx (reuse the `_build_group_deck` / `_build_table_deck` helpers'
pattern already in `test_ppt_filler_parser.py`):

- **Top-level shape → geometry**: a text box at a known left/top/width/height containing
  `{{logo}}` → anchor with those exact EMU values and `invalid_location=False`.
- **Group child → absolute geometry**: a text box inside a group; assert the returned absolute
  left/top/width/height equal the composed transform (build the group with known group off/ext and
  child chOff/chExt so the expected absolute box is computable). This is the highest-risk geometry
  (RFC watch-point #2) — test it carefully with non-identity scale (e.g. group ext != child chExt).
- **Table cell → invalid location**: `{{flag}}` in a table cell → anchor with
  `invalid_location=True`.
- **Same key in two shapes** → two anchors (so every shape gets filled later).
- **Key split across runs** inside a shape → still anchored (run-merging works).

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- Committed with `feat(ppt-filler): add image-anchor shape-walking traversal`.
</content>
