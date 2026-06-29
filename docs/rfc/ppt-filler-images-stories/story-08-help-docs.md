# Story 08 — Help documentation: image templating + per-error docs

**Area:** frontend (static help markdown)
**Depends on:** Story 01 (authoring syntax), Story 03 (error codes) — can be written from the RFC
in parallel with implementation since it's documentation.
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

Document image templating so an author can configure it without trial and error, and document each
new error with what triggers it and how to fix it.

## Files

- `frontend/public/ppt-filler-help.md` (English)
- `frontend/public/ppt-filler-help.fr.md` (French)

(The help page `PptFillerHelpPage.tsx` fetches `/ppt-filler-help.md` or `.<lang>.md` and renders
markdown; route `/ppt-filler-help`. No code changes needed — only the markdown.)

## Content to add

### New authoring section (after the existing "Advanced usage" / before/around "Errors")

Title: "Adding images". Cover:

- How to mark an image spot: draw a shape (rectangle or text box) where the image should go, write
  `{{key}}` as its text. The shape's position and size become the image's placement box.
- Declare it in the notes with a metadata block directly under the key header:

  ````
  {{countryFlag}}:
  - type: image
  - folder: "images/flags"
  Pick the flag matching the country discussed.
  ````

- `type: image` makes the agent place a picture (default is `text`).
- `folder:` points at a folder of your uploaded resources (personal or your team's). Quotes
  optional; keywords/values are case-insensitive.
- Multi-key header shares one folder + guidance: `{{skill1}}, {{skill2}}, {{skill3}}:` then one
  `type`/`folder` block — offer several slots configured once.
- "Choose how many": you can offer N image slots and tell the agent (in the prose) to use only the
  ones that fit. **Unused image slots are removed** — the deck shows no empty box. (Omitted text
  keys become empty text, as today.)
- The image is scaled to **fit inside** the shape's box, aspect ratio preserved, centered (no
  distortion, no cropping in v1).
- A repeated image key (same key in several shapes on one slide) gets the same image in every
  shape — like repeated text keys.
- Real presenter notes after the `---` separator are untouched.
- The folder must be a real folder in your space; it's checked when you pick the template and again
  when you save.

### Errors section — add one entry per new code

For each, give the trigger and the fix (mirror the existing two entries' style):

- `unknown_metadata` — you used a metadata keyword other than `type`/`folder`. Fix the typo.
- `unknown_type` — `type:` value is not `text` or `image`. Use one of those.
- `duplicated_metadata` — the same metadata key appears twice in one key's block. Remove the dup.
- `image_without_folder` — a key is `type: image` but has no folder (or an empty one). Add
  `- folder: "..."`.
- `empty_folder` — a `folder:` line is blank. Fill it in.
- `folder_without_image_type` — you set a `folder` on a key that isn't an image. Either add
  `- type: image` or remove the folder.
- `folder_not_found` — the named folder doesn't exist in your space (personal or team). Fix the
  name, or create/upload to that folder.
- `image_key_invalid_location` — an image key sits somewhere that can't hold a picture (a table
  cell). Move it into a text box or a rectangle.

Keep the existing two error entries (`key_without_description`, `described_but_not_in_slide`).

Optionally add a screenshot reference if one exists under `public/ppt-filler/`; otherwise text is
fine.

## Done when

- Both markdown files updated and consistent (English + French).
- Committed with `docs(ppt-filler): document image templating and image errors`.
</content>
