# fred-capability-pptx-generator

Fred agent capability that composes a PowerPoint deck **from scratch** — title,
slides, bullets, tables, charts, images, shapes and speaker notes — in a single
`generate_pptx` tool call. An optional brand template makes the deck match
corporate branding.

This is the compact, current reference for the capability. Questions still open
live in `docs/swift/rfc/PPTX-GENERATOR-CAPABILITY-RFC.md`.

## Why a separate capability from `ppt_filler`

`ppt_filler` fills the placeholders of a template the user must upload: its tool
schema is rebuilt per turn from that template, so it needs `middleware()`, a
preview router, and only runs on ReAct agents. Here the deck's structure comes
from the LLM call itself, so the schema is **static** (`GeneratePptxArgs`,
`models.py`). That makes this the plain `tools(ctx)` case of `AUTHORING.md`:

- no `middleware()`, no prompt fragment — discoverability comes from the tool
  description, like `document_access`;
- default `execution_models`, so it works on ReAct **and** Graph agents;
- no router and no owned table — the deck lives in the session workspace;
- usable with zero configuration (python-pptx's default theme).

The two capabilities share the PDF conversion helper and the preview/download
UX pattern, nothing else.

## The tool

`generate_pptx(title, slides, theme?)` — one call builds the whole deck; a
follow-up call regenerates it wholesale.

- **Slide kinds**: `title`, `section_header`, `bullets`, `two_content`,
  `columns`, `image`, `table`, `chart`. Styling fields (`background`,
  `title_style`, `body_style`, `shapes`) are additive on any kind.
- **Bullets** support nesting (`level`) and inline `**bold**` / `*italic*`.
- **Charts**: bar, column, line, pie, doughnut, area, radar, scatter and bubble
  are native `XL_CHART_TYPE` objects, editable afterwards in PowerPoint.
  Heatmap, waterfall, funnel and Gantt have no native equivalent and are
  rendered by matplotlib as an embedded PNG. The choice is made at build time;
  the agent only names the chart type.
- **Images** (`image_ref`, background `image_ref`, `icon_ref`) are corpus
  `document_uid`s fetched through `document_content.fetch_raw()`. The agent
  finds them with the document-access tools first; no folder browsing here.
- **Theme**: `theme.preset` picks one of eight curated, contrast-checked
  identities (`palettes.py`). Presets apply a "strong" treatment to title and
  section slides and a "soft" one to content slides; explicit per-slide or
  deck-wide fields win. Presets exist because LLMs pick colours inconsistently.
- **Backgrounds**: solid, two-stop gradient, image, or a procedural pattern
  (`soft_circles`, `diagonal_bands`, `dot_grid`) rendered by matplotlib.
  Patterns are deterministic so output stays testable.
- **Shapes**: a curated `MSO_SHAPE` set positioned in **fractions of the slide
  size**, so placement survives any template's slide dimensions.

### Return contract

The deck is written to `outputs/{session_id}/…pptx` in the workspace, then
converted to PDF with `fred_core.convert_office_bytes_to_pdf` (best effort).
Success returns a `PptxGeneratedPart` (`"pptx_generated"`, preview pane +
download); if conversion fails, a plain download `LinkPart`. It is a new part
class rather than `ppt_filler`'s `PptPreviewPart` because each capability must
own its discriminator in the chat-part registry.

Invalid input (unknown `image_ref`, oversize table, too many slides) returns an
`is_error` result the model can correct. Elements that don't fit the chosen
layout (a field the template slide has no zone for, a shape covering text) are
**dropped with a warning** appended to the tool result instead of failing the
deck.

### Guardrails

`MAX_SLIDES = 50`, `MAX_SHAPES_PER_SLIDE = 20`, `MAX_TABLE_ROWS = 50`,
`MAX_TABLE_COLS = 20`, `MAX_COLUMNS = 4` (`deck_builder.py`); template upload
capped at 50 MB. Deck building is CPU-bound: it runs in `asyncio.to_thread`
behind a bounded gate (`concurrency.py`, 4 concurrent jobs), and image
prefetches are bounded too.

## Brand template

One optional `AssetSlot` (`brand_template`, `.pptx`). At config save,
`validate_config` checks the size, opens the file off the event loop to prove
it is a `.pptx`, stores the blob in `agent_assets` (only the key is persisted)
and computes `template_slide_catalog` (`template_inventory.py`): one line per
template slide with its title, content tags and text-zone styles. `tools()` is
synchronous and cannot fetch the template per turn, so the catalog is spliced
into the tool description instead (capped at 50 slides).

The template's masters and layouts are always inherited. Its own slides never
appear in the output unless the agent reuses one.

### Reusing a template slide

`SlideSpec.template_slide_index` duplicates that slide (background, decorative
shapes, placeholders) and fills it with the slide's content according to
`kind`. Reference is by position only. Notes:

- python-pptx has no slide-duplication API: shapes are deep-copied and picture
  relationships re-wired, recursing into groups. Slides containing charts, OLE
  objects or media are rejected with an actionable error rather than producing
  dangling relationships.
- A reused slide skips the preset's automatic background and fonts — it
  already has a designed look.
- **Chapter dividers with inverted placeholders**: some templates type the
  numbered badge ("01") as `title` and the real title as `body`. For
  `section_header`, if a slide has exactly two placeholders and exactly one
  default text matches `^\d{2}$`, zones are detected by content: the title goes
  to the non-badge zone and the badge gets the next ordinal, computed by the
  builder (never supplied by the agent). Both zones are read back after
  writing; a mismatch fails the build. Any other shape falls back to the
  type-based fill.
- `columns` slides map template zones sharing a left edge to columns, left to
  right, with optional label zone (`group_label`) and icon frames (`icon_ref`).

### Layout resolution (generated slides)

Layouts are matched by name first (`_LAYOUT_NAMES_BY_KIND`), then
structurally: each layout is scored on its count of real content placeholders
(BODY/OBJECT; date/footer/slide-number excluded) against what the kind wants,
with `image` preferring a PICTURE placeholder and `title` a SUBTITLE one. There
is no numeric index fallback — it used to collapse four kinds onto one layout
for non-English templates. Fallback content boxes are fractions of the actual
slide size, not fixed inches.

Tables size their font from the row count and distribute column widths by text
length (with a floor).

## Known gaps

- A decorative shape can still overlap a **title**: title placeholders span
  most of the slide width, and python-pptx cannot measure rendered text, so a
  geometric guard rejects legitimate corner accents. Mitigation: avoid `shapes`
  on `title` / `section_header` slides.
- Pie/doughnut charts are not coloured per series (they colour per point).
- No shadows/glow, no theme-XML rewrite (styles are applied per run/shape), no
  freeform shapes, no SmartArt, animations or transitions.

## Frontend

Plugin in `apps/frontend/src/rework/features/capabilities/pptx_generator/`:
card renderer, PDF preview side panel (`pptx_preview_pane`), authenticated
download button (`downloadAuthed()`, since a bare link 401s on `/fs/download`),
brand-template config form. Icon `co_present`, distinct from `ppt_filler`'s
`slideshow`.

## Registration

Installing this package *is* the registration: the fred-agents pod discovers
the capability at boot via the `fred.capabilities` entry point in
`pyproject.toml`
(`pptx_generator = "fred_capability_pptx_generator.capability:PptxGeneratorCapability"`).
On the frontend, the plugin is listed in `features/capabilities/index.ts`.
