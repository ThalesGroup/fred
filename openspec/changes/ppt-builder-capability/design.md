## Context

`libs/fred-capability-ppt-filler/` already owns everything around a deck except its creation: bounded python-pptx work (`concurrency.py`), text-run traversal that survives run splitting (`traversal.py`), image placement with folder resolution (`fill.py`, `folder_resolution.py`), LibreOffice PDF conversion, the `ppt_preview` chat part, the side pane and the download. Nothing in the repo adds a slide, instantiates a layout or duplicates an example slide.

Constraints that shape the approach:

- `validate_config` receives `SaveContext.services` (asset store, folder resolution); no model call is guaranteed on the save path, so analysis must be deterministic.
- One chat-part kind per owner: `ppt_builder` cannot re-declare `ppt_preview`. It returns the part `ppt_filler` declares (same package, always installed together) and declares its own side-panel widget id pointing at the same pane component.
- The pod mounts a capability router with the caller's bearer available (`Security(oauth2_scheme)`), and Knowledge Flow serves agent config assets at `teams/{team}/agents/{instance}/config/{key}` to team members.
- Real reference: the Thales FR template (20 typed layouts, 38 example slides). Its free-form slides (agenda with 8 numbered groups, 4 KPI cards, 3/6 icon cards, 3 process steps, 6-year timeline, team pairs, contacts) are the bar the heuristics must clear; its icon banks, chart and table slides are the cases to exclude by default.

## Goals / Non-Goals

**Goals:**

- Deterministic, testable analysis whose result the author can read and correct.
- A generation path that only ever fills existing zones — the corporate design cannot be broken by the agent.
- One shared package: no duplicated preview, conversion or concurrency code.

**Non-Goals:**

- Charts, SmartArt, tables as generated content (kept verbatim when part of a fixed slide, otherwise excluded).
- Vision-based checking of the rendered slides.
- Editing a generated deck in place; regeneration from an amended plan is the correction path.
- Persisting chat corrections into the agent configuration.

## Decisions

### D1. Second capability in the same package, sharing the preview part

`PptBuilderCapability` lives in `fred_capability_ppt_filler/builder/` with its own `fred.capabilities` entry point. It reuses `PptPreviewPart`, `convert_office_bytes_to_pdf`, the heavy-job slots, `_place_images_on_slide`-style image embedding and the folder listing tool. Alternative — a separate package depending on ppt-filler — was rejected: it adds a release coupling for no isolation benefit, and the shared chat part would still have to be imported.

### D2. Inventory model persisted in the config; overrides separate

`PptBuilderConfig = { template_key, inventory: TemplateInventory | None, overrides: list[PatternOverride] }`. The inventory is recomputed from the real bytes at every upload (same doctrine as `ppt_filler.schema_slides`) and is small (tens of patterns, tens of zones each). Overrides are keyed by pattern id + zone key. Pattern ids are stable across re-uploads of the same file: `layout:<index>` and `slide:<xml slide id>`; zone keys are `ph:<idx>` for placeholders and `sp:<shape id path>` for free shapes (group path joined by `/`). Alternative — persist only overrides and re-analyse per turn — rejected: analysis of a 4 MB deck is CPU work that should not run on every turn.

### D3. Analysis pipeline (deterministic, ordered by confidence)

1. **Placeholders first.** Layouts: signature from placeholder types and geometry. Slides: `is_placeholder` shapes keep their type. A `BODY` placeholder at the top band (top < 12 %, height < 8 %) is a _heading_, not a body (the reference template's "Bullet Points" layout types its headings as BODY).
2. **Shared decoration.** Text identical on ≥ 3 slides, and pictures smaller than 6 % of the slide area sitting in a corner, are never zones.
3. **Free text boxes.** Only boxes whose text matches the sample-text lexicon (`Cliquez ici`, `Changez ce texte`, `Titre du`, `Lorem ipsum`, `Nom`, `Poste`, `Texte`, `Insert`, `Type here`, …, multilingual, plus "single short generic label" heuristics) or are the largest text on a slide without a title placeholder. Role by font-size rank and geometry: largest and top → `heading`; ≥ 40 pt and ≤ 4 characters → `number`; ≤ 3 lines and under a picture → `caption`; small and directly above/below a sibling zone → `label`; otherwise `body`.
4. **Repeated groups.** Sibling groups (or ungrouped clusters aligned on a grid) with identical structure signature (multiset of shape kinds + rounded font sizes + text-box count) and ≥ 3 occurrences → one `RepeatGroup` with `count` and per-item zones ordered reading-wise. The agenda, KPI, icons, steps, timeline and team slides of the reference template all resolve this way.
5. **Pictures.** Picture placeholders are image zones. Free pictures are decoration unless they are the largest shape on the slide (≥ 25 % area) → replaceable image zone.
6. **Intent** from the zone set: `title` (title + subtitle, no body, first slide or cover-named layout), `section` (single large title), `agenda` (repeat group of number+heading), `content` (title + body), `two_columns` (title + two bodies), `comparison` (two headings + two bodies), `image_text` (title + body + image), `cards` (repeat group of heading/body/(number|image)), `steps` (repeat group with ordered numbers), `statement` (one large centred body, no title), `contact` (name/role/phone/email labels), `fixed` (no zone).
7. **Annotations** override: a shape name from a known vocabulary (`title`, `subtitle`, `heading`, `body`, `caption`, `number`, `label`, `image`, `keep`, optionally suffixed `heading_2`; PowerPoint's automatic `<words> <n>` names never count) sets the role; an `intent:` line in the speaker notes sets the intent and a `label:` line the label; `{{key}}` markers are honoured as body zones so a `ppt_filler` deck still analyses.
8. **Exclusion by default**: a chart or table as the slide's main content, ≥ 20 pictures and no body zone (icon bank), or layouts with zero placeholders (decorative masters). Layouts and example slides with the same intent are both kept; the example slide is flagged `preferred` because the designer put it in the deck.

Alternative considered: an LLM pass at save time to classify ambiguous slides. Rejected for V1: no model port is guaranteed on the save path, and a deterministic pass is what makes the review widget trustworthy and the tests meaningful. The tool description carries each pattern's derived description, so the agent's own judgement does the semantic matching at chat time.

### D4. Plan model: semantic fields, patterns declare what they consume

One `SlidePlan` shape for every pattern: `pattern` (enum of inventory ids), `title`, `subtitle`, `body: list[str]` (bullets, `\n` and leading `-` for sub-levels), `columns: list[{heading, bullets}]`, `items: list[{number, heading, text, value, label, image}]`, `image`, `images`, `notes`. The renderer maps these onto a pattern's zones by role (`heading` ← title, `body` ← bullets, repeat group ← items, …). Alternative — one nested args model per pattern, as `ppt_filler` does — rejected: 25 patterns × 10 zones yields a schema the model handles worse than a short semantic vocabulary plus a catalogue in the tool description.

### D5. Rendering

- Work on a copy of the template: layouts are instantiated with `slides.add_slide(layout)`; example slides are duplicated by deep-copying the `spTree` and re-creating the slide's image and media relationships (the known python-pptx pattern, wrapped in one helper with a round-trip test); every original example slide is removed at the end, and the resulting slide order is the plan's.
- Fill by zone role through the existing run-merging traversal so the first run's style is inherited; bullets become paragraphs with `level` from indentation. Unfilled fillable zones are emptied; unfilled image placeholders and unused repeat-group items are deleted.
- Overflow: estimate lines from box width, font size and an average glyph width, shrink through `normAutofit fontScale` down to 70 %, then truncate at a word boundary and report the zone in the tool result.
- The built-in theme is a `.pptx` shipped in the package with one layout per intent, analysed through the same pipeline at import time (cached), so "no template" is not a special code path.

### D6. Author review surface

- Routes: `POST /analyze` (multipart → inventory + errors + summary) and `POST /preview` (multipart → PDF, one page per pattern in inventory order, produced from a deck that instantiates each layout with its zone names and copies each example slide). Both stateless and bounded like `ppt_filler`'s.
- After save, the patterns PDF is stored beside the template as a second config asset and its Knowledge Flow path (`teams/{team}/agents/{instance}/config/…`) is kept in the config, so re-opening the form fetches the thumbnails with the user's bearer — no proxy route, no thumbnails in `tuning_json`.
- Widget: upload row → summary line → "Review patterns" opens the grid (thumbnail via react-pdf, editable label, intent `Select`, zone chips, include `Switch` small) → a card opens the central `Dialog` with the large thumbnail, numbered zone outlines drawn from the inventory's normalized geometry, and a role `Select` per zone. Pack options in the Simple view show only the upload row, the summary and the review button.

### D7. Execution model and prompt fragment

ReAct-only, like `ppt_filler`: the tool's `pattern` enum is built from the persisted inventory in the middleware. The middleware also overlays a prompt fragment with the working rules (plan first, telegraphic bullets, limits per zone, never write download links, correct by regenerating).

## Risks / Trade-offs

- [Heuristics misclassify a free-form slide] → the review grid makes every decision visible and correctable; a shape name fixes a stubborn case without touching the slide's content; excluded-by-default only applies to clear resource slides.
- [Slide duplication breaks on exotic parts (charts, embedded OLE, media)] → such slides are excluded by default; duplication copies only picture/media relationships and refuses (with an analysis warning) slides holding parts it cannot copy.
- [Generated deck size] → duplicated example slides share the template's image parts when the relationship target is the same part; measured on the reference template in tests.
- [Overflow estimation without font metrics] → conservative average glyph width plus the fontScale floor; the tool reports truncations so the agent shortens content rather than shipping clipped text.
- [Two capabilities on one agent] → both packs can be enabled; tools have distinct names; prompt fragments are distinct.

## Migration Plan

- Additive: a new entry point in an already-installed package; no table, no migration, no config version bump. Pods pick it up at next boot (`uv sync` in fred-agents for local dev).
- Rollback: remove the entry point; existing agents with the capability enabled are suspended with the standard "capability unavailable" reason.

## Open Questions

- Whether the `/preview` PDF should also be persisted for the built-in theme (it can be rendered on demand from the bundled file; decide from the widget's perceived latency once measured).
