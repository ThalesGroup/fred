# Verification: ppt-builder-capability

Evidence for WP9, WP11, WP12, WP13 and WP15 (design D11). Run on 2026-10-05 on a developer laptop. This is
evidence for the tool path and the analysis, not for the UI.

## How it was run

`make eval` in `libs/capabilities/fred-capability-ppt-filler/` (`eval/run_eval.py`,
opt-in, not part of `make test`):

- **Analysis**: the background job's own pipeline (`analysis_job._analyse`):
  deterministic analysis, patterns deck, LibreOffice PDF, vision labelling through
  a `CapabilityModelPort`. The **rules** variant uses the deterministic analysis
  only.
- **Agent**: `chat.mistral.small` (`mistral-small-latest`, temperature 0, reasoning
  off, as the admin default), built with `fred_core.model.factory.get_model` from
  `models_catalog.yaml`, the same factory fred-runtime uses. The model gets a short
  stand-in agent prompt, the capability's `_BUILD_INSTRUCTIONS` fragment, and the
  `build_presentation` tool built by `build_builder_tools` (same schema and
  description as in a pod). Each tool error is sent back to the model; at most 3
  repairs.
- **Vision model**: `chat.mistral.small` (flagged `supports_vision`).
- **Prompts**: 10 French and English business requests (`eval/prompts.py`): a
  cyber strategy, a quarterly review with KPIs, a project kickoff with a timeline
  and a team, a two-option comparison, an agenda-heavy committee, a 4-slide pitch,
  a 12-slide training, 9 sites on one slide (forces a repair), a 7-step process,
  an ESG update with a quote.
- **Templates** (not committed; passed by path):
  - `corporate`: the template of a local "PPT Corporate" agent, a French
    corporate deck. 20 layouts, 20 example slides.
  - `prism`: the "PPT Prism" agent's template (4.3 MB): 3 layouts without
    placeholders, 10 example slides, 7 reusable.
  - `builtin`: the interim built-in theme (`theme.py`, deleted in WP7), rules only;
    the shipped Fred deck since WP7.
  - `paintress` (WP13): the developer's "Paintress" agent template, read from its
    analysis row; the corporate deck plus a data-table slide.

Two full matrices per state (100 runs each): **before** = WP9 runs 1 and 2,
**after** = WP11 runs 6 and 7 (same templates, prompts, models and harness; the
harness gained a first-call column). One LLM at temperature 0 still varies
between runs: read single-cell differences as noise.

## Results: before (WP9) / after (WP11)

| template | mode | success | first call | avg repairs | cover once@1 | 3-in-a-row | distinct/slides | leftovers | truncated + lost |
|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 20 → 18 | 5 → 7 | 1.5 → 1.2 | 100% → 100% | 4 → 1 | 0.70 → 0.70 | 4* → 0 | 0 → 0 |
| corporate | rules | 19 → 20 | 0 → 8 | 1.6 → 0.8 | 100% → 100% | 1 → 2 | 0.72 → 0.67 | 2* → 0 | 0 → 0 |
| corporate | vision | 17 → 19 | 1 → 7 | 1.6 → 0.7 | 100% → 100% | 0 → 3 | 0.76 → 0.69 | 1* → 0 | 0 → 0 |
| prism | rules | 20 → 19 | 0 → 12 | 1.8 → 0.8 | n/a (no cover) | 3 → 12 | 0.35 → 0.38 | 0 → 0 | 0 → 0 |
| prism | vision | 16 → 20 | 3 → 11 | 1.6 → 0.6 | 100% → 100% | 76 → 18 | 0.31 → 0.45 | 0 → 0 | 0 → 0 |
| **total** | | **92 → 96** | **9 → 45** | 1.6 → 0.8 | 100% | 84 → 36 | | 0 | 0 |

**WP12** (example slides that copy a layout stand for it; rows of same-size shapes are
repeat groups; one matrix run, `make eval` with the same 10 prompts):

| template | mode | success | first call | avg repairs | cover once@1 | 3-in-a-row | distinct/slides | leftovers / truncated / lost |
|---|---|---|---|---|---|---|---|---|
| builtin | rules | 10 → 9 | 4 → 2 | 0.6 → 1.4 | n/a (no cover) → 100% | 5 → 1 | 0.53 → 0.62 | 0 / 1→0 / 0 |
| corporate | rules | 20/20 → 10/10 | 8/20 → 4/10 | 0.8 → 0.8 | 100% | 2/20 → 2 | 0.67 → 0.66 | 0 |
| corporate | vision | 19/20 → 10/10 | 7/20 → 4/10 | 0.7 → 0.8 | 100% | 3/20 → 0 | 0.69 → 0.63 | 0 |
| prism | rules | 19/20 → 10/10 | 12/20 → 6/10 | 0.8 → 0.5 | n/a → 100% (slide 1 is now the cover) | 12/20 → 3 | 0.38 → 0.44 | 0 |
| prism | vision | 20/20 → 9/10 | 11/20 → 3/10 | 0.6 → 1.2 | 100% | 18/20 → 8 | 0.45 → 0.51 | 0 |

Before = WP7 (builtin, one run) and WP11 runs 6+7 (corporate, prism). No success
regression on corporate; prism vision first call lower, 4 of its 7 first-call problems
being the known one-heading prism cover given a subtitle. Built-in deck after WP12: a
cover (slide 1), `figures` 3 items, `process` 4 items, `cards` 3 items (Title Only
slide), `quote`, `image_text`; its remaining repairs are agenda items (the agenda slide
is a plain list: "holds 4") and figure values over ≈7 chars. Corporate: the two
"Images + 3 colonnes" designs are now `cards` [image, text]; prism slide 781 is a
6-card grid. A render fix (recentred placeholders lost their inherited `y`) landed
after this run; it changes geometry only, not these metrics.

\* Run 1 counted the step numbers the renderer writes ("1", "2"…) as leftovers; the metric now excludes them.

Intermediate WP11 runs (kept in the report, not here): with only capacities,
coherence and soft fallback, first-call success was 7/50; most first calls
then failed on a subtitle on a content slide (21/82 problems) and on the prism
cover described as `columns.heading`. The D6 placement rule (subtitle leads the
body, step numbers need no zone) and naming a lone heading as `title` in the
catalogue brought it to 45/100.

Analysis: corporate vision labelling 44-47 s for 20 slides (20/20 labelled); prism
71-74 s (7/8 labelled). Rules only: about 1 s. Calibration raises the measured
line width of 30/178 prism zones (designer samples that our substitute font
says overflow) and 0/96 corporate zones.

## Results: WP13 (deck-wide variety)

Before = the WP12 code (snapshot of `ff8dc9a49`'s package run with the WP13 harness),
after = `915b27d82`; same 10 prompts, `chat.mistral.small`, one matrix each, run on
2026-10-06. Builtin and Paintress-vision "after" come from a second, single-process run:
the first after-run shared the Mistral quota with the corporate baseline and lost 3
builtin runs and 10 Paintress vision labels to 429s (those cells are not used). New
columns: **max reuse** (most uses of one template slide in a deck), **A-B-A** (a slide
coming back two positions later), **avoidable reuses** (a reuse while an unused slide of
the same kind would have held the content), **patterns used** (distinct template slides
used across the 10 decks / assignable ones; layouts covered by a slide left the
inventory, so the denominator drops).

| template | mode | success | first call | avg repairs | 3-in-a-row | distinct/slides | max reuse | A-B-A | avoidable reuses | patterns used |
|---|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 10 → 10 | 3 → 5 | 1.2 → 0.6 | 2 → 1 | 0.65 → 0.80 | 5 → 4 | 12 → 3 | 12 → 0 | 10/15 → 12/15 |
| corporate | rules | 9* → 10 | 0 → 3 | 1.1 → 0.8 | 0 → 2 | 0.75 → 0.91 | 5 → 4 | 9 → 0 | 17 → 0 | 11/38 → 17/31 |
| corporate | vision | 10 → 10 | 4 → 3 | 0.8 → 0.9 | 3 → 1 | 0.65 → 0.87 | 6 → 3 | 23 → 0 | 28 → 0 | 12/40 → 16/33 |
| paintress | rules | 9* → 9* | 2 → 3 | 0.9 → 0.9 | 1 → 1 | 0.72 → 0.88 | 4 → 5 | 12 → 2 | 17 → 0 | 12/38 → 16/31 |
| paintress | vision | 9** → 9 | 3 → 4 | 0.5 → 1.0 | 0 → 1 | 0.78 → 0.91 | 4 → 3 | 9 → 1 | 10 → 0 | 10/40 → 16/33 |

\* The failure is the known harness artifact (an invented image id, no `document_content`
port). \*\* 7/10 in the main run plus the 2 runs lost to a network `ReadError`, re-run
alone (both delivered); the row's other metrics are over the main run's 7 decks. Leftovers, truncated and lost stay 0 everywhere; cover once at 1
100 %.

- **A B A B is gone**: 65 A-B-A returns → 6, avoidable reuses 84 → 0. The remaining
  reuses are the ones the content forces (one `two_columns` slide in the deck, the
  agenda) and are named in the success message ("Slides 4, 8, 12 all use…").
- **Success unchanged** (47/50 → 48/50 on the cells above). The one new failure,
  `paintress/vision/options_comparison`, ran out of repairs sending three columns to a
  two-column template four times; the same prompt passed in the first after-run.
- **Icon cards (`slide:272`/`slide:273`) still do not appear in the eval decks.** They
  are listed now ("3 icônes + texte", "6 icônes + texte" in the `cards` line) and chosen
  for short items (reference-template test), but their text zones are measured at
  ≈12 chars × 2 lines (20 pt) and ≈18 chars: every items slide the model wrote carries
  longer text ("Sophia" + "450 employees\nSpace" already overflows). The photo cards
  (`slide:266`, 27 × 3) and the six-box slide (`slide:269`, 31 × 4) took those slides
  (266: 3 → 9 decks, 269: 0 → 7 decks over the cells above). Getting the icon cards used needs
  either shorter content or text allowed to grow into the empty card below the box;
  not done here.
- The `cards` line of the catalogue shows 5 variants on Paintress, not the 6 the task
  expected: layouts 10/11 left with their slides, so the cards designs are
  `slide:266/267/269/272/273`.
- Layouts 2, 7, 9, 10, 11, 12 of Paintress (and the same ones of corporate) left the
  inventory: a slide of the deck holds their slots. Layouts 4, 5, 18, 19 stay as
  fallback (Q7). `slide:269` keeps layout 5 because its drawn boxes make it `cards`,
  not `image_text`.
- Assign time on a 30-slide deck against Paintress: 106 ms after, 110 ms before (median
  of 5, `asyncio.to_thread`); the beam search is 3 ms of it, the fit check the rest. The
  tool description grows from 3 555 to 4 349 chars on Paintress (≈+200 input tokens per
  model call).

## Results: WP15 (table slides)

One matrix on 2026-10-06, after `7f9dd85ad`, same harness and model as WP13, 12 prompts:
the WP13 ten plus `offers_table` (three cloud offers × five criteria) and
`schedule_table` (eight training sessions × date, theme, trainer, room). One process,
nothing else running; no 429. Like-for-like against WP13 (its ten prompts only):

| template | mode | success | first call | avg repairs | 3-in-a-row | distinct/slides | max reuse | A-B-A | avoidable reuses |
|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 10 → 9* | 5 → 4 | 0.6 → 0.8 | 1 → 0 | 0.80 → 0.82 | 4 → 2 | 3 → 2 | 0 → 0 |
| corporate | rules | 10 → 9* | 3 → 4 | 0.8 → 1.1 | 2 → 0 | 0.91 → 0.91 | 4 → 4 | 0 → 0 | 0 → 0 |
| corporate | vision | 10 → 10 | 3 → 5 | 0.9 → 0.8 | 1 → 3 | 0.87 → 0.86 | 3 → 4 | 0 → 0 | 0 → 0 |
| paintress | rules | 9* → 10 | 3 → 4 | 0.9 → 0.7 | 1 → 1 | 0.88 → 0.88 | 5 → 3 | 2 → 1 | 0 → 0 |
| paintress | vision | 9 → 10 | 4 → 6 | 1.0 → 0.5 | 1 → 1 | 0.91 → 0.90 | 3 → 3 | 1 → 0 | 0 → 0 |

\* `training_12`: the known harness artifact (an invented image id, no
`document_content` port). Leftovers, truncated and lost stay 0 everywhere; cover once at
1 100 %. No regression beyond run-to-run noise.

The two tabular prompts (all 10 runs delivered):

| template | mode | tables used / given | shape kept | off the slide | first call | 3-in-a-row |
|---|---|---|---|---|---|---|
| paintress | rules | 2/2 (+1 in `esg_report`: 3/3) | 3 | 0 | 2/2 | 0 |
| paintress | vision | 2/2 (+3 in `cyber_2027`, `options_comparison`, `quarterly_review`: 5/5) | 5 | 0 | 1/2 | 0 |
| builtin, corporate | both | 0/0 (no table slide: no `table` field in the schema) | - | - | 3/6 | 7 |

- **Paintress**: every table the model sent went to `slide:300`, rendered with the plan's
  rows and columns (header row, Medium Style 2 banding, columns widened when fewer than
  5, rows removed below the content, a two-line cell growing its row), nothing past the
  slide. Contact sheets: `~/fred-tmp/wp15-eval/sheets/paintress-*-*_table.png`.
- **Templates without a table slide** recast the table: `corporate/rules/schedule_table`
  made one `two_columns` slide per session (8 in a row: 6 of the 7 corporate-rules
  triples, max reuse 8), reported to the agent as repetitions. Not a WP13 regression (new
  prompt); a table-less template has no better slide for eight rows.
- Synthetic render (`~/fred-tmp/wp15/try.pptx`, `try.pdf`, `try-2.png`, `try-3.png`): a
  5 × 4 comparison and a 13-row × 3 schedule on Paintress. LibreOffice converts it without
  complaint; the 13-row table is set at 85 % in one size and ends above the footer; row ids
  unique, `gridCol` count = cells per row, frame height = the rows' sum. PowerPoint itself
  was not available: "opens without repair" is shown by those invariants, not by
  PowerPoint.
- Rules analysis of Paintress: `slide:300` is `table` (5 columns ≈18 chars per cell line,
  header + 11 lines of rows); the Gantt grid `slide:278` stays excluded (`table`: its
  body cells carry different fills). Corporate unchanged (no data table).
- Behaviour beyond D14, decided in implementation: a plan table without `header` on a
  template table with a header row takes its first row as the header; the `table` field
  is in the tool schema only when the template offers a `table` kind; vision cannot turn
  a table-zone slide into another kind (nor give `table` to a slide without one); shrink
  goes by 5 % steps down to the 0.7 floor, a row never shorter than the template's own row
  at that scale.

## Targets (WP11)

| Target | Result |
|---|---|
| First-call success clearly up from 10/100 | **Met**: 9 → 45/100 (every cell up) |
| Overall success ≥ 95/100 | **Met**: 96/100 (one failure is the harness artifact below) |
| Vision ≥ rules on success | **Met**: 39/40 vision vs 39/40 rules on the same templates |
| Cover exactly once at 1 | **Met**: 100% of successful decks on templates with a cover |
| 0 leftovers, 0 overflow/lost | **Met**: 0 / 0 / 0 |
| Zero 3-in-a-row (WP9 target) | Not met on prism (30) and still a few on corporate: prism has one usable bullets slide; soft fallback and the subtitle rule now let more slides land there instead of failing. Each repetition is reported to the agent |

## Fixes applied during WP9

1. **Large templates got no thumbnails and no vision labels.** The background job
   converted the patterns deck with the 60 s turn default; the prism patterns deck
   takes 64 s here. The PDF was dropped, so no thumbnails, and labelling silently
   fell back to rules. Fix: `PATTERNS_PDF_TIMEOUT_SECONDS = 300` in
   `analysis_job._analyse` (nobody waits on the job). Before: prism vision 0/8
   labelled, analysis aborted. After: 7/8 labelled in 72 s.
2. **The model asked for kinds the template does not offer.** The `kind` field's
   JSON schema kept the full `SlideKind` enum in its nested `anyOf` next to the
   template's list, so models picked absent kinds. Fix: `_kind_enum` replaces the
   nested enum with the offered kinds only (test updated). Before: 49 "this
   template has no 'X' slide" problems over 50 runs. After: 19. Runs passing on
   the first call went from 3 to 7.
3. **Per-turn CPU on the event loop** (performance review): `apply_overrides`
   deep-copied the whole inventory on every turn, and the tool's pydantic schema
   was rebuilt on every turn. Now only overridden patterns are copied, and the
   schema is cached per kind set. Middleware build on the corporate inventory went
   from 9.6 ms to 2.7 ms per turn (1.5 ms on the built-in theme).

## Remaining failures and diagnosis (after WP11)

- **4 failures of 100**: `builtin/many_items` (twice) and `builtin/cyber_2027`
  run out of repairs on short item zones: the built-in agenda heading holds ≈26
  chars, figures ≈5-char numbers and ≈19-char labels, and the model shortens one
  entry per call. `prism/rules/kickoff`: the leftmost heading of the prism
  "cards" slide is taken as its title and holds ≈13 chars. The problems now name
  each element and the "resent unchanged / changed but still there" flag shows
  on the last calls; the model still converges too slowly with three repairs.
- One harness artifact per matrix: the model invents an image id and the
  harness provides no `document_content` port.
- **Vision coherence** keeps two prism kinds (`figures`, `cards` on slides with
  no repeated group) as `bullets`, with a warning in the review panel. The
  prism cover still holds only one heading: the catalogue now calls it `title`.
- **Prism previews time out**: every rendered prism deck exceeds the 60 s
  LibreOffice limit, so in a pod it would be delivered as a download only. Most
  of the 55-60 s wall time per prism run is that timeout. Not changed: the
  limit protects a live turn.
- Visible in the contact sheets (corporate): the timeline slide's decorative line
  crosses the date labels. Not measured by any metric.

## What is NOT proven

- The UI: upload, analysis status, review panel, preview pane, download (task 9.4,
  manual).
- A real fred-agents process: middleware wiring, the routed `CapabilityModelPort`
  (usable models, team routing, vision refusal), readiness and suspension in the
  control plane, ReBAC on the analysis routes. The harness calls the same tool and
  pipeline code, not the pod.
- Several replicas, lease recovery, re-runs, and concurrency under load.
- Other models: only Mistral Small was evaluated, as agent and as vision model.
- Statistical confidence: one run per cell, 10 prompts.

## Checks

- WP15: package `make code-quality` passed; `make test` 369 passed, 4 skipped (12 new in
  `test_table_slides.py`); with `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 373
  passed; on the Paintress deck the reference-bearing files (analysis, render, assign)
  141 passed. `make builtin-inventory` regenerated (`ANALYSIS_VERSION` 10; only the version
  and the new `table: null` zone field changed). ppt_builder slice regenerated (`table`
  kind and role, `TableSpec`), `table` added to `SLIDE_KINDS` with fr/en labels;
  `npx tsc --noEmit` clean, vitest on `ppt_builder/` + `src/locales` 33 passed.
  `fred-performance-reviewer` on the tool path: no I/O added; assign and render stay in
  `asyncio.to_thread`; schema still cached per kind set; description 0.14 ms per turn. One
  finding fixed (`7f9dd85ad`): cell widths were re-measured at every font scale; a
  30-slide deck with ten overflowing 30 × 5 tables went from 326 ms to 130 ms of assign
  CPU (122 ms without tables, WP13: 106-110 ms).
- WP13: package `make code-quality` passed; `make test` 357 passed, 4 skipped; with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 361 passed (the Paintress deck
  passes the reference tests too). `fred-performance-reviewer` on the assigner: no
  finding (assign stays in `to_thread`, no new I/O or shared state; description build
  0.12 ms per turn). `Pattern.preferred` left the API model: the ppt_builder frontend
  slice was **not** regenerated (WP14 owns `apps/frontend`; the field is read nowhere).
- WP14 (review dialog, frontend only, no schema change): sections split on the
  existing `Pattern.source` / `Pattern.included`. `npx tsc --noEmit` clean;
  `npx prettier --check` and `npx eslint` clean on the touched files; `npx vitest run`
  on `ppt_builder/` and `src/locales`: 4 files, 33 passed (PatternReviewDialog 6, of
  which 2 new: section order slides → layouts (folded, with hint) → excluded, and an
  excluded layout landing in "excluded" with empty sections dropped). Not proven: the
  browser layout (14.4, developer check on the Paintress agent).

- WP12: package `make code-quality` passed (the deck hash in the stored inventory is
  now in the detect-secrets baseline); `make test` 349 passed, 3 skipped; with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 352 passed. No schema change.

- WP7: package `make code-quality` passed; `make test` 338 passed, 3 skipped; the
  wheel carries `builder/assets/*`. ppt_builder slice regenerated (`/builtin`,
  `/builtin/patterns.pdf`), `tsc --noEmit`, prettier and the slice's vitest (21) clean.
- WP11: `make code-quality` in the package passed (ruff, format, bandit,
  detect-secrets, basedpyright 0 errors); `make test` 335 passed, 3 skipped.
  ppt_builder frontend slice regenerated (`Zone.max_chars` → `chars_per_line`),
  `tsc --noEmit` clean.


- WP9: `make code-quality` in the package: passed (ruff, format, bandit,
  detect-secrets, basedpyright 0 errors; `eval/` added to the type-checked paths).
- `make test` in the package: 326 passed, 3 skipped (the reference-template tests,
  which pass with `PPT_BUILDER_REFERENCE_TEMPLATE` pointing at the corporate deck:
  3 passed).
- fred-sdk, fred-runtime and frontend suites were not re-run in WP9 (they were
  last run in WP1/WP10/WP8, and WP9 does not touch them).
- `fred-performance-reviewer` on the tool path and the background job: findings
  are listed in the WP9 report; fix 3 above is the one applied.
