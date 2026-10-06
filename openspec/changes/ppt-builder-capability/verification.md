# Verification: ppt-builder-capability

Evidence for WP9, WP11, WP12, WP13, WP15, WP16, WP17 and WP18 (design D11). Run on 2026-10-05 on a developer laptop. This is
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

## Results: WP16 (no dropped text, first-deck variety revision, choice guide)

Run on 2026-10-06 after `3a3e7d314`/`b44524487`, same harness and model as WP15, 13 prompts:
the WP15 twelve plus `country_comparison` (Spain and Italy: figures, domains, dated
initiatives, challenges, then a comparison). Two `make eval`-equivalent processes run one
after the other (Paintress, then corporate; each also runs the built-in template), nothing
else running, no 429. Like-for-like against WP15 (its twelve prompts only); the built-in
cell gives the Paintress process's run / the corporate process's run:

| template | mode | success | first call | avg repairs | 3-in-a-row | distinct/slides | max reuse | lost | variety asks |
|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 11 → 11 / 11 | 6 → 2 / 2 | 0.67 → 1.58 / 1.17 | 0 → 0 / 0 | 0.85 → 0.86 / 0.86 | 2 → 3 / 2 | 0 → 1* / 0 | 2 / 1 |
| corporate | rules | 11 → 11 | 4 → 3 | 1.25 → 1.25 | 7 → 0 | 0.85 → 0.90 | 8 → 2 | 0 → 0 | 1 |
| corporate | vision | 12 → 12 | 6 → 4 | 0.83 → 1.08 | 3 → 1 | 0.89 → 0.90 | 4 → 3 | 0 → 0 | 2 |
| paintress | rules | 12 → 11 | 6 → 3 | 0.58 → 1.00 | 1 → 0 | 0.90 → 0.93 | 3 → 3 | 0 → 0 | 2 |
| paintress | vision | 12 → 12 | 7 → 5 | 0.58 → 0.92 | 1 → 0 | 0.91 → 0.96 | 3 → 2 | 0 → 0 | 0 |

\* `lost` now counts raw-argument text missing from its slide (WP15 counted the
renderer's report, which could not see a dropped key). The one hit is a bullet the
renderer cut at a word boundary (`truncated` 1 on the same deck). The failures are the
known harness artifact (an invented image id, no `document_content` port) and two
`cyber_2027` runs out of repairs on figure/label sizes. Cover once at 1: 100 %;
leftovers 0; tables 9/9 used and shape kept on Paintress.

- **Variety**: 3-in-a-row 12 → 1 and the worst reuse 8 → 3 over these cells; distinct
  per slide up everywhere. 9 variety asks over 78 runs (never two in one run), each answered by a recast deck or
  a resend, never a loop (the next call was always built). An ask names the slides and
  alternatives with what each suits, e.g. `paintress/rules/cyber_2027`: four
  "6 zones de texte" cards slides → the recast deck used timeline, figures and cards
  once each (max reuse 2).
- **First call is lower** (29 → 17 of 60). Not the asks themselves (only 1 of the
  final runs' first-call failures was a variety ask): repairs are mostly long cover
  subtitles and items sent to figures/process slides that do not hold their fields. It is
  noisy: three runs of the same Paintress rules cell gave 2, 5 and 3. Same-day built-in
  A/B (12 prompts): pre-WP16 code 5/12, WP16 with the first guide 1-2/12, without the
  guide (old sentence) 3/12, with the final guide 2/12; the first guide wording sent text
  to figures slides (figures problems per run 0.30 → 0.50), hence `3a3e7d314` (figures
  hold a value and a short label, within each variant's fields). Success stays at WP15's
  level (58/60 → 57/60).
- **No dropped text**: no run sent `heading2` again; the new problems caught real model
  keys that the old coercion dropped silently: `""` (empty key holding a section title,
  `builtin/country_comparison`), `"title: "`, `"{"` inside an item, `"figures"` on a slide
  (`corporate/rules/pitch_4`). A first-run "incomplete entries" on a figures slide
  (number + text beside number + label) led to `b44524487` and `fd860d377`: a number
  leads an item, a number with its label is a whole entry (the last fix is after the final
  runs; it only removes that false problem).
- **`country_comparison`**: 5/6 delivered (the failure is the harness artifact), max
  reuse 2 in every deck, no columns slide restating a table.
- First-deck detection: `workspace_fs.ls("outputs/{session_id}")`, listed only when a
  revision would follow; a 404 (folder never written) is "no deck yet", any other error
  "delivered" (`02151b36a`, found by the performance review).
- Tool description (chars): builtin 3 385 → 3 404, Paintress 4 499 → 4 629, corporate
  4 349 → 4 406 (≈ +5 to +35 tokens per model call).

## Results: WP17 (variety by kind, content-based alternatives)

Run on 2026-10-06 after `a44965990`, same harness and model (`chat.mistral.small`) as
WP16, 14 prompts: the WP16 thirteen plus `thales_spain_italy` (the real session's request,
no comparison asked). Two `make eval` processes one after the other (Paintress, then
corporate; each also runs the built-in template), nothing else running, no 429. New
columns: **max kind repeat** (most slides of one non-structural kind in a deck: max, and
mean over delivered decks; recomputed for WP16 from its saved runs) and **tool calls** (all
build calls of the cell). Like-for-like against WP16 (its thirteen prompts); the built-in
cell gives the Paintress process's run / the corporate process's run:

| template | mode | success | first call | avg repairs | max kind repeat (mean) | decks with a kind ×3+ | distinct/slides | max reuse | variety asks | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 12 / 12 → 9 / 9 | 2 / 2 → 1 / 0 | 1.62 / 1.23 → 1.92 / 2.08 | 7 / 6 (3.42 / 3.08) → 4 / 4 (2.56 / 2.33) | 8 / 7 → 3 / 3 | 0.85 / 0.84 → 0.89 / 0.86 | 3 / 3 → 2 / 4 | 2 / 2 → 9 / 9 | 34 / 30 → 40 / 41 |
| corporate | rules | 11 → 12 | 3 → 1 | 1.15 → 1.85 | 10 (3.82) → 9 (3.17) | 7 → 7 | 0.90 → 0.87 | 2 → 3 | 1 → 9 | 27 → 37 |
| corporate | vision | 13 → 9 | 5 → 1 | 1.00 → 2.00 | 10 (3.92) → 3 (1.78) | 9 → 2 | 0.90 → 0.87 | 3 → 3 | 2 → 10 | 26 → 43 |
| paintress | rules | 12 → 12 | 3 → 3 | 1.00 → 1.46 | 11 (3.25) → 7 (2.75) | 5 → 6 | 0.92 → 0.91 | 3 → 4 | 2 → 9 | 26 → 34 |
| paintress | vision | 13 → 12 | 6 → 1 | 0.85 → 1.85 | 9 (3.69) → 4 (2.00) | 7 → 3 | 0.95 → 0.91 | 2 → 4 | 0 → 9 | 24 → 37 |

Cover once at 1: 100 %; leftovers and truncated 0; tables 14/14 used and shape kept on
Paintress. `lost` is 0 except 9 on `corporate/vision/many_items`: the model split the deck
into three parallel calls (three files) and the metric read the first one (harness
artifact, not WP17). Four of the like-for-like failures are the known harness artifact (an
invented image id, no `document_content` port).

- **Kind repetition is down**: the mean worst kind per deck goes from 3.1-3.9 to 1.8-3.2,
  and the delivered decks with one kind on 3+ slides from 43 to 24; distinct/slides stays
  where WP16 left it. A deck with 7 bullets slides is still delivered when the model resends
  as is (`paintress/rules/training_12`).
- **Success is down: 73/78 → 63/78.** The ask now fires on most first decks (59 asks over 84
  runs, against 9 over 78 in WP16), and each ask costs one of the harness's three repair
  rounds. 13 of the 15 failures had an ask; in most, the recast deck brought new fit
  problems the model did not fix in the rounds left (items sent to figures/process slides
  without a label or number zone, four columns on a two-column slide). First-call success
  drops (21 → 7 of 78) for the same reason: an asked deck is never a first-call success.
  Tool calls +39 % (167 → 232). A live turn has no three-repair cap, so the harness
  overstates the lost decks, but every ask is one more full model call.
- **Advice from the content**: 12 of the 29 Paintress-process asks carry a `suggested` line
  (the run logs keep 2 000 chars of each answer, so this is a lower bound), e.g.
  `paintress/vision/country_comparison`: `slides 7, 11 → timeline (dated items)`. On the
  evidence plan the unit tests give exactly slide 5 → cards, 7 → timeline, 9 → two_columns
  or cards, 10 → cards.
- `thales_spain_italy` (not in the table): Paintress rules `[cover, figures, figures, cards,
  cards, bullets ×4, closing]` and vision `[cover, bullets, bullets, image_text, image_text,
  two_columns, process, process, bullets]`, each after one ask; corporate vision delivered
  with 2 bullets slides, corporate rules hit the harness artifact.
- Tool description (chars): builtin 3 404 → 3 439, Paintress 4 629 → 4 664, corporate
  4 406 → 4 441 (the bullets cap, ≈ +9 tokens per model call). The harness now also records
  model tokens per run.

**Agent model on Paintress rules: `chat.mistral.small` vs `chat.mistral.medium`** (reasoning
off, as the eval loads every profile; 14 prompts each, one process after the other):

| model | success | built when it called the tool | first call | variety asks | tool calls | tokens in / out per delivered deck | wall s per delivered deck | max kind repeat (mean) |
|---|---|---|---|---|---|---|---|---|
| small | 11/14 | 11/14 | 3 | 8 | 37 | 9.2k / 2.3k | 23.8 | 4 (2.09) |
| medium | 12/14 | 12/12 | 1 | 6 | 31 | 9.0k / 2.2k | 24.6 | 3 (1.83) |

Medium never ran out of repairs; its two failures (and four of 14 on the built-in template)
are `no_tool_call`: it wrote a slide plan and asked the user to confirm before building,
which a one-turn harness counts as a failure. Same tokens and wall time per delivered deck
as small: the cost difference is the per-token price only (not measured here).

## Results: WP18 (variety asked on the first call only, with fit hints)

Run on 2026-10-06 after `c6043beaa`, same harness, model (`chat.mistral.small`) and 14 prompts
as WP17. Two `make eval` processes one after the other (Paintress, then corporate; each also
runs the built-in template), nothing else running, no 429. Like-for-like on the WP16
thirteen prompts (78 runs per state; WP16 = `eval-wp16c-*`, WP17 = `eval-wp17-*`, WP18 =
`eval-wp18-*`); the built-in cell gives the Paintress process's run / the corporate
process's run:

| template | mode | success | first call | tool calls | variety asks | decks with a kind ×3+ | max kind repeat (mean) | lost |
|---|---|---|---|---|---|---|---|---|
| builtin | rules | 12/12 → 9/9 → 10/11 | 2/2 → 1/0 → 1/1 | 34/30 → 40/41 → 35/38 | 2/2 → 9/9 → 8/7 | 8/7 → 3/3 → 4/6 | 7/6 (3.42/3.08) → 4/4 (2.56/2.33) → 4/7 (2.40/3.09) | 1/0 → 0/0 → 0/0 |
| corporate | rules | 11 → 12 → 13 | 3 → 1 → 0 | 27 → 37 → 33 | 1 → 9 → 8 | 7 → 7 → 8 | 10 (3.82) → 9 (3.17) → 7 (3.31) | 0 → 0 → 0 |
| corporate | vision | 13 → 9 → 12 | 5 → 1 → 1 | 26 → 43 → 35 | 2 → 10 → 9 | 9 → 2 → 7 | 10 (3.92) → 3 (1.78) → 8 (2.83) | 0 → 9* → 0 |
| paintress | rules | 12 → 12 → 11 | 3 → 3 → 1 | 26 → 34 → 32 | 2 → 9 → 7 | 5 → 6 → 1 | 11 (3.25) → 7 (2.75) → 3 (1.91) | 0 → 0 → 0 |
| paintress | vision | 13 → 12 → 12 | 6 → 1 → 2 | 24 → 37 → 30 | 0 → 9 → 10 | 7 → 3 → 5 | 9 (3.69) → 4 (2.00) → 10 (3.17) | 0 → 0 → 0 |
| **total** | | **73 → 63 → 69** | **21 → 7 → 6** | **167 → 232 → 203** | **9 → 55 → 49** | **43 → 24 → 31** | **11 → 9 → 10** | 1 → 9* → 0 |

\* the three-parallel-calls harness artifact of WP17 (see there). Cover once at 1: 100 %;
leftovers 0.

- **Success recovers most of the loss: 63 → 69 of 78** (WP16: 73). Without the harness
  artifact (an invented image id, no `document_content` port: 3 / 4 / 4 runs), the other
  failures go 2 → 11 → 5, and only 2 of WP18's 5 had an ask (WP17: 9 of 11). The 5 are
  `repairs_exhausted` on the built-in template (`esg_report` ×2, `training_12`,
  `offers_table`) and `paintress/vision/esg_report`, all ending on fit problems (cover
  subtitle, figure labels, row lengths).
- **The ask no longer costs a round of its own**: 29 of the 48 recorded asks came merged with
  the first call's fit problems (WP17: every ask was a separate round, after the repair). No
  ask followed a fit repair. Tool calls drop 232 → 203 (−12.5 %), still +22 % over WP16.
- **First call does not recover (7 → 6)**, as expected: the ask still fires on most first
  decks (49 asks), and an asked deck is never a first-call success. Most first-call misses
  are fit problems that would be there without the ask (cover subtitle ≈32 chars and figure
  labels ≈12 chars on Paintress).
- **Variety: part of WP17's gain is kept.** Decks with one kind on 3+ slides 43 → 24 → 31;
  the gain holds on Paintress rules (1 deck, worst 3) and the built-in Paintress run, and
  shrinks on corporate and Paintress vision, where a merged ask is answered by fixing the
  fit problem and keeping the kinds (the resend rule) more often. Worst kind repeat 11 → 9
  → 10 (`paintress/vision/training_12`: 10 bullets slides, the model kept them).
- **Fit hints**: 37 of the 48 recorded asks carry a `holds` line (run logs keep 2 000 chars of
  each answer, so this is a lower bound). A first Paintress run (`eval-wp18a`, before
  `c6043beaa`) showed a cards suggestion quoting `items max 4 [number, label ≈12 chars]` for
  `Label : text` points: an unmeasured `number` field counted as endless room. Fixed (room sums
  measured fields; holding the longest entry outranks an empty item picture) and both
  processes re-run; the table is the re-run.
- Example of the ask as the model sees it (`paintress/rules/quarterly_review`, first call,
  delivered on the second; option list shortened here):

  ```
  No deck was built: some slides fit no slide of this template. Fix each slide listed under `slides` with one of its options. Also, several other slides would look the same: recast some of the slides under `variety` into one of their options (`suggested` names the kind each slide's content already suits and what that slide holds), rewriting the content in that shape and to those sizes. Then call build_presentation again with the WHOLE deck. If the slides under `variety` must stay alike, keep them: the next deck that fits is built as is.
  {"status": "needs_revision", "slides": [{"slide": 4, "kind": "figures", "problem": "closest fit, a 'figures' slide: items: 5 given, max 4", "options": ["trim to 4 items or split them over two slides", "a 'figures' slide takes: title ≈71 chars; items max 4 [number, label ≈12 chars]"]}], "variety": [{"slides": [3, 5, 7, 8], "kind": "bullets", "suggested": ["slide 7 (parallel 'Label : text' points) → cards holds items max 6 [heading+text ≈31 chars × 4 lines]"], "options": ["'figures' for a few key numbers, each a value + a short label: Indicateurs de performance / chiffres clés: title ≈71 chars; items max 4 [number, label ≈12 chars]", "'timeline' for dated items or milestones: …", "…"]}]}
  ```

  The delivered deck: `[cover, agenda, cards, figures, cards, process, bullets, bullets]`.
- Model tokens (now recorded): 796k in / 237k out over the 78 runs (no earlier baseline).

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

- WP18: package `make code-quality` passed; `make test` 389 passed, 4 skipped (2 new in
  `test_assign.py` for the hints and their ranking, 1 for repeats beside problems, 2 in
  `test_build_tool.py`: no ask after a fit repair, ask merged with problems); with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 393 passed; on the Paintress deck the
  reference-bearing files 152 passed. No
  API model change (no frontend regeneration). `fred-performance-reviewer` on the tool path: no
  new I/O except the existing outputs listing, now also on a first call that has fit problems
  and a repeat (once per turn at most); `assign` still in `asyncio.to_thread`; on a plan with
  problems it now also runs the beam over the fitting slides: 29-slide deck against Paintress
  233 ms (no problem) / 272 ms (one unfit slide, 30 slides), measured median of 7; the hints
  read stored capacities only. The tool-instance `called` flag is per turn, as the WP16 flag
  was; no shared state. No finding.
- WP17: package `make code-quality` passed; `make test` 384 passed, 4 skipped (4 new in
  `test_assign.py`, 2 in `test_build_tool.py`); with `PPT_BUILDER_REFERENCE_TEMPLATE` on the
  corporate deck 388 passed; on the Paintress deck the reference-bearing files 149 passed. No
  API model change (no frontend regeneration). `fred-performance-reviewer` on the tool path:
  no new I/O; repeats and content shapes run inside `assign` (in `asyncio.to_thread`): assign
  on a 29-slide deck against Paintress 233.8 → 233.5 ms (median of 7), `content_shape` over
  29 slides 0.14 ms; description build 0.14 ms per turn, unchanged. The cost that matters is
  on the LLM path: each ask is one more model call (tool calls +39 % in the eval above).
- Closing slide "Merci" shown as "Merc" / "i" in the preview (`slide:287`, task 17.8): not
  ours. The output slide is empty; the text lives in its layout ("Merci", layout 18), byte
  for byte as in the template. LibreOffice converting the template alone shows the same
  break on page 39. The text box is `wrap="none"` + `spAutoFit`, 2 107 949 EMU (166.0 pt)
  wide, "Merci" 60 pt bold in the theme font Century Gothic, which this host lacks
  (`fc-match` → Noto Sans): "Merci" in Noto Sans Bold 60 pt measures 167.2 pt, over the box,
  and LibreOffice breaks it despite `wrap="none"`. PowerPoint never wraps a `wrap="none"`
  box and sized it to the text in Century Gothic: one line there. No code change.
- WP16: package `make code-quality` passed; `make test` 378 passed, 4 skipped; with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 382 passed; on the Paintress deck
  the reference-bearing files 145 passed. No API model change (the dumped ppt_builder
  OpenAPI equals the committed slice; no regeneration). `fred-performance-reviewer` on the
  tool path: coercion +0.2 ms per 30-slide plan on the event loop (0.35 → 0.55 ms), assign
  150 → 154 ms median in `asyncio.to_thread` (within noise), description 0.14 ms per turn
  unchanged; the outputs listing is one async KF call through the shared workspace client,
  only on the revision path; the once-per-turn flag is tool-instance state, and "delivered"
  is read from the shared workspace, so replicas agree. One finding fixed (404 = no deck).
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
