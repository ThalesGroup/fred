# Story 01 — Notes-metadata parsing + image schema fields

**Area:** agentic-backend (pure parser, no I/O)
**Depends on:** nothing
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

Extend the PPT Filler parser so a `{{key}}`'s description block in the slide notes may begin
with a **contiguous metadata block** declaring the key as an image with a source folder, and
extend the per-key schema model with `type` / `folder` fields. This is the pure parsing +
validation half (folder *resolution* is Story 03; geometry is Story 02).

## Files

- `agentic-backend/agentic_backend/integrations/ppt_filler/parser.py` (edit)
- `agentic-backend/agentic_backend/tests/test_ppt_filler_parser.py` OR
  `agentic-backend/tests/test_ppt_filler_parser.py` (the existing parser test file — add tests there)

> NOTE: there are two test dirs (`agentic_backend/tests/` and top-level `tests/`). The existing
> parser tests live at `agentic-backend/tests/test_ppt_filler_parser.py`. Add to that file.

## Authoring syntax (RFC "Authoring syntax")

A key's description block is everything between its `{{key}}:` header and the next header /
the `---` kept-notes separator. It MAY begin with a contiguous block of **metadata lines**,
each of the exact form `- <key>: <value>`:

```
{{countryFlag}}:
- type: image
- folder: "images/flags"
Pick the flag matching the country discussed.
```

Rules:

1. The metadata block is the run of leading lines matching `^\s*-\s*(\w+)\s*:\s*(.*)$`.
   It ends at the **first line** that is not such a line; everything from there on is prose
   (the agent guidance), exactly as today.
2. A leading-dash line that is NOT a `key: value` shape (e.g. `- choose the most recent`) ends
   the metadata block and is treated as **prose**, not metadata, not an error.
3. Recognized metadata keys: `type`, `folder` (case-insensitive; stored normalized lowercase).
4. Recognized `type` values: `text` (default when absent), `image` (case-insensitive; stored
   normalized lowercase).
5. The `folder` value may be wrapped in single or double quotes — strip a single matching pair
   of surrounding quotes.
6. A **multi-key header** (`{{a}}, {{b}}:`) shares one `type`, one `folder`, and one description
   across all its keys (the metadata block is parsed once for the header and applied to each key).
7. The prose description is everything after the metadata block (leading/trailing blank lines
   trimmed, internal blanks kept — same as today).
8. The kept-notes `---` separator is unaffected (metadata is single-dash; `---` is 3+ dashes and
   already split off by `split_authoring_and_kept_notes`).

## Schema model changes (`parser.py`)

Extend `KeyField`:

```python
class KeyField(BaseModel):
    key: str
    description: str = ""
    type: Literal["text", "image"] = "text"
    folder: Optional[str] = None        # author's folder string; only meaningful for images
    folder_tag_id: Optional[str] = None # resolved tag id, filled later (Story 03/05); None here
```

Text keys keep `type="text"`, `folder=None`, `folder_tag_id=None`. Serialization must keep the
JSON contract additive — text keys may serialize `type: "text"` and null folders; that's fine.

## Parsing changes

Rework `_parse_notes_descriptions` (or add a sibling) so it returns, per described key, a small
record carrying `description`, `type`, `folder`, plus any **metadata errors** discovered while
parsing that header's block. Suggested internal shape:

```python
@dataclass
class _ParsedKeyMeta:
    description: str
    type: str            # "text" | "image" (normalized)
    folder: Optional[str]
    errors: list[tuple[str, str]]  # (code, key) raised for THIS header, attributed per key later
```

Metadata validation rules (these produce the new codes — emitted from `parse`, attributed to the
right slide + each key of the header):

- `unknown_metadata` — a metadata key other than `type`/`folder`.
- `unknown_type` — a `type` value other than `text`/`image`.
- `duplicated_metadata` — the same metadata key declared more than once in one block.
- `image_without_folder` — `type: image` with no `folder` line, OR a `folder` line whose value is
  empty when type is image (an empty folder value maps here so "you didn't give a folder" reads
  right). Precedence: if `type: image` and folder is absent → `image_without_folder`.
- `empty_folder` — a `folder` line whose value is blank **on a key that is not image-without-folder**.
  Per RFC: `empty_folder` is the "you gave a folder line but left it blank" case, distinct from
  "no folder line at all". When `type: image` AND folder line present but blank → RFC says the
  empty value "also maps to image_without_folder" so the message reads grammatically. So:
    - `type: image`, no `folder` line → `image_without_folder`
    - `type: image`, `folder:` present but blank → `image_without_folder`
    - `type` not image (text), `folder:` present but blank → `empty_folder`
      (the folder is stray AND blank; report the blank as the specific issue) — but ALSO see
      `folder_without_image_type` below; emit the single most specific code. Recommended: when a
      blank folder sits on a non-image key, emit `empty_folder` (the value problem) rather than
      `folder_without_image_type`. Document the chosen precedence in a comment + test it.
- `folder_without_image_type` — a non-empty `folder` line on a non-image (text) key.

`folder_not_found` and `image_key_invalid_location` are NOT in this story (folder resolution =
Story 03/05; geometry = Story 02). Do not emit them here.

Define the new code constants in `parser.py` alongside the existing two:

```python
CODE_UNKNOWN_METADATA = "unknown_metadata"
CODE_UNKNOWN_TYPE = "unknown_type"
CODE_DUPLICATED_METADATA = "duplicated_metadata"
CODE_IMAGE_WITHOUT_FOLDER = "image_without_folder"
CODE_EMPTY_FOLDER = "empty_folder"
CODE_FOLDER_WITHOUT_IMAGE_TYPE = "folder_without_image_type"
# (folder_not_found, image_key_invalid_location defined in their own stories)
```

The `parse()` function must:
- build each slide's `KeyField`s using the parsed `type` + `folder` (folder_tag_id stays None);
- still emit `key_without_description` / `described_but_not_in_slide` unchanged (image keys reuse
  them);
- emit the new metadata error codes, each with the correct `slide` and `key` and a clear English
  `message` (the message is the fallback; the frontend i18n's by code).

## Tests (add to existing parser test file)

Assert EXTERNAL behavior (schema + error codes/slides), not internals:

- `type: image` + `folder: "images/flags"` → key has `type="image"`, `folder="images/flags"`,
  `folder_tag_id is None`; no error.
- folder value quote-stripping: `'images/flags'`, `"images/flags"`, and bare `images/flags` all
  yield `folder == "images/flags"`.
- case-insensitivity: `- TYPE: Image`, `- Folder: X` → normalized `type="image"`, recognized.
- contiguous-block rule: prose line with a leading dash that's not `key: value`
  (`- choose the most recent`) ends metadata and is captured as description, NOT an error.
- prose after metadata block is the description; metadata lines are NOT in the description.
- multi-key header `{{a}}, {{b}}:` with one metadata block → both keys share type/folder/desc.
- each new error code fires on its trigger with the right `code` + `slide` + `key`:
  `unknown_metadata`, `unknown_type`, `duplicated_metadata`, `image_without_folder` (both
  no-folder and blank-folder-on-image), `empty_folder` (blank folder on text key),
  `folder_without_image_type`.
- image key with no description still raises `key_without_description`.
- image key described but absent from slide still raises `described_but_not_in_slide`.
- default `type` is `text` when no metadata block present (backward compat); existing tests stay
  green.

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- All existing ppt_filler parser tests still pass (backward compatible).
- Committed on the branch with a `feat(ppt-filler): parse image metadata in slide notes` message.
</content>
