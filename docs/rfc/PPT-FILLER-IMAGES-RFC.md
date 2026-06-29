# PPT Filler Toolkit — Image Support — PRD / RFC

Status: Implemented
Provider key: `ppt_filler` (extends the existing toolkit)
Area: Agentic Backend (toolkit parsing/validation, fill tool, analyze endpoint) + Frontend (agent creation form) + Knowledge Flow (folder/tag resolution, raw content fetch)
Extends: [`PPT-FILLER-TOOLKIT-RFC.md`](./PPT-FILLER-TOOLKIT-RFC.md)

---

## Problem Statement

The PPT Filler toolkit lets an agent fill a `.pptx` template's `{{key}}` placeholders with
**text** extracted from the conversation and documents. But real deliverables are not text-only:
a CV needs skill icons, a country report needs a flag, a proposal needs a logo. Today a template
author has no way to say "put an image here, chosen from my uploaded resources." They can only get
text, so any image must be baked into the template by hand before every run — which defeats the
purpose of a reusable, agent-filled template.

Concretely, an agent creator cannot:

- mark a spot in their template where the agent should place an **image** (not text);
- point the agent at a **folder of images** they already uploaded to their space (personal or
  team) and let the agent pick the right one per run;
- let the agent **choose how many** images to use when several slots are offered (e.g. "use the
  2–3 skills that fit this CV") and have unused slots disappear cleanly;
- get **clear, early, slide-numbered feedback** when the image configuration in the notes is
  wrong — in the same inline-before-save way text keys already get.

## Solution

Extend the toolkit so a `{{key}}` can be declared as an **image** in the slide notes, with the
folder of candidate images it should be drawn from. The author draws a shape (rectangle / text
box) where the image should appear and writes `{{key}}` as its text; the shape's position and size
become the image's placement box. In the notes, metadata lines under the key's header declare it:

```
{{countryFlag}}:
- type: image
- folder: "images/flags"
Pick the flag matching the country discussed in the conversation.
```

At configuration time the template is analyzed exactly as today — but now image metadata is parsed
and validated too, and the declared `folder` is resolved against the **current space's** resource
folders (personal or team), with specific slide-numbered errors for every authoring mistake.

At chat time the agent is told, per image key, which **folder (by id)** to browse with its existing
document-tree tool; it picks the document that fits and passes that document's id to the fill tool,
which fetches the original image bytes and places the picture in the shape's box. Image slots the
agent leaves unfilled have their shape removed, so the deck never shows an empty placeholder.

The uploaded template remains the single source of truth: the schema (now including image type +
resolved folder) is always recomputed server-side from the actual file.

## User Stories

### Authoring image placeholders

1. As a template author, I want to mark a spot for an **image** (not text) by writing `{{key}}` in
   a shape and declaring it in the notes, so that the agent places a picture there.
2. As a template author, I want the **shape I draw** (its position and size) to define where and
   how big the image will be, so that I control the layout visually in PowerPoint.
3. As a template author, I want to declare a key as an image by writing `- type: image` on a line
   under the key's header, so that the agent treats it as a picture and not text.
4. As a template author, I want to specify which **folder** of my uploaded resources the image
   should come from via `- folder: "images/flags"`, so that the agent only chooses from the right
   set of images.
5. As a template author, I want metadata lines to sit directly under the key header as a small
   block, so that the configuration reads naturally above my free-text guidance.
6. As a template author, I want to write the folder value with or without quotes, so that I am not
   tripped up by a formatting detail.
7. As a template author, I want metadata keywords (`type`, `folder`) and values (`image`, `text`)
   to be case-insensitive, so that a capitalization slip does not break my template.
8. As a template author, I want my free-text description (prose) after the metadata block to still
   guide the agent, so that I can explain which image to choose.
9. As a template author, I want a bulleted line in my prose that is not real metadata (e.g.
   `- choose the most recent`) to be treated as description, not metadata, so that I can write
   naturally.
10. As a template author, I want to give several image keys the same image configuration with one
    multi-key header (`{{skill1}}, {{skill2}}, {{skill3}}:`), so that I don't repeat the folder
    and guidance for each slot.
11. As a template author, I want all keys of a multi-key header to share one type and one folder,
    so that a row of image slots is configured once.
12. As a template author offering several image slots, I want to tell the agent it may use only the
    number that fits, so that I can offer up to N slots without forcing exactly N.
13. As a template author, I want an image key I reuse in several shapes on one slide to be filled
    with the same image in every shape, so that repeated marks (e.g. a watermark) stay consistent —
    matching how text keys already repeat.
14. As a template author, I want my real presenter notes (after the `---` separator) to be
    untouched by image metadata parsing, so that the kept-notes feature still works.

### Immediate feedback / validation

15. As an agent creator, I want my image configuration validated the moment I pick a template,
    inline and before saving, with the **slide number** for each problem, so that I fix it
    immediately.
16. As an agent creator, I want to be told when I used an **unknown metadata keyword** (not `type`
    or `folder`), so that I correct the typo.
17. As an agent creator, I want to be told when I used an **unknown type** value (not `text` or
    `image`), so that I use a supported type.
18. As an agent creator, I want to be told when I **declared the same metadata twice** in one key's
    block (e.g. two `type` lines), so that I remove the duplicate.
19. As an agent creator, I want to be told when a key is `type: image` but has **no folder**, so
    that I add the folder.
20. As an agent creator, I want to be told when I gave a `folder` line but **left it empty**, so
    that I fill it in — with a message distinct from "folder not found."
21. As an agent creator, I want to be told when I gave a `folder` but the key is **not an image**,
    so that I either set `type: image` or remove the stray folder.
22. As an agent creator, I want to be told when the `folder` I named **does not exist** in my space
    (personal or team), so that I fix the name or create/upload to the folder.
23. As an agent creator, I want to be told when an image key sits in a shape that **cannot hold an
    image** (e.g. a table cell), with guidance to move it to a text box or rectangle, so that I
    place it somewhere it can actually be rendered.
24. As an agent creator, I want image keys to still benefit from the existing checks — a key
    present but undescribed, or described but absent — so that the same safety net applies.
25. As an agent creator, I want all of this feedback in my own language (driven by stable error
    codes), so that it is understandable.

### Folder resolution (space-aware)

26. As an agent creator, I want the folder to be resolved within **my current space** — my personal
    resources, or the owning team's resources if the agent is team-owned — so that the agent reads
    images I actually have access to.
27. As an agent creator, I want the folder resolved and verified **at save time** as well as during
    inline analysis, so that a saved agent never references a non-existent folder.
28. As an agent creator, I want the resolved folder to be stored with the schema, so that at chat
    time the agent can browse it directly without re-deriving it.

### Using the agent (chat time)

29. As an end user, I want the agent to **choose** the right image from the declared folder based
    on the conversation, so that I get a relevant picture without specifying it myself.
30. As an end user, I want the agent to be able to **browse** the declared folder (with its existing
    document-tree tool) and identify candidates by name, so that its choice is informed.
31. As an end user, I want the agent to place the chosen image in the marked spot at the right size,
    **without distortion**, so that the deck looks right.
32. As an end user offering optional image slots, I want unused slots to **disappear** (their shape
    removed), so that the deck shows no empty boxes.
33. As an end user, I want the user and agent to be able to **iterate** — filling some keys and not
    others across turns — so that we can refine the deck progressively.
34. As an end user, if the declared folder has since been **deleted**, I want the agent to do its
    best, finish what it can, and explain the problem (and that an owner/editor should fix the
    folder), so that I am not left with a silent failure.
35. As an end user, if the agent picks a document that is **not a usable image**, I want the fill to
    fail loudly so the agent re-picks, rather than silently dropping the picture, so that the result
    is correct.

### Documentation

36. As a template author, I want the help documentation to explain image templating (authoring,
    folder, multi-key "choose how many", the empty-slot-removed behavior), so that I can configure
    it without trial and error.
37. As a template author, I want each error documented in the Errors section with what triggers it
    and how to fix it, so that I can self-serve.

## Implementation Decisions

This feature extends the existing `ppt_filler` toolkit; it does not add a new provider. It reuses
the existing analyze endpoint, asset processor, fill tool, params model, and the shared traversal
module, extending each.

### Authoring syntax (notes metadata)

- A key's description block (between its header and the next header / kept-notes `---` separator)
  may begin with a **contiguous block of metadata lines**, each of the form `- <key>: <value>`.
- The metadata block ends at the first line that is not a `- <key>: <value>` line; everything from
  there is free-text prose (the agent guidance), exactly as today. A leading-dash line that is not
  a `key: value` shape (e.g. `- choose the best`) ends the block and is treated as prose, not an
  error.
- Recognized metadata keys: **`type`** and **`folder`**. Recognized `type` values: **`text`**
  (default when absent — backward compatible) and **`image`**.
- Matching of metadata keys and `type` values is **case-insensitive**; stored normalized.
- The `folder` value may be wrapped in single or double quotes; surrounding quotes are stripped.
- A **multi-key header** (`{{a}}, {{b}}:`) shares one description, one `type`, and one `folder`
  across all listed keys. A header is uniformly text or uniformly image.
- The kept-notes `---` (3+ dashes) separator is unaffected: metadata is single-dash and is parsed
  only in the authoring section before the separator.

### Schema shape (extension)

- The per-key schema field gains: `type` (`text` | `image`, default `text`), `folder` (the author's
  folder string, for display and messages), and `folderTagId` (the resolved folder id). Text keys
  carry `type: text` and no folder fields. The per-slide grouping is unchanged.

### Validation — new error codes

All are analyze-time and save-time, reported per-slide with the offending key, i18n-driven by a
stable `code` (same error contract as the existing toolkit):

- `unknown_metadata` — a metadata key other than `type` / `folder`.
- `unknown_type` — a `type` value other than `text` / `image`.
- `duplicated_metadata` — the same metadata key declared more than once in one block.
- `image_without_folder` — `type: image` with no `folder` line (an empty folder value also maps
  here, so "you didn't give a folder" reads grammatically).
- `empty_folder` — a `folder` line whose value is blank (distinct code so the message is specific).
- `folder_without_image_type` — a `folder` line on a non-image key.
- `folder_not_found` — a non-empty `folder` that does not resolve to a folder in the current space.
- `image_key_invalid_location` — an image key detected in a shape that cannot hold an inserted
  picture (a table cell). Message (heading) tells the author to move it into a text box or a
  rectangle, with keys grouped by slide as the UI already does.

Image keys also reuse the two existing presence errors unchanged: `key_without_description` and
`described_but_not_in_slide`.

### Folder = DOCUMENT tag (resolution model)

- A space's resource "folders" are **document tags** (hierarchical, with a stable id and a
  full path). The `folder` string (e.g. `images/flags`) resolves to a DOCUMENT tag's id, scoped to
  the owning **team** when the agent is team-owned, otherwise to the **user**.
- Resolution happens in Knowledge Flow (tag lookup by full path within the owner scope) and is
  invoked by the agentic analyze/save flow. The resolved id is persisted as `folderTagId`.

### Analyze endpoint — becomes space-aware

- The inline analyze endpoint additionally accepts the **current space context** (the optional
  team id alongside the already-present authenticated user). It collects every `folder` referenced
  in the notes and verifies each resolves, producing `folder_not_found` where it does not. Analyze
  still returns `200 { schema, errors }` for preview. The frontend sends the current space context
  with the file.

### Save flow — folder resolution in the asset processor

- The existing toolkit asset processor (params → params on save) is extended: when it re-parses the
  uploaded bytes, it also resolves every `folder` to a `folderTagId` within the agent's space and
  fails the save (422, structured errors) on any unresolved folder. The strip-before-persist
  invariant for the base64 upload field is unchanged.

### Fill tool — image branch

- Leaf keys in the dynamically built `args_schema` become **optional** (today they are required).
  For an **image** key, the per-key description instructs the agent to browse its folder (by
  `folderTagId`) with the existing document-tree tool, pick the document that fits, and pass that
  **document id** as the key's value; and, if the folder is missing, to do its best and explain to
  the user that an owner/editor must fix it.
- Filling an image key: fetch the chosen document's **original image bytes** by id, scale the image
  to **fit inside** the placeholder shape's box preserving aspect ratio (centered), insert it as a
  picture at the shape's absolute geometry, and remove the placeholder shape. An image key that
  appears in several shapes is filled in every one.
- An **omitted** image key (agent chose not to use that slot): the placeholder shape is removed, so
  no empty box remains. (An omitted text key resolves to empty string, as today.)
- **Chat-time failure policy:** a folder whose tag no longer resolves is a **soft** condition — the
  agent is told (via the tool description) to proceed and explain to the user. A document id that
  cannot be fetched or is not a usable image is a **hard** failure — the whole fill fails so the
  agent re-picks (it is the agent's own correctable mistake, versus an owner's config problem).
- A new Knowledge Flow client method is required on the agentic side to fetch a document's
  **original** bytes by id (the existing client exposes only preview/markdown-media fetchers, not
  the raw original). It wraps the existing raw-content download capability.

### Shared traversal — image anchoring

- Key **detection** already recurses into tables and grouped shapes (recently merged), so an image
  key inside a table cell is *detected* (not "missing") — which is precisely why
  `image_key_invalid_location` is needed.
- The existing list/replace traversal flattens to paragraphs and discards the containing shape, so
  it cannot supply geometry. Image anchoring therefore needs a **separate shape-walking traversal**
  that yields, per image key, the containing shape and its **absolute** geometry:
  - top-level text boxes and autoshapes → their own geometry;
  - **group children** → absolute coordinates composed from the group transform;
  - **table cells** → flagged as an invalid location (drives `image_key_invalid_location` at
    analyze and is refused at fill).
- This single shape-walking utility drives **both** the analyze error and fill-time insertion, so
  parse and fill cannot diverge for images — the image counterpart of the existing text round-trip
  invariant.
- SmartArt and chart text remain out of scope (no clean text-frame API): keys there are not
  detected at all, same as today.

### Frontend

- The existing `ppt_filler` configuration form sends the current space context to analyze, and
  renders the new error codes the same way it renders the existing two (group by code, then slide;
  i18n by code, falling back to the server message for unmapped codes).
- Regenerated OpenAPI types reflect the extended schema fields and the analyze request shape.

## Testing Decisions

Good tests assert **external behavior**, not traversal mechanics: given a `.pptx` and a (faked)
folder-resolution result, what schema and what error codes / slide numbers come out; given a
filled deck, that pictures land and unfilled image shapes are gone. Tests stay offline and
fixture-driven (small `.pptx` files built in-test or checked in). Prior art: the existing
`ppt_filler` parser/validator tests and `tests/test_kf_vector_search_tools.py`.

Seams, reusing the existing parser seam and adding two:

1. **Parser/validator seam (reused, extended)** — `parse(.pptx) → { schema, errors }`, pure, no I/O.
   New assertions:
   - metadata block parsed into `type` / `folder` (contiguous-block rule, case-insensitivity,
     quote-stripping);
   - prose with a non-metadata leading-dash line stays prose;
   - multi-key header shares `type` + `folder` + description;
   - each new error code fires on its trigger with the right `code` and `slide` (the folder-
     resolution-dependent `folder_not_found` driven via an injected/faked resolver);
   - image keys still raise the existing presence errors.

2. **Image-anchor traversal seam (new)** — a focused unit over the shape-walking utility: top-level
   shape → geometry; group child → absolute geometry from the group transform; table cell →
   invalid location. This unit feeds an extended **round-trip** test: parse → fill (text substituted
   and image shapes replaced by pictures, unfilled image shapes removed) → re-parse finds no
   remaining `{{keys}}` and the expected pictures/removals — the image counterpart of the existing
   round-trip guard.

3. **Folder-resolution seam (new, faked/injected)** — resolve a `folder` string + space scope to a
   tag id. Tests assert: existing path → id; missing path → not-found signal that surfaces as
   `folder_not_found`; team vs personal scope honored. The actual Knowledge Flow lookup and the
   raw-bytes fetch are faked/injected; the asset processor test asserts that on save, folders are
   resolved into `folderTagId` and an unresolved folder fails the save.

Chat-time fill behavior (fetch by id → fit-inside insert → shape removal; soft folder-missing vs
hard bad-image) is covered with the document fetch faked.

## Out of Scope

- Image sources other than the space's document folders (no inline upload of an image at chat time,
  no external URLs).
- SmartArt and chart text as key locations (unchanged from the base toolkit).
- Cropping or fill-to-cover sizing — v1 uses fit-inside, aspect-preserved, centered only.
- Per-key folders within a single multi-key header (one folder per header).
- Non-image binary insertion (video, audio, embedded files).
- Localization of image content; only error messages are i18n.

## Further Notes

- **Highest-risk watch-points:**
  1. The image-anchor traversal must stay in sync with key detection — if an image key is detected
     but the anchor walk disagrees about its shape/geometry, fills land wrong or silently drop.
     Covered by the extended round-trip test.
  2. Group-child absolute geometry (composing the group transform) is the only non-trivial
     geometric computation; get it wrong and grouped image slots are mispositioned.
  3. Analyze becoming space-aware widens a previously stateless contract — the frontend must send
     space context, and folder resolution must be scoped correctly (team vs personal) so an author
     never validates against the wrong space's folders.
  4. The new raw-original-bytes client method is the only net-new backend dependency at chat time;
     the rest reuses existing capabilities.
- The chat-time soft/hard split is deliberate: a missing folder is an owner's configuration problem
  the agent cannot fix (soft, explain), whereas a bad document choice is the agent's own correctable
  mistake (hard, re-pick).
