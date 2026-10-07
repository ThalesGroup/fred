## Why

Teams want an agent that produces a PowerPoint deck from a few instructions, on the corporate template their company hands out — or from nothing when they have none. `ppt_filler` only fills a deck whose slides carry `{{key}}` markers; that annotation step is why it is not used. `ppt_builder` must work from a plain, unannotated template (GitHub issue #2679).

A first version shipped on this branch and failed end to end: on a real corporate deck the cover came back on almost every slide. A five-expert review traced it to the design, not to tuning:

- **Analysis misreads real templates.** A free text box becomes a slot only when its text matches a sample-text lexicon, so example slides written with real corporate text are classified `title`/`section`: on the reference deck 6 of 8 patterns came out title-only.
- **The model is asked to pick slides it cannot see.** `pattern` is the first schema property, an enum of ~56 opaque ids (`slide:257`) in three namespaces; an exact id is honoured with no fit check, and the tool never asks for a retry.
- **Silent fallbacks pick the cover.** `plan.resolve()` ends on `included[0]` (the cover); `DEGRADATION` maps section ↔ title ↔ statement.
- **The composition layer competes with the template** instead of filling it: 2-6 short bullets get a drawn layout by default.
- **OOXML defects** in duplication: slide-to-slide hyperlink relationships resurrect removed slides, notes are never copied, `p:clrMapOvr` is lost, per-level formatting is lost in multi-level bodies.

The reliable approach in the market (Copilot in PowerPoint, Anthropic's pptx skill, PPTAgent) is the same everywhere: label the template's example slides once into functional archetypes with a slot schema, then generate by **duplicating the chosen reference slide and editing only its text and images**, choosing slides in code from a content outline, and validating after render.

## What Changes

- **Park the composition layer.** `components.py`, `compose.py`, `composed_render.py`, `layout.py`, `design_system.py`, the design-system/canvas/icon extraction in `analysis.py`, `PatternSource="composed"`, the icon catalogue, their tests and the `ppt-builder-composition` OpenSpec change leave this branch for a parked branch. Nothing is ever drawn: the template is the only source of design.
- **Archetype labelling at upload, in the background.** Each example slide is rendered to an image and labelled by a vision-capable model: functional kind, purpose of each text slot, max items, reusable or not. Deterministic analysis still provides geometry, slots, repeat groups and capacities; vision supplies meaning. A "Use a vision model" setting (default on, forced off with an explanation when no vision-capable model is available) and an optional vision-model selector control it. Saving the agent never waits for it; the form shows "analysis in progress" until it completes.
- **Every text shape is a slot by default** on an example slide, unless its text repeats on ≥ 2 slides or it is a footer/date/slide-number field. The sample-text lexicon stops deciding what is fillable; it serves only the after-render check.
- **The code chooses the slide.** The model writes content per slide with an optional `kind` from a small closed vocabulary (last in the schema, inferable from content shape). A deterministic assigner maps each slide to the best archetype — an example slide (duplicate + fill), else a layout — under deck rules: cover exactly once at position 1, closing at most once and last, no three identical archetypes in a row, capacity check. Pattern ids leave the tool schema.
- **No silent fallback.** When no archetype can hold a slide, or original sample text survives the render, the tool returns a structured error naming the slide and what fits, and the model corrects (repair loop) instead of receiving a wrong deck.
- **Built-in Fred template.** A real `.pptx` with example slides, designed by the developer, ships in the package and goes through exactly the customer path; the in-memory generated `theme.py` serves as the interim built-in source until that file lands, then is deleted.
- **Agent unavailable until its template is analysed.** The agent cannot be chosen in chat while analysis is pending, running, failed or interrupted; the form shows the error and a "re-run analysis" action. The tool's own refusal stays as defence in depth.
- **OOXML fixes** in duplication: only image/media/external-hyperlink relationships are copied, notes and colour-map overrides are copied, per-level paragraph formatting survives a multi-level fill.
- **Review panel simplified**: thumbnail + vision label per slide; the author may relabel or exclude; zone-role editing goes.
- **Opt-in evaluation harness** (outside `make test`): prompts × templates through the real tool and configured model, with deck-quality metrics. Its results are this change's verification evidence.
- Kept: slide duplication with shared media, fill by role, overflow control and `text_metrics`, repeat-group detection and item-count adaptation, lost-content reporting, PDF preview / side pane / download, author overrides, the "Presentation builder" pack.

## Capabilities

### New Capabilities

- `ppt-builder`: generating a PowerPoint deck from chat on a labelled corporate template or the built-in Fred template — background template analysis, author review, deterministic slide assignment with repair, rendering and delivery.

### Modified Capabilities

- none — `ppt_filler` keeps its contract; the preview chat part and side pane are reused.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: deleted `components.py`, `compose.py`, `composed_render.py`, `layout.py`, `design_system.py`, `theme.py`; new `labelling.py` (vision), `assign.py` (deck assigner, replaces `plan.resolve` and its scoring), `analysis_job.py` (background analysis and its store), `checks.py` (after-render checks); reworked `analysis.py`, `models.py`, `plan.py`, `render.py`, `tools.py`, `capability.py`, `preview.py`; bundled `assets/fred_template.pptx`; an `eval/` harness; an owned table + Alembic tree (design D4).
- `libs/fred-sdk` + `libs/fred-runtime`: a turn-free capability model port added to `RuntimeServices` and injected on the save path and the background path; an optional `supports_vision` flag on model profiles (design D3).
- `apps/fred-agents/config/models_catalog.yaml`: vision flag on capable profiles.
- `apps/frontend/src/rework/features/capabilities/ppt_builder/`: analysis-status state, simplified review dialog, regenerated API slice; `locales/{en,fr}`.
- Stored agent configs: `ANALYSIS_VERSION` bump; older inventories stay in use and are recomputed in the background when first seen. `PatternSource="composed"` disappears; no released config holds it.
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` §8 entry (new `RuntimeServices` port), `AUTHORING.md` (turn-free model port), `COMPONENT-UX.md` (review panel), package `README.md`; migration note per `docs/swift/ops/MIGRATION-GUIDES.md`.
- Out of scope: the control-plane validate-config timeout (handled separately).
- Tracking: GitHub issue #2679.
