# RFC — PPTX Generator Capability: agent-composed PowerPoint decks from scratch

**Status:** Draft for developer review
**Author:** ewan-schwaller (drafted with Claude Code)
**Date:** 2026-09-15
**Area:** `fred-runtime` (new capability package), `frontend`
**Related:** `libs/fred-capability-ppt-filler/` (sibling PPTX capability, used
as the asset/PDF-preview reference — see §5 for how this diverges from it),
`HTML-ARTIFACT-CAPABILITY-RFC.md` (structure template for this RFC, and the
precedent for a single-tool, no-owned-table v1), `docs/swift/capabilities/AUTHORING.md`,
the `add-fred-capability` skill, and `docs/swift/backlog/CHAT-UI-BACKLOG.md`
§4.5.E (a stale "slide-template validation agent" stub, superseded first by
`ppt_filler` and now further superseded by this RFC — to be pruned once this
ships, per §7).

---

## 1. Problem

Fred has no way to produce a PowerPoint deck **from scratch**. The only
existing PPTX capability, `ppt_filler` (#1903), fills placeholders in a
`.pptx` **template the user must already own and upload** — it cannot
compose a new deck's structure, slide count, or content. Asked to "build me
a 10-slide deck on Q3 results with a revenue chart and a competitor table",
an agent today can only paste an outline as chat text.

A reuse audit (2026-09-15) confirms: no RFC or backlog item covers
from-scratch PPTX generation; the closest match,
`CHAT-UI-BACKLOG.md` §4.5.E ("Minimal slide-template validation agent"), is
already superseded by `ppt_filler`'s shipped shape and does not describe
generation either. `libs/fred-core/fred_core/conversion/office_pdf.py`
(PPTX→PDF via headless LibreOffice) and the `services.workspace_fs` /
asset-download UI machinery are directly reusable — see §5.

---

## 2. Goals

1. Give an agent one tool to compose a **complete PowerPoint deck** — title,
   multiple slides, bullet content (with nesting), tables, native charts,
   images, and speaker notes — in a single call.
2. Cover the large majority of real business-deck charts as **native,
   PowerPoint-editable chart objects** (bar/column, line, pie, doughnut,
   area, radar, scatter, bubble — all natively supported by `python-pptx`'s
   `XL_CHART_TYPE`), so a user can click into PowerPoint/LibreOffice Impress
   and edit the underlying data afterward.
3. Cover a useful set of chart types `python-pptx` cannot express natively
   (heatmap, waterfall, funnel, Gantt/timeline) via a **matplotlib-rendered
   image fallback**, transparent to the agent — it just asks for the chart
   type, the builder decides native-vs-image at build time.
4. Optionally inherit a **brand template** (masters, theme, color palette)
   the same way `ppt_filler` accepts one, so generated decks can match
   corporate branding without a separate mechanism to learn.
5. Reuse the shipped preview/download UX (PDF preview pane + authenticated
   download button) rather than inventing a new one — mirror `ppt_filler`'s
   two-tier return contract.
6. Use only free, open-source components: `python-pptx`, `matplotlib`,
   `Pillow`, and the already-vendored headless LibreOffice conversion path.

---

## 3. Non-goals (v1)

- **No SmartArt, animations, or slide transitions.** Hard limits of
  `python-pptx`/generative OOXML; out of scope for any version without a
  different toolchain.
- **No treemap, sankey, or network-diagram charts.** Buildable in principle
  but need extra dependencies (e.g. `squarify`) beyond plain `matplotlib`;
  deferred to v2 if requested (§8).
- **No iterative slide-by-slide editing.** Like `html_artifact` v1, a call
  produces a complete deck; a follow-up call regenerates it wholesale. No
  "just change slide 3" partial-update tool.
- **No agent read-back of a previously generated deck.** The agent does not
  re-ingest its own output to keep editing it in a later turn.
- **No photographic/generative image content.** Images placed on slides come
  only from the existing document library (already-uploaded assets), never
  from a text-to-image model — no such model is wired into Fred today, and
  adding one is out of scope here.
- **No owned table, no CRUD router.** Same reasoning as `html_artifact` §5 —
  see §5 below for why this one is even simpler than `ppt_filler`.

---

## 4. Design

### 4.1 Lane and shape

Full **capability package** lane, out-of-tree like `ppt_filler` and
`html_artifact` (`docs/swift/capabilities/AUTHORING.md` §"three authoring
lanes", lane 2/3). New package:
`libs/fred-capability-pptx-generator/fred_capability_pptx_generator/`.

**Divergence from both existing PPTX-adjacent capabilities, and why:**
unlike `ppt_filler`, the tool's argument schema is **static** — it is a
fixed pydantic model (`GeneratePptxArgs` in §4.3), not derived per-turn from
an uploaded template's placeholder set. A static schema is exactly the
`tools(ctx)` case in the AUTHORING.md decision table (the canonical
`document_access` pattern), not the `middleware()` escape hatch. This
capability therefore implements **only `tools(ctx)`**, declares no
`middleware()` override, and is left at the **default** `execution_models`
(`("react", "graph")`) — it works on Graph agents too, which neither
`ppt_filler` nor `html_artifact` can claim (both are ReAct-only because they
use `middleware()`). Tool discoverability relies on a clear LangChain tool
`description` (same as `document_access`, which also carries no prompt
fragment) rather than an always-on system-prompt overlay — simpler, and one
fewer moving part per the consolidation phase's bias against unneeded
machinery.

### 4.2 Typed models

`AgentCapability[PptxGeneratorConfig, PptxGeneratorConfig, EmptyModel]` — no
chat-time turn options. `ConfigModel` carries exactly one optional field, the
brand-template upload slot (§4.2.1); `StoredConfigModel` defaults to the same
model (`template_key: str | None` after `validate_config` resolves the
upload). No config at all is required — an agent can use this capability
with zero setup, generating decks with `python-pptx`'s default blank theme.

#### 4.2.1 Brand template (optional)

```python
assets = [
    AssetSlot(key="brand_template", accepted_types=[".pptx"], min_count=0, max_count=1)
]
```

`validate_config` mirrors `ppt_filler/capability.py`'s state machine, minus
the placeholder-schema parsing step (there is nothing to parse — the file is
only a source of masters/theme):

1. Upload present → cap-check bytes (reuse `ppt_filler`'s
   `MAX_TEMPLATE_UPLOAD_BYTES` constant/value, 50 MB) → open with
   `python-pptx` inside `asyncio.to_thread` purely to **validate** it parses
   as a `.pptx` (no schema extraction) → store the blob via
   `ctx.services.agent_assets.store(config.template_key, pptx_bytes,
   content_type=_PPTX_CONTENT_TYPE, filename=config.template_key)` — the
   blob is **never** persisted in `tuning_json`, only the key.
2. No upload, `template_key` already configured → pass through unchanged.
3. No upload, nothing configured → pass through unchanged (this field is
   optional, unlike `ppt_filler`'s required template).

Unlike `ppt_filler`, **no router is needed** — there is no `/analyze`
preview-parse endpoint, because there is no placeholder schema to show the
user at configuration time.

### 4.3 The tool

One tool, static schema, closed over `CapabilityContext` for services/identity
(never in the LLM-visible schema — the hard split):

```python
class SlideSpec(BaseModel):
    kind: Literal["title", "bullets", "image", "table", "chart", "section_header", "two_content"]
    title: str | None = None
    subtitle: str | None = None
    bullets: list[BulletItem] | None = None      # BulletItem: text: str, level: int = 0
    image_ref: str | None = None                  # existing document-library asset key
    table: TableSpec | None = None                 # headers: list[str], rows: list[list[str]]
    chart: ChartSpec | None = None                  # chart_type, title, categories, series
    speaker_notes: str | None = None

class GeneratePptxArgs(BaseModel):
    title: str                                     # deck title / output file name basis
    slides: list[SlideSpec]                        # 1..MAX_SLIDES (v1 cap: 50)

async def generate_pptx(title: str, slides: list[SlideSpec]) -> tuple[str, ToolInvocationResult]:
    ...
```

`response_format="content_and_artifact"`, mirroring `ppt_filler`'s fill tool.
On success: `deck_builder.build(title, slides, template_bytes=...)` (off the
event loop via `asyncio.to_thread`, under a bounded concurrency gate copied
from `ppt_filler/concurrency.py`) → `presentation.save()` bytes →
`services.workspace_fs.write(f"outputs/{session_id}/{file_name}.pptx", ...)`
→ best-effort `fred_core.convert_office_bytes_to_pdf(..., suffix=".pptx")` (reused as-is, zero
new conversion code) → second `workspace_fs.write(...)` for the PDF → a
`PptxGeneratedPart` (pane + download) on success, or a plain
`LinkPart(kind="download")` fallback if PDF conversion fails — the exact
two-tier return contract of `ppt_filler/fill.py`. Error paths (unknown
`image_ref`, table too large, over `MAX_SLIDES`) return an `is_error`
`ToolInvocationResult` steering the model to correct its call, same pattern
as `html_artifact`'s over-cap rejection.

**Chart native-vs-fallback decision (build-time, invisible to the agent):**

```python
_NATIVE_CHART_TYPES = {"bar", "column", "line", "pie", "doughnut", "area", "radar", "scatter", "bubble"}
_IMAGE_FALLBACK_CHART_TYPES = {"heatmap", "waterfall", "funnel", "gantt"}
```

Native → `slide.shapes.add_chart(XL_CHART_TYPE.<mapped>, x, y, cx, cy,
chart_data)` (editable afterward in PowerPoint/Impress). Fallback → render a
PNG via `matplotlib` in `chart_render.py` (plain `matplotlib`, no extra
dependency — heatmap via `imshow`, waterfall/Gantt via offset/broken
`barh`, funnel via decreasing-width horizontal bars — all standard
matplotlib recipes) inside the same `asyncio.to_thread` call as the rest of
the deck build, then `slide.shapes.add_picture(io.BytesIO(png_bytes), ...)`
directly — no intermediate storage round-trip, the bytes never leave the
worker thread until they are embedded in the deck.

**Images** (`image_ref`) — **implementation note (2026-09-15, post-build):**
the shipped capability does **not** reimplement `ppt_filler`'s
team/user folder-resolution logic (`folder_resolution.py`) as originally
sketched above. `SlideSpec.image_ref` is a flat `str`, resolved directly as a
corpus `document_uid` via `ctx.services.document_content.fetch_raw(image_ref)`
— the same port `ppt_filler` uses to read an already-*chosen* image's bytes,
without ppt_filler's separate folder-listing/browsing step. The tool
description instructs the agent to obtain the `document_uid` from the
document-access capability's search/tree tools first (cross-capability
chaining, the same doctrine `ppt_filler` documents for itself). This is the
smaller, working design given the actual `SlideSpec` shape and the
`RuntimeServices` ports available — the folder-browsing sketch above was
never built and should not be assumed to exist.

### 4.4 The chat part

```python
class PptxGeneratedPart(BaseModel):
    type: Literal["pptx_generated"] = "pptx_generated"
    preview_id: str
    title: str
    pdf_download_url: str
    version: str                    # sha256(pdf_bytes)[:16], same recipe as PptPreviewPart
    pptx_download_url: str | None
    file_name: str | None
```

Deliberately **not** a reuse of `ppt_filler`'s `PptPreviewPart` class even
though the shape is nearly identical: two independent capabilities each
declaring `chat_parts=[PptPreviewPart]` for the same imported class would
collide at the chat-part registry (each capability owns its discriminator).
A new discriminator (`"pptx_generated"` vs `ppt_filler`'s `"ppt_preview"`)
keeps the two capabilities' registrations independent, as the boot-time
duplicate-discriminator check expects. The frontend pane/download component
logic (§4.5) can still be shared at the UI-component level (plain React
reuse, not a registry construct) without conflict.

### 4.5 Frontend

New plugin `apps/frontend/src/rework/features/capabilities/pptx_generator/`,
mirroring `ppt_filler`'s: `PptxPreviewPane.tsx` (PDF preview, same
worker-based renderer as `PptPreviewPane.tsx` — a shared internal component
extracted or duplicated, developer's call at implementation time),
`PptxDownloadButton.tsx` reusing `downloadAuthed()` from
`utils/downloadUtils.tsx` (a bare `<a href download>` 401s against the
bearer-protected `/fs/download` route — same rationale as `ppt_filler`'s
button). `plugin.ts`:

```ts
export const pptxGeneratorCapability: CapabilityUiPlugin = {
  id: "pptx_generator",
  partRenderers: { pptx_generated: PptxGeneratedCardRenderer },
  sidePanels: { pptx_preview_pane: { Component: PptxPreviewPane, icon: "co_present", useHasContent: useHasPptxPreview, ownsHeader: true } },
};
```

Registration is the two sanctioned one-line edits: the plugin object added
to `features/capabilities/index.ts`'s array, and the backend
`fred.capabilities` entry-point line in `pyproject.toml`. No config widget
needed beyond the stock upload-slot renderer already used for
`ppt_filler`'s template slot (if the brand-template `AssetSlot` maps to the
same generic asset-upload UI — to confirm against the current generic
`AssetSlot` renderer at implementation time; only build a custom widget if
that renderer cannot express an *optional* single-file slot).

**Icon**: `co_present` (a person presenting, distinct from `ppt_filler`'s
`slideshow` — avoids two visually identical capability icons in the same
picker). Needs adding to the `materialIcons` allow-list in
`apps/frontend/src/rework/components/shared/utils/Type.ts` (§7).

---

## 5. Why this is simpler than `ppt_filler`, not a variant of it

`ppt_filler` needs `middleware()` because its tool schema is **dynamic**
(built per-turn from a parsed template's placeholders), needs a router
because there's a template to preview/validate before save, and needs
`agent_assets` storage as a **required** input (no template, no capability).
None of that applies here: the deck's shape comes from the LLM call itself,
the brand template (if any) is a passive theme source with nothing to
parse or preview, and the capability is fully usable with zero
configuration. Building this as a mode inside `ppt_filler` (the rejected
alternative in §6.1) would force a dynamic-schema, `middleware()`-only,
ReAct-only capability to carry a static-schema, `tools()`-compatible,
Graph-capable code path in the same class — a worse shape for both halves.
Keeping them separate is the smaller, more consolidated design, not a
duplication of it: they share the PDF-conversion helper and the
preview/download UX pattern, and diverge exactly where their actual
mechanics diverge.

---

## 6. Alternatives considered

1. **Extend `ppt_filler` with a "generate new" mode.** Rejected — see §5.
2. **Two tools** (`render_chart_image` producing a reusable image reference,
   plus `generate_pptx` consuming it). Rejected: an extra LLM round-trip and
   an intermediate storage write for no benefit in v1, since no chart image
   needs to be reused across multiple slides or calls. The matplotlib
   fallback is folded into the single `generate_pptx` build step instead
   (§4.3) — simpler, fewer tool-call round trips, smaller surface.
3. **Owned table + CRUD router for generated decks.** Rejected for v1, same
   reasoning as `html_artifact` §5 — no editing/persistence need yet; the
   `outputs/{session_id}/...` workspace-fs path plus the chat part already
   gives the user a durable, redownloadable artifact.
4. **Always route charts through matplotlib for visual consistency.**
   Rejected — throws away the real, user-valued benefit of native
   PowerPoint charts (post-generation editability of the underlying data),
   which most requested chart types (bar/line/pie/etc.) support natively.
5. **Require a brand template (like `ppt_filler`).** Rejected — the whole
   point of from-scratch generation is working with **no** prior template;
   making one mandatory would just be `ppt_filler` with extra steps.

---

## 7. Impact on existing contracts

- **New chat-part discriminator** `"pptx_generated"` (must be unique at
  boot, §4.4). New **side-panel widget** `"pptx_preview_pane"`.
- **Capability catalog** picks the manifest up automatically via the
  `fred.capabilities` entry point (`libs/fred-capability-pptx-generator/pyproject.toml`);
  `apps/fred-agents/pyproject.toml` gains one dependency line. No
  control-plane code (the capability boundary).
- **Frontend plugin registry** gains one entry in
  `features/capabilities/index.ts`; no generated-API-client impact (no
  router in v1).
- **New icon** `co_present` added to the `materialIcons` allow-list in
  `apps/frontend/src/rework/components/shared/utils/Type.ts`.
- **i18n**: `capability.pptx_generator.name` / `.description` + any viewer
  labels, `en` + `fr`.
- **Docs on completion**: add the capability to
  `docs/swift/capabilities/AUTHORING.md`'s worked-examples table; prune the
  stale `CHAT-UI-BACKLOG.md` §4.5.E stub (already superseded, now doubly
  so); fold the settled design into whatever compact doc catalogs shipped
  capabilities (mirrors `html_artifact`'s close-out plan); trim this RFC to
  any part still genuinely open.

No change to frozen execution/product contracts expected — chat parts and
side panels are already a generic capability-system extension point.

---

## 8. Deferred — v2, out of scope here

- Treemap / sankey / network-diagram chart types (need `squarify` or
  similar — an actual new dependency, not "free matplotlib recipe").
- Iterative editing ("regenerate slide 4 only") instead of whole-deck
  regeneration.
- Agent read-back of a previously generated deck to keep refining it.
- Photographic/generative image content once/if a text-to-image model is
  wired into Fred generally (a platform-level decision well outside this
  RFC's scope).
- Owned table + router, if a persisted/editable deck workflow is wanted
  later (same extension path `html_artifact` left open for itself).

---

## 9. Resolved decisions

1. **One tool, not two** — chart fallback is an internal build-time branch,
   not a second LLM-callable tool (§4.3, §6.2).
2. **`tools(ctx)`, not `middleware()`** — static schema, works on ReAct and
   Graph, no prompt-fragment overlay; relies on tool `description` for
   discoverability, same as `document_access` (§4.1).
3. **Brand template is optional, not required** — the defining difference
   from `ppt_filler` (§4.2.1, §5).
4. **Native chart types**: bar/column, line, pie, doughnut, area, radar,
   scatter, bubble (all real `python-pptx` `XL_CHART_TYPE` entries).
   **Matplotlib-fallback types (v1)**: heatmap, waterfall, funnel, Gantt —
   all buildable with plain `matplotlib`, no new dependency (§4.3).
5. **Deck size cap**: 50 slides per call (v1; revisit if real usage needs
   more) — mirrors the spirit of `html_artifact`'s size cap as an
   engineering guardrail, not a hard product limit.
6. **New chat-part class, not a reuse of `ppt_filler`'s `PptPreviewPart`**
   — avoids a discriminator collision at the registry (§4.4).
7. **Icon `co_present`**, distinct from `ppt_filler`'s `slideshow` (§4.5, §7).
8. **`image_ref` is a flat corpus `document_uid`, resolved directly via
   `document_content.fetch_raw()`** — not a folder/path-based lookup. Settled
   during the build once the actual `SlideSpec` shape and available
   `RuntimeServices` ports were fixed; supersedes the folder-resolution sketch
   in an earlier draft of §4.3 (see the implementation note there).

---

## 10. Build plan (after developer sign-off — not started)

1. GitHub issue (link this RFC), attached to the currently open milestone.
2. Backend package `libs/fred-capability-pptx-generator/`: capability class
   (`tools(ctx)`, `AssetSlot` + `validate_config`), `models.py`
   (`SlideSpec`/`ChartSpec`/`TableSpec`), `deck_builder.py` (python-pptx
   construction incl. native charts + fallback image embedding),
   `chart_render.py` (matplotlib fallback recipes), `concurrency.py`
   (bounded gate, adapted from `ppt_filler`), `parts.py`
   (`PptxGeneratedPart`). Unit tests: `registry.validate()` green; deck
   builder per slide variant; each fallback chart recipe produces a valid
   PNG; tool happy/error paths with a stubbed `RuntimeServices`.
3. Frontend plugin: card renderer, `PptxPreviewPane.tsx`,
   `PptxDownloadButton.tsx`, plugin registration, i18n, `co_present` icon
   added to the allow-list.
4. `make test` + `make code-quality` in `libs/fred-capability-pptx-generator`
   and `apps/frontend`; the `fred-performance-reviewer` skill (mandatory —
   `generate_pptx` is a per-turn tool-call site doing CPU-bound
   `python-pptx`/`matplotlib` work, must run under `asyncio.to_thread` with
   a bounded concurrency gate, same class of review `ppt_filler` went
   through); then `/code-review` self-review on the diff before reporting
   done.
5. Prune `CHAT-UI-BACKLOG.md` §4.5.E; add the capability to
   `docs/swift/capabilities/AUTHORING.md`'s worked-examples table; trim this
   RFC to whatever (if anything) remains open; close the GitHub issue.

---

## 11. Amendment (2026-09-15) — shapes and visual styling (v1.1)

**Status:** approved by developer for implementation (chat confirmation,
2026-09-15) — scoped here before coding, per the RFC-first rule for
not-yet-built design.

### 11.1 Problem

v1 (§2–§9) covers structured content (text/tables/charts/images) but has no
way to draw a shape (box, arrow, circle used as a diagram element or
highlight) and no way to control color/font/background — a deck can only
look as good as its optional brand template. The developer asked for shapes
plus "everything useful for beautiful, modern, complex slides." Scoped here
to a concrete, bounded set rather than left open-ended — every item below is
a real `python-pptx` capability, none require new dependencies or theme-XML
surgery.

### 11.2 New models (`models.py`)

- `ShapeSpec`: `shape_type` (curated `Literal` over `MSO_SHAPE`/`MSO_AUTO_SHAPE_TYPE`
  members: rectangle, rounded_rectangle, oval, triangle, diamond,
  arrow_right/left/up/down, line, star, pentagon, hexagon, chevron, cloud),
  `left`/`top`/`width`/`height` as **fractions of slide size (0.0–1.0)** —
  not absolute inches — so a shape's position is correct regardless of
  whether the deck uses the default blank presentation or an uploaded brand
  template with different slide dimensions; `fill_color`/`line_color`
  (hex `#RRGGBB`), `line_width_pt`, `rotation` (degrees), optional `text` +
  `text_style` (a shape can double as a labeled diagram node).
- `TextStyle`: `font`, `size_pt`, `color` (hex), `bold`, `italic`, `align`
  (left/center/right) — all optional, applied where set and left at the
  layout's inherited default otherwise.
- `BackgroundSpec`: `kind` (`solid`/`gradient`/`image`), `color` (solid),
  `gradient_colors` (exactly 2 hex colors, simple 2-stop diagonal gradient),
  `image_ref` (full-bleed picture — reuses the existing `document_content`
  image-resolution path, §4.3; implemented as a picture shape sized to the
  slide and sent to the back, since `python-pptx` has no first-class
  "background image" primitive).
- `ThemeSpec` (new field on `GeneratePptxArgs`): deck-wide defaults —
  `heading_font`, `body_font`, `primary_color`, `background` — applied to
  every slide that doesn't set its own override.
- `SlideSpec` gains: `background: BackgroundSpec | None`,
  `title_style` / `body_style: TextStyle | None`,
  `shapes: list[ShapeSpec] | None` (a decorative/diagram layer on top of
  whatever the slide's `kind` already renders — not a new `SlideKind`, since
  shapes are additive to any slide type, e.g. an arrow annotation on a chart
  slide).
- `ChartSeries` gains `color: str | None` (hex) — honored for
  bar/column/line/area/radar (series-level fill/line color); **not** wired
  for pie/doughnut in this pass (those color per-point, not per-series, a
  different and more involved API path — left for a future pass if wanted).

### 11.3 Bullets: inline `**bold**`/`*italic*`

`BulletItem.text` gains lightweight inline-markdown parsing (bold/italic,
mirroring the small parser pattern already used by
`ppt_filler/inline_markdown.py` and `writable_document/inline.py` —
reimplemented locally per this package's existing no-cross-import stance,
§4.3) so an agent can emphasize key terms within a bullet without a separate
styling call per word.

### 11.4 Guardrails

`MAX_SHAPES_PER_SLIDE = 20` (engineering guardrail, same spirit as §9 item
5). Hex colors validated with a `field_validator` (`^#[0-9A-Fa-f]{6}$`);
invalid input raises the same actionable `ValueError` pattern the builder
already uses elsewhere (agent self-corrects, no silent fallback).

### 11.5 Non-goals (this pass)

- No shadow/glow/reflection effects (no stable high-level `python-pptx` API;
  would mean raw OOXML XML manipulation — real scope creep for a styling
  pass).
- No rewriting the deck's actual theme XML (`theme1.xml`) — fonts/colors are
  applied per-run/per-shape at build time instead, which is what the
  existing `python-pptx` API reliably supports.
- No pie/doughnut per-point coloring (§11.2).
- No freeform/curved shapes (curated `MSO_SHAPE` set only).

### 11.6 Verification

Extends the existing test files (`test_deck_builder.py`: one shape/style per
slide variant, background solid/gradient/image, theme defaults vs. per-slide
override; `test_capability.py`: background `image_ref` folded into the same
prefetch path as content images) — no new test files needed. Same
`make code-quality` / `make test` / `fred-performance-reviewer` /
`/code-review` gate as the rest of this RFC's build plan (§10).

---

## 12. Amendment (2026-09-16) — curated palettes, adaptive layout, procedural
backgrounds (v1.2)

**Status:** approved by developer for implementation (chat confirmation,
2026-09-16) — scoped here before coding.

### 12.1 Problem

Real-world use of v1.1 (§11) surfaced three concrete quality gaps, diagnosed
by actually rendering decks through the same LibreOffice engine that serves
the PDF preview (not guessed):

1. **Decks often ship with a plain white background and mismatched colors.**
   Verified this is NOT a rendering bug — a `BackgroundSpec(kind="solid"/
   "gradient")` renders perfectly (confirmed visually). It is a *prompt
   reliability* problem: asking the model to both (a) remember to set
   `theme.background` every time and (b) invent hex colors that look good
   together from scratch is asking an LLM to do color theory on the fly,
   which it does inconsistently.
2. **Table/text layout is sometimes cramped or awkward.** `SlideSpec` gives
   the model no lever over box/font sizing for tables — a 3-row and a
   15-row table get the same fixed box and default font size. This is not a
   prompt problem: there is no field to ask for.
3. **Backgrounds are visually flat.** `BackgroundSpec` only supports a solid
   fill, a 2-stop linear gradient, or a static uploaded image — no way to
   get a modern "abstract shapes / soft blobs / diagonal bands" background
   without a design asset the agent doesn't have.

### 12.2 Design

**(a) Curated theme presets** (`models.py`): a small, hand-designed catalog
of named presets (`palettes.py`, ~8 entries — e.g. `corporate_navy`,
`startup_electric`, `sustainability_green`, `healthcare_calm`,
`creative_bold`, `editorial_warm`, `minimal_mono`, `sunset_gradient`), each
defining a complete, contrast-checked visual identity: `heading_font`,
`body_font`, a "strong" background+text treatment (for `title`/
`section_header` slides) and a "soft" background+text treatment (for
content slides), plus an `accent_color` for shapes/chart series. `ThemeSpec`
gains `preset: str | None`; `deck_builder` resolves it once per build and
applies the strong/soft split **per slide kind** automatically — a slide's
own explicit `background`/`title_style`/`body_style` still wins when set
(same override precedent as `theme.background`, §11.2). This is the
recommended path in the tool description: pick a preset by name and mood
match, don't invent colors from scratch. Manual `theme.primary_color`/
`background` fields remain available for advanced control and are unchanged.

**(b) Adaptive table layout** (`deck_builder.py`): table cell font size is
computed from row count instead of left at the default (a fixed size-tier
step function, floor/ceiling bounded), and column widths are distributed
proportionally to each column's header/content text length instead of
python-pptx's equal-width default — both cheap, deterministic, pure
functions, no new dependency.

**(c) Procedural pattern backgrounds** (`background_render.py`, new,
sibling to `chart_render.py`): `BackgroundSpec.kind` gains `"pattern"`
(+ `pattern: Literal["soft_circles","diagonal_bands","dot_grid"]`,
`accent_color` — falls back to `theme.primary_color` like every other
color field in this capability). Rendered via `matplotlib` (already a
dependency) as a full-bleed PNG at build time, reusing the exact same
embed-as-background-picture + `_send_to_back` mechanism `kind="image"`
already has (§11.2) — no new placement code, only a new pixel source.
Deterministic compositions (fixed geometry, colors as the only input) — no
randomness, so output stays predictable and testable. Theme presets may set
a pattern as their "strong" treatment for extra visual sophistication.

### 12.3 Non-goals (this pass)

- No free-form/arbitrary procedural patterns (LLM-described shapes) — three
  curated, tasteful compositions only, same "curated over generative"
  philosophy as (a).
- No adaptive sizing for charts/images (aspect-fit already handles them,
  §11 code-review fix) or for shapes (fixed fractional coordinates by
  design, §11.2) — table text is the concrete, reported pain point.
- No per-cell table styling (colors/fonts per cell) — font-size and column
  width only.

### 12.4 Verification

Extends the existing test files — no new ones except `test_background_render.py`
(sibling to `test_chart_render.py`, same pattern: each pattern produces
valid, non-empty, correctly-sized PNG bytes). `test_deck_builder.py`: preset
resolution (strong vs soft per slide kind, explicit override still wins),
table font-size tiers, column-width proportionality. Visual sanity check via
the same real-LibreOffice-render approach used to diagnose this amendment in
the first place (not just XML-marker assertions) before considering it done.
Same `make code-quality` / `make test` / `fred-performance-reviewer` /
`/code-review` gate as §10/§11.

---

## 13. Amendment (2026-09-21) — reusing an individual template slide (v1.3)

**Status:** approved by developer for implementation (chat confirmation,
2026-09-21) — scoped here before coding, implemented same session.

### 13.1 Problem

A developer reported that an agent using this capability "doesn't manage to
pick the right template slides at the right time and place them in the right
location," and asked whether that was a system-prompt problem or a code
problem. Diagnosis: code. §4.1/§4.2.1/§9.3 deliberately designed the optional
brand template as a **passive theme source** — masters/theme/palette only,
never parsed, never individually addressable. `SlideSpec.kind` (§4.3) is a
fixed set of 7 generic kinds; there was no field an agent could use to say
"use template slide 4," and `deck_builder._resolve_layout` only does
best-effort **layout**-name/index matching, never full-slide reuse. No amount
of system-prompt tuning could fix this — the tool schema couldn't express the
request. This amendment reopens §4.1/§9.3's "theme-only" decision for the
specific case of an agent wanting to reuse one of the template's own
pre-designed slides.

### 13.2 Design

**(a) Reference by position, duplicate-and-fill (not verbatim reuse).**
`SlideSpec` gains `template_slide_index: int | None` (0-based). When set,
`deck_builder._duplicate_slide` deep-copies that exact slide from the
uploaded template — its background, decorative shapes, and placeholder
layout — into the output deck, instead of `_resolve_layout` picking a generic
layout. The slide's `kind` still governs which of `title`/`bullets`/
`image_ref`/`table`/`chart` gets written into the duplicated slide's
placeholders, via the exact same fill functions (`_set_title`,
`_fill_bullets_on_slide`, `_take_content_box`, etc.) already used for a
layout-based slide — chosen over verbatim/unmodified reuse because the
reported need was pre-designed layouts filled with new content, not fixed
boilerplate slides.

**(b) No per-turn template fetch — catalog computed at config-save time.**
`tools(ctx)` is synchronous (§4.1: no `middleware()` escape hatch to await a
fetch from), so a per-agent listing of the template's own slides (index +
title + a same content-kind tag) is computed once in `validate_config`
(`template_inventory.describe_template_slides`, mirroring `ppt_filler`'s
placeholder-schema extraction) and stored as
`PptxGeneratorConfig.template_slide_catalog`. `tools()` splices it into the
tool description only when non-empty — the zero-config/no-template case
(§5) is completely unaffected. Capped at 50 slides listed (mirrors
`MAX_SLIDES`) so a pathological "template" can't inject an unbounded block
into the prompt every turn. A catalog entry is tagged `image`/`table`/
`chart`/`text` only when the shape is an actual PLACEHOLDER — the only kind
of shape `_body_placeholder`/`_take_content_box` ever replace; a decorative,
non-placeholder picture/table/chart is left untagged since setting
`image_ref`/`table`/`chart` would never touch it.

**(c) The template's own source slides never leak into the output.**
`deck_builder.build()` already opened the template as the base
`Presentation` (to inherit masters/layouts) but never removed its original
slides — an existing latent bug (only masked because the only tested
template was a blank `Presentation()` with zero slides). Now that a
template's slides are meaningful raw material, `build()` captures them
before the generation loop and strips them from the output afterward
(`_strip_template_source_slides`) — only the agent's explicitly generated
slides appear, same contract as the non-template path.

**(d) Preset/theme precedence.** A `template_slide_index` slide skips the
curated theme-preset's automatic background/font injection (§12) — it
already has a real designed look, and the preset exists specifically to fix
mismatched colors on slides that don't. An explicit per-slide `background`/
`title_style`/`body_style`, or a deliberately-set deck-wide `theme` field,
still applies on top.

**(e) Unsupported shapes rejected, not corrupted.** python-pptx has no
built-in slide-duplication API; `_duplicate_slide` deep-copies the shape
tree by hand and re-wires picture (`a:blip`) relationships to the new slide
part, recursing into group shapes. A chart, linked/embedded OLE object, or
media shape — each carrying relationships (an embedded workbook, a linked
payload) far more involved to re-wire — is rejected with an actionable
`ValueError` naming the offending `template_slide_index`, rather than
silently producing a `.pptx` with dangling relationship references.

### 13.3 Non-goals (this pass)

- **No verbatim/unmodified slide reuse.** Every `template_slide_index` slide
  still gets its `kind`-appropriate content written in; there is no "insert
  this exact slide untouched" mode (deferred if a real boilerplate-slide need
  surfaces — e.g. a fixed legal/contact slide inserted as-is).
- **No reference by title/name.** Position-only (§13.2a) — simpler and more
  robust to a template being re-uploaded with re-ordered slides than a
  text-matching scheme would be.
- **No fix to `_DEFAULT_CONTENT_BOX`'s fixed-size fallback** for a
  `template_slide_index` slide whose duplicated shapes contain no
  placeholder at all (rare — a slide picked specifically for reuse
  typically has one) — pre-existing behavior, shared with the non-template
  path, out of scope for this amendment.

### 13.4 Verification

New `template_inventory.py` module +
`tests/test_template_inventory.py` (catalog text, placeholder-only tagging,
title truncation, size cap). `test_deck_builder.py`: duplicate+fill per
`kind`, decorative-shape/background preservation, picture blip re-wiring,
out-of-range/no-template errors, unsupported-shape rejection (including
nested in a group), source-slide stripping, preset-skip precedence.
`test_capability.py`: `validate_config` computes the catalog (including the
zero-slide/theme-only case), `tools()` splices it into the description only
when present. `make code-quality` / `make test` green;
`fred-performance-reviewer` run (confirmed: the new duplication work stays
inside the existing `asyncio.to_thread(build_deck, ...)` offload, and the
config-save-time catalog scan was moved into the existing template-open
`to_thread` call rather than left inline on the event loop);
`/code-review` self-review run and findings triaged — two real bugs in
the new code fixed (unsupported-shape check now recurses into groups; the
catalog only tags placeholder-backed shapes and gained a slide-count cap),
several more findings identified in pre-existing code adjacent to this
change but left out of scope per the repo's scope-discipline rule (bundling
unrelated cleanup into a single-purpose change makes both harder to review).

---

## 14. Amendment (2026-09-21) — layout resolution and content-box sizing

**Status:** approved by developer for implementation (chat confirmation,
2026-09-21) — scoped here before coding, implemented same session.

### 14.1 Problem

A developer reported, backed by a real generated deck: the same generic
"title + small content" slide look kept recurring across their deck no
matter which brand template they uploaded, and asked for a real fix (not
just the §13 opt-in reuse path). Root cause, confirmed by reading
`deck_builder._resolve_layout`: when a template's layout NAMES didn't match
`_LAYOUT_NAMES_BY_KIND`'s hardcoded English strings (the normal case for any
non-default, non-English-named brand template), the fallback picked a layout
by a fixed numeric INDEX per kind — and `_LAYOUT_INDEX_FALLBACK_BY_KIND` sent
`bullets`, `image`, `table`, AND `chart` all to the SAME index. Four
structurally different content kinds collapsed onto one physical layout
regardless of what the template actually offered, independent of which
template was uploaded — exactly the reported symptom.

Separately, the same PDF surfaced generated text overflowing past the
template's footer on slides whose fallback content box came from
`_DEFAULT_CONTENT_BOX`, a fixed `Inches(0.5, 1.5, 9.0, 5.0)` box sized for
the default 10x7.5in presentation — never adjusted for an actually
differently-sized or -proportioned uploaded template.

### 14.2 Design

**(a) Structural layout matching replaces the index fallback.**
`_resolve_layout` still tries name-matching first (a real name match is a
strong signal). When it fails, `_best_structural_layout_match` scores every
layout the template actually has by its own placeholder makeup — a count of
"real content" placeholders (`_GENERIC_CONTENT_PLACEHOLDER_TYPES`: BODY,
OBJECT, and their vertical variants — furniture placeholders like date/
footer/slide-number are excluded, or they swamp the count) against what each
kind wants (`_WANTED_GENERIC_CONTENT_BY_KIND`), plus two targeted
preferences: `image` prefers a layout with a real PICTURE placeholder,
`title` prefers one with a real SUBTITLE placeholder. `_LAYOUT_INDEX_FALLBACK_BY_KIND`
is deleted outright (consolidation-phase bias toward deletion) — the
structural match never needs a numeric guess, and an empty `layouts` list now
raises a clear, agent-facing `ValueError` instead of an unhandled `IndexError`.
`bullets`/`table`/`chart` still legitimately share one generic-content layout
when a template only offers one — that's the template's actual shape, not a
bug; `image`/`title`/`two_content` no longer do.

**(b) The fallback content box scales with the actual presentation.**
`_DEFAULT_CONTENT_BOX` becomes `_default_content_box(presentation)`,
computed as fixed fractions (`_DEFAULT_CONTENT_BOX_FRACTIONS`) of
`presentation.slide_width`/`slide_height` instead of absolute `Inches()` —
the same fix `_fractional_box_to_emu` already applied to decorative shapes
(RFC §11.2) extended to every other fallback-box call site (`_set_title`,
`_set_secondary_text`, `_take_content_box`, `_fill_bullets_on_slide`,
`_two_content_boxes`), all now threaded a `presentation` parameter for it.

### 14.3 Investigated, not fixed — title/shape overlap

The same deck also showed a decorative shape drawn squarely over a slide's
title text. `_occupied_content_boxes` deliberately excludes the title
placeholder from its overlap guard (RFC §12, documented at the time as
intentional: the title placeholder's box is far bigger than its actual
rendered text, so checking it would false-positive-reject a legitimate
corner accent). A same-session attempt to reject a shape centered on the
title's own box was implemented, tested, and **reverted**: measured against
the actual default template, the title placeholder's box already spans
~90% of the slide's width and ~17% of its height — any reasonably-sized
corner accent's center falls inside that box too, so the fix broke the exact
"accent near the title" cases §12's tests already lock in (regression
confirmed, not hypothetical). python-pptx exposes no text-measurement API to
find the title's actual rendered footprint inside that box, so a
geometry-only fix cannot distinguish "accent near an oversized title box"
from "shape covering the title text" — pursuing it further risks exactly the
"magic threshold tuned against one bug report" failure mode this repo's own
review process flagged elsewhere in this package. Left as a known gap;
mitigations that don't need a code change: avoid placing `shapes` on
`title`/`section_header` slides, or keep shape `text` short so an
accidental overlap is less likely to obscure meaningful title text.

### 14.4 Non-goals (this pass)

- **No text-measurement/rendering integration** to compute a title's real
  glyph extent (would need a font-metrics or headless-render dependency —
  real scope creep for what surfaced as a two-line bug report).
- **No change to the overlap threshold or background-shape exclusion**
  (`_SHAPE_OVERLAP_AREA_FRACTION_THRESHOLD`, `_BACKGROUND_SHAPE_AREA_FRACTION`)
  — unrelated to what was reported, out of scope per the repo's
  scope-discipline rule.

### 14.5 Verification

`test_deck_builder.py`: structural fallback tests against a template whose
layouts are all renamed to defeat name-matching (`_custom_named_template_bytes`)
— `image` lands on the picture-placeholder layout, `title` and `bullets` no
longer collapse onto one layout, `two_content` picks the 2-placeholder
layout, an empty-layouts template raises the clear error;
`_default_content_box` scales with a non-default slide size. All 84
pre-existing layout/box-dependent tests re-verified green (the default
template's own layout names still match `_LAYOUT_NAMES_BY_KIND` exactly, so
name-matching — unchanged — still resolves them first). `make code-quality`
/ `make test` green.

---

## 15. Amendment (2026-09-22) — content-based zone detection for a
chapter-divider slide with inverted placeholder types

**Status:** approved by developer for implementation (chat confirmation,
2026-09-22) — scoped here before coding, implemented same session.

### 15.1 Problem

A developer reported that a real customer brand template's chapter-divider
slides ("intercalaire de chapitre") were being filled backwards: the small
numbered badge shape ("01") received the full chapter name (overflowing its
box, illegible), while the real title shape kept the template's own default
placeholder text. Confirmed against the template's actual XML: for this
slide, `type="title"` is the numbered badge and a generic `type="body"`
placeholder is the real chapter title — the opposite of every other slide in
the same template (covers, content). §13.2(a)'s duplicate-and-fill mechanism
assumed a `template_slide_index` slide's placeholder TYPES line up with
their visual role the same way a generic layout's do — `_set_title` always
writes to `slide.shapes.title` (python-pptx's TYPE-based notion of "the
title placeholder"), `_set_secondary_text` to the first non-title-type
placeholder. That assumption is false for this template's divider slides,
and nothing in §13 anticipated a template author assigning types backwards
on a subset of slides only.

### 15.2 Design

**(a) Detect the two zones by their template-authored DEFAULT TEXT, not
type — for `kind="section_header"` + `template_slide_index` only.**
`_section_header_badge_and_title_placeholders` (`deck_builder.py`) inspects
the duplicated slide's placeholders (before any write): if there are
exactly two, and exactly one's default text matches `^\d{2}$`, that one is
the badge zone and the other (if it has non-empty default text) is the
title zone. Any other shape — 1, 3+ placeholders, zero or 2+ numeric
matches, an empty non-badge placeholder — returns `(None, None)`, and the
slide falls back to the existing type-based `_set_title`/`_set_secondary_text`
path unchanged. This keeps every template that does NOT have this inversion
(the common case) on the exact behavior §13 already shipped.

**(b) The badge number is computed, never supplied by the caller.**
`SlideSpec` gains no new field. `build()` tracks how many badge-matched
`section_header` slides it has already built and passes the next 1-based
ordinal (zero-padded to 2 digits) into `_fill_section_header_from_template`
— an agent constructing the deck only ever sets `title` (the chapter name),
the same field every other slide kind already uses for its heading. This
also forecloses an entire class of bug (a caller passing a stale, duplicate,
or out-of-order number) by construction, rather than by validation.

**(c) Full replace, verified.** Both zones are written with
`text_frame.text = ...` (python-pptx's own full-replace assignment — clears
every existing paragraph/run, never appends) exactly like every other
`_set_title`/`_set_secondary_text` call in this file. Immediately after
writing, `_fill_section_header_from_template` re-reads both zones and raises
`ValueError` if the badge isn't exactly one paragraph/one run matching the
number just written, or the title zone's text isn't exactly `spec.title` —
so a template whose placeholder locks formatting in an unexpected way fails
the build loudly instead of shipping a half-filled divider. A missing
`spec.title` on a badge-matched slide is also a hard error (a chapter
divider can't ship with the template's own default title text).

### 15.3 Non-goals (this pass)

- **No new `SlideSpec` field for the badge number** — deliberately computed
  (§15.2b) rather than added to the public tool schema, since every
  candidate use case is "the Nth divider" and an explicit field would just
  reopen the same staleness bug it prevents by construction.
- **No generalization beyond the two-zone, one-numeric-shape shape.** A
  three-zone divider (e.g. badge + title + a short subtitle line) is out of
  scope until a real template needs it — `(None, None)`'s safe fallback
  means such a template degrades to the pre-existing type-based fill rather
  than guessing.

### 15.4 Verification

`test_deck_builder.py`: badge/title filled by content on an inverted
template across several dividers with correctly incrementing numbers, badge
written as a single run/paragraph (no stacking), a non-inverted
`section_header` template slide keeps the original type-based fill
unchanged, a badge-matched divider with no `title` raises, numbering only
advances for badge-matched slides (a non-divider `template_slide_index`
slide in between doesn't consume an ordinal). `make code-quality` / `make
test` green (109 tests in `test_deck_builder.py`, 171 in the package).
Manually verified end-to-end against a synthetic template reproducing the
real template's inverted structure: a 4-chapter deck built cleanly with
badges "01"-"04" and no leftover default text in any zone.

---

