## Why

The owner's template ships ready-made example slides with two and four charts, and `ppt_builder` ignores them at analysis: a slide with two ~24 % charts is excluded as `chart` (step 4c of `analysis.py` makes a zone only for exactly one main chart ≥ `_MAIN_CONTENT_AREA` 0.15, so `_apply_exclusions` then finds an unheld main chart), and a slide with four ~9.3 % charts is excluded as `unsupported_parts` (no chart is held, so its chart parts count as uncopyable). A designer who prepared these slides gets decks that never use them. GitHub issue #3144.

`ppt-builder-charts` listed "a second chart per slide" as a Non-Goal. Owner decision, 2026-10-16: this change reopens it explicitly. Multi-chart example slides prepared in the template must be used and filled, and the tool stays template-first: it fills the chart frames the template already has, it never invents a chart layout.

## What Changes

- **Analysis**: every top-level, non-`keep` chart frame of at least 5 % of the slide becomes a chart zone (up to 4 per slide), numbered in reading order (top to bottom, then left to right). A slide still holding a chart that is not a zone (too small, grouped, more than 4) stays excluded with its current reason. `ANALYSIS_VERSION` 16, so saved agents are re-analysed.
- **Plan**: a slide may send `charts: [chart, …]`; `chart` stays as the one-chart form, unchanged. The field is offered in the schema only when the template has a multi-chart slide.
- **Assignment**: a slide with k charts goes to a template slide with exactly k chart frames; when none exists, `needs_revision` names the counts the template offers and how to get there (split the slide, or merge charts).
- **Per-chart rules**: each chart follows every `ppt-builder-charts`, `ppt-builder-more-chart-types` and `ppt-builder-storytelling` rule on its own (types, theme accents, validation messages naming `charts[i]`, room measured from its own frame, example formatting kept when the type matches, one measure per chart). Each chart of a multi-chart slide needs a title; the slide keeps one takeaway and one source.
- **Edits**: `changes` paths `charts[i]…` (e.g. `charts[1].series[0].values[2]`); editing the `charts` list to another count moves the slide to a template slide with that count.
- **Model guidance**: the catalogue line says how many charts a slide offers (`charts×2`); the tool guide says when to use a multi-chart slide (related measures side by side, one per chart).
- **After-render check**: the delivered slide holds as many native charts as planned, each linked to its own chart part.
- Help Center (fr+en), package README, evaluation prompts, migration-note line.

Out of scope: drawing charts in free areas of a slide (no layout invented); combo charts (owner refusal in `ppt-builder-more-chart-types`); charts inside `items`/cards or `columns`; more than four charts per slide.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds requirement "Template slides with several charts are filled". Extends `ppt-builder-charts`, `ppt-builder-more-chart-types` and `ppt-builder-storytelling` (all in flight): applied and archived after them.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `analysis.py` (step 4c, `_apply_exclusions`, `ANALYSIS_VERSION`), `plan.py` (`SlidePlan.charts`, `chart_summary`/`zone_summary`), `assign.py` (chart-count match, misfits, `_chartless`/`_chart_options`, substitution text), `render.py` (`chart_host` → hosts, `_fill_chart` per pair, per-chart notes), `charts.py` (unchanged logic, called per chart), `story.py` (units, spread, figures per chart; titles required), `notes.py` (illustrative caption per chart), `changes.py` (`charts[i]` paths), `checks.py` (chart count after render), `tools.py` (schema field, catalogue, guide); regenerated built-in inventory; `eval/prompts.py`; tests.
- No new dependency. Frontend: Help Center `guides/prepare-powerpoint-template.md` (fr+en); no API or client change.
- Migration note: impact none → patch (a line in `docs/swift/ops/migrations/ppt-builder-capability.md` while unreleased). Templates are re-analysed automatically.
