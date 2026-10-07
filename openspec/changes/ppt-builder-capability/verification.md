# Verification: ppt-builder-capability

Evidence for WP9, WP11, WP12, WP13, WP15, WP16, WP17, WP18, WP19, WP20, WP21, WP22, WP29 and WP31 (design D11). Run on 2026-10-05 on a developer laptop. This is
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
  "delivered" (`02151b36a`, found by the performance review). Replaced by the history check in WP23.
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

## Results: WP19 (variety check setting, capped suggestions)

Run on 2026-10-06/07 after `3b033bdc5` (the later frontend-only commits do not touch the tool
path), `make eval` with `--variety`, seven processes strictly one after the other, nothing else
running, no 429; 14 prompts (the WP16 thirteen + `thales_spain_italy`). Same template and
model for both modes of a pair, so the pairs are head-to-head; one run per cell, so read
differences of one or two runs as noise. Columns: first call = delivered without any
repair; tool calls = all build calls of the cell; decks ×3+ = delivered decks with one
non-structural kind on 3+ slides; max reuse = most uses of one template slide in a deck.

| model | template / mode | variety_check | success | first call | tool calls | variety asks | decks ×3+ | max reuse (mean) | max kind repeat (mean) | distinct/slides | wall s/run | tokens in/out (k) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| small | paintress rules | template_slide | 13/14\* | 4 | 25 | 1 | 9 | 3 (1.46) | 11 (4.23) | 0.93 | 23.7 | 89/29 |
| small | paintress rules | kind | 12/14\*\* | 3 | 29 | 8 | 7 | 4 (1.58) | 5 (2.83) | 0.93 | 24.6 | 120/37 |
| small | paintress rules | off | 14/14 | 4 | 29 | 0 | 10 | 3 (1.29) | 11 (4.21) | 0.94 | 23.2 | 111/31 |
| small | paintress vision | template_slide | 13/14\* | 7 | 23 | 0 | 10 | 3 (1.38) | 10 (4.31) | 0.92 | 22.0 | 82/27 |
| small | paintress vision | kind | 13/14 | 1 | 32 | 10 | 6 | 3 (1.69) | 8 (2.92) | 0.89 | 26.9 | 124/38 |
| small | paintress vision | off | 13/14\* | 7 | 20 | 0 | 9 | 3 (1.38) | 9 (4.31) | 0.92 | 19.5 | 64/22 |
| small | corporate rules | template_slide | 13/14 | 6 | 26 | 2 | 8 | 2 (1.54) | 9 (4.15) | 0.89 | 20.1 | 86/24 |
| small | corporate rules | kind | 11/14 | 1 | 38 | 9 | 5 | 3 (1.55) | 6 (2.82) | 0.91 | 24.1 | 143/37 |
| medium | paintress rules | template_slide | 13/14† | 4 | 22 | 2 | 7 | 3 (1.69) | 8 (3.15) | 0.88 | 19.8 | 71/19 |
| medium | paintress rules | kind | 12/14† | 1 | 25 | 7 | 2 | 3 (1.58) | 3 (1.83) | 0.90 | 19.2 | 90/23 |

\* the one failure is the known harness artifact (an invented image id, no `document_content`
port). \*\* both failures are that artifact. † `no_tool_call` only: medium writes a plan and asks
the user to confirm, which a one-turn harness counts as a failure (WP17). The other failures
are `repairs_exhausted` on fit problems: `paintress/vision/cyber_2027` (kind),
`corporate/rules/country_comparison` (both modes), `cyber_2027` and `quarterly_review`
(corporate, kind). The built-in template ran in each process too (`target/eval-wp19-*`), same
picture: kind 14/14 and 12/14 against template_slide 14/14 and 13/14.

Totals over the four pairs (3 mistral-small, 1 mistral-medium; 56 runs per mode,
template_slide → kind): success 52 → 48 (without the harness artifact and `no_tool_call`: 52/53
→ 48/52), first call 21 → 6, tool calls 96 → 124 (+29 %), input tokens 328k → 477k (+45 %),
variety asks 5 → 34, decks with a kind on 3+ slides 34 → 20; mean worst kind repeat 4.2 → 2.9
(small) and 3.2 → 1.8 (medium); wall time per run 21.9 → 25.2 s on small (+15 %), unchanged on
medium.

- **`template_slide` almost never asks (5 asks in 56 runs) and behaves like `off`**: the
  assigner's reuse cost (D12) already keeps one template slide to 3 uses at most, so the
  trigger rarely fires. `off` vs `template_slide` on Paintress small: same success (27 vs 26
  of 28, the difference is the artifact), same first call (11 vs 11), same variety.
- **`kind` buys variety, at a cost.** Decks with one kind on 3+ slides nearly halve and the
  worst repeat drops by about 1.5 slides, on every pair; medium in `kind` mode gives the most
  varied decks of the matrix (2 decks ×3+, worst 3). The cost: first-call success collapses
  (an asked deck is never a first-call success), 29 % more build calls and 45 % more input
  tokens (each ask is one more model call carrying the deck), and 3 more failed decks over
  42 mistral-small runs (all `repairs_exhausted` on fit problems, 2 of them corporate).
- **Caps hold.** No delivered deck in any mode has 3+ figures slides; the evidence session's
  over-correction (4 figures slides on the single figures slide) did not recur. 23 of the 52
  recorded kind asks carry a `suggested` line. Max reuse 4 once (`paintress/rules/kickoff`,
  kind): 4 slides suggested `cards` (Paintress has 5 cards variants, so within the cap), but
  only one cards variant held their long text, so the assigner reused it.
- **The small-model evidence plan** (the live session's first call, rerun through `assign`):
  the agenda slide is now apart, the bullets count is 2, no ask in either mode; the live
  third call (4 figures slides) would now get no figures suggestion or option.
- **Recommendation: keep `template_slide` as the default.** The data does not clearly favour
  `kind`: it is the better choice for deck variety (and on mistral-medium it costs little:
  12 vs 13, both failures `no_tool_call`, +3 tool calls), but on mistral-small, the admin
  default, it trades 3 failed decks in 42, a 3× drop in first-call success and +29 % calls/+45 %
  tokens for that variety. An author who wants more varied decks can pick `kind`, best with
  a stronger model. Since `template_slide` is nearly inert, a follow-up could reasonably
  make `off` and `template_slide` one value; not done (developer's decision).

## Results: WP20 (max uses setting)

Run on 2026-10-07 after `b940f3e20` (the later commits are frontend and docs only), `make eval`
with `--no-builtin --modes rules --variety … --max-uses …` on the Paintress template, six
processes strictly one after the other, 14 prompts each, nothing else running, no 429 or quota
sign in any log. One run per cell: read differences of one or two runs as noise. Success
excludes the known harness artifacts, listed apart (an invented image id with no
`document_content` port; medium's `no_tool_call`, WP17). Columns as in WP19.

| cell | model | variety_check | max | success | apart | first call | tool calls | variety asks | decks ×3+ | max reuse (mean) | max kind repeat (mean) | distinct/slides | wall s/run | tokens in/out (k) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | small | template_slide | 2 | 13/14 | – | 6 | 27 | 0 | 10 | 3 (1.38) | 7 (3.77) | 0.94 | 22.2 | 102/30 |
| 2 | small | template_slide | 1 | 10/11 | 3 image id | 3 | 27 | 3 | 5 | 4 (1.60) | 6 (2.70) | 0.93 | 20.5 | 114/31 |
| 3 | small | kind | 2 | 11/11 | 3 image id | 1 | 30 | 9 | 8 | 2 (1.45) | 7 (3.82) | 0.92 | 22.5 | 122/36 |
| 4 | small | kind | 1 | 13/13 | 1 image id | 1 | 32 | 10 | 4 | 2 (1.31) | 7 (2.38) | 0.95 | 23.7 | 129/36 |
| 5 | medium | kind | 1 | 11/11 | 1 image id, 2 no_tool_call | 0 | 25 | 8 | 0 | 2 (1.55) | 2 (1.64) | 0.91 | 19.5 | 95/25 |
| 6 | medium | template_slide | 1 | 13/13 | 1 no_tool_call | 3 | 27 | 6 | 6 | 2 (1.31) | 5 (2.54) | 0.95 | 20.1 | 96/24 |

The other failures are `repairs_exhausted` on fit problems: `training_12` (cell 1), `kickoff`
(cell 2). Contact sheets (not committed): `~/fred-tmp/wp20-sheets/<cell>.png` for
`thales_spain_italy` (cells 1, 2, 4; that run is an artifact in cells 3, 5, 6) and
`~/fred-tmp/wp20-sheets/cyber_2027/<cell>.png`, delivered in all six cells.

- **Max 2 on the new assigner is the old behaviour.** Cell 1 against WP19's small Paintress
  rules `template_slide` row: same success (13/14), no ask, decks ×3+ 10 vs 9, worst kind
  repeat 3.77 vs 4.23. The over-max cost rarely changes a choice at 2, since D12 already
  spreads template slides.
- **Max 1 by template slide buys variety at almost no cost** (cell 2 vs 1): decks with a kind
  on 3+ slides halve (10 → 5 of 13 and 10), the worst kind repeat falls 3.77 → 2.70, tool calls
  are unchanged (27), 3 asks, input tokens +12 %; first call 6 → 3. Max reuse 4 once
  (`options_comparison`: four `two_columns` slides asked, Paintress has one such variant; the
  ask came, the model resent; the requested kind is kept, D7).
- **By kind asks often**: 9–10 asks in 14 runs on small, first call falls to 1, +11–19 % calls,
  +20–26 % input tokens. At max 2 its variety is no better than cell 1 here (one run; three
  artifacts); at max 1 it gives the best small-model variety (4 decks ×3+, worst 2.38).
- **Medium uses the max well**: `kind` max 1 gives the most varied decks measured so far (no
  deck with a kind on 3+ slides, worst 1.64), at 25 calls; `template_slide` max 1, 27 calls and
  6 decks ×3+.
- **Recommendation for the V1 beta defaults: switch on, `template_slide`, max 1.** On
  mistral-small, the admin default, it is the only setting that improves variety clearly
  without more model calls; `kind` max 1 is more varied but asks on most first decks (first
  call 1 of 14, +26 % tokens), a better fit for an author with a stronger model. Not applied:
  the developer validated max 2 in real sessions with small and medium and keeps the code
  default (`template_slide`, max 2) on 2026-10-07; max 1 scored slightly better here only.

## Results: WP21 (limits in the schema, build directly, framed pictures, agent prompt)

Run on 2026-10-07 after `5f5c251cd` (final code for items 1–3 and the harness option), `make
eval` with `--no-builtin --modes rules --variety template_slide --max-uses 1` on the Paintress
template, four processes strictly one after the other, 14 prompts each, nothing else running, no
429 or quota line in any log. Stand-in = the harness's one-line agent prompt; optimized =
`eval/agent_prompts/agent_prompt_fr.txt` (`--agent-prompt`). One run per cell: read differences
of one or two runs as noise. Success excludes the harness artifacts, listed apart (an invented
image id with no `document_content` port; `no_tool_call`). Since WP21 the deck metrics re-run the
assignment with the run's variety mode and max, as the tool did; WP20's max-1 rows were measured on
the default (max 2) assignment, so their variety columns are approximate (success, calls, tokens
and fit problems are not affected).

| cell | model | agent prompt | success | apart | first call | tool calls | variety asks | decks ×3+ | max kind repeat (mean) | max reuse (mean) | slides (mean) | wall s/run | tokens in/out (k) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WP20 cell 2 | small | stand-in | 10/11 | 3 image id | 3 | 27 | 3 | 5 | 6 (2.70) | 4 (1.60) | 6.1 | 20.5 | 115/31 |
| A | small | stand-in | 13/13 | 1 image id | 3 | 30 | 5 | 7 | 6 (3.31) | 2 (1.54) | 7.5 | 25.8 | 132/39 |
| B | small | optimized | 13/14 | – | 3 | 31 | 5 | 11 | 7 (4.54) | 4 (1.69) | 8.8 | 20.6 | 129/24 |
| WP20 cell 6 | medium | stand-in | 13/13 | 1 no_tool_call | 3 | 27 | 6 | 6 | 5 (2.54) | 2 (1.31) | 6.9 | 20.1 | 97/25 |
| C | medium | stand-in | 14/14 | – | 5 | 25 | 5 | 8 | 6 (3.00) | 3 (1.64) | 7.4 | 18.8 | 83/15 |
| D | medium | optimized | 14/14 | – | 4 | 27 | 5 | 9 | 5 (2.93) | 2 (1.36) | 7.6 | 19.4 | 105/17 |

The failures: `committee_agenda` (B, `repairs_exhausted`). Fit problems by field over every call of
the cell (a slide's `needs_revision` entry split into its problems; "too long" = over the zone's
room, "no place" = a field the closest slide lacks):

| cell | problem slides | cover subtitle too long | figure labels too long | items over max | no place (item fields) | other |
|---|---|---|---|---|---|---|
| WP20 cell 2 | 26 | 5 | 5 | 5 | 5 | 7 (4 ignored `columns2`, 2 two_columns bullets, cover items) |
| A | 24 | 3 | 6 | 4 | 7 | 5 (columns over max ×2, cover title, cover items, bullets) |
| B | 24 | 5 | 4 | 5 | 11 | 4 (cover title, items, bullets; figures subtitle) |
| WP20 cell 6 | 11 | 1 | 5 | 3 | 0 | 2 (cover title, cover items) |
| C | 9 | 0 | 2 | 1 | 0 | 6 (3 figures bullets, columns over max ×2, cover items) |
| D | 12 | 1 | 6 | 1 | 2 | 2 (team label, table columns) |

Contact sheets (not committed): `~/fred-tmp/wp21-sheets/{cyber_2027,thales_spain_italy}/<cell>.png`,
all four cells delivered both prompts.

- **Items 1–3 against WP20 cell 2 (A):** same first-call success (3), one fewer failure
  (13/13 vs 10/11, the remaining artifact is one invented image id against three), 3 more build
  calls over 3 more counted runs. Cover-subtitle problems fall 5 → 3, figure labels do not
  (5 → 6): the label hint reads "Room: team ≈25 chars; cards ≈18 chars; figures ≈12 chars" and
  mistral-small still writes 18–40-char labels. On medium (C vs WP20 cell 6) problem slides
  11 → 9, figure labels 5 → 2, cover subtitles 1 → 0, first call 3 → 5, calls 27 → 25, input
  tokens −14 %. The schema hints help the stronger model clearly and the small one only on the
  cover subtitle; one run per cell.
- **Build directly (item 2):** `no_tool_call` 0 in both medium cells (28 runs) against 3 in WP20's
  two medium cells (28 runs).
- **Framed pictures (item 3):** the image-cards slides (`slide:266`, `slide:267`) were picked 4
  times in WP20 cells 2 and 6 and never in WP21 (no plan gave pictures); the cyber_2027 sheets show
  no grey band. The live slide ('Nos quatre priorités', `kind: cards`, no pictures) now lands on
  "6 zones de texte avec images + texte latéral" (3 of 6 cards kept, no band).
- **Optimized prompt (B vs A, D vs C):** no gain on the measured path. Success and first call are
  unchanged on small (13 vs 13, 3 vs 3) and one lower on medium (first call 4 vs 5, +2 calls,
  +26 % input tokens). Decks get longer (rule 1, 8–12 slides: mean 8.8 vs 7.5 on small) and less
  varied on small (11 decks with a kind on 3+ slides vs 7, worst repeat 4.54 vs 3.31); on medium
  variety is about equal (9 vs 8 decks ×3+, max reuse 1.36 vs 1.64). Output tokens fall a third on
  small (24k vs 39k: rule 7, a short answer). Rule 2 ("à compléter" instead of inventing) shows on
  every no-document prompt: D's thales_spain_italy deck carries "à compléter" on most bullets,
  where C wrote plausible content; with team documents this is the intended behaviour, in the
  eval (no documents) it empties the slides.
- **Recommendation: do not ship the optimized prompt as the suggested prompt as is.** It costs
  tokens and variety on mistral-small and buys nothing measurable on mistral-medium; its rules 3
  (build directly) and 5 (write short) duplicate what the capability fragment and the schema
  now carry. Its useful parts for an author are rule 2 (no invented figures, when the agent has
  documents) and rule 7 (short answer after delivery): a shorter suggested prompt keeping those
  two, without the slide count and the variety rules, would be the candidate to measure next.

## Results: WP22 (short author prompt)

Run on 2026-10-07, same harness options as WP21 (`--no-builtin --modes rules --variety
template_slide --max-uses 1`, Paintress, 14 prompts), two processes strictly one after the other, no
429 or quota line in either log. Short = `eval/agent_prompts/agent_prompt_short_fr.txt`: the
stand-in in French plus two rules (no invented figure, qualitative content rather than a
placeholder; one or two sentences after delivery, no slide recap). A–D are WP21's runs, not re-run.
The harness now makes one more model call after delivery and keeps its tokens apart, so build
tokens stay comparable. A–D never made that call: the reply columns come from a **replay** of every
delivered run's last turn (system prompt, request, last build call, delivery message, then the
model's answer, tools still bound), the same for all six cells. "Rebuilds" = the model called the
tool again instead of answering. "New figures" = amounts, percentages and large counts on the two
prompts that give none (`cyber_2027`, `thales_spain_italy`), from the last plan. One run per cell.

| cell | model | agent prompt | success | apart | first call | tool calls | decks ×3+ | slides (mean) | tokens in/out (k) | reply chars (mean, replay) | rebuilds after delivery (replay) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | small | stand-in | 13/13 | 1 image id | 3 | 30 | 7 | 7.5 | 132/39 | 895 (11) | 2/13 |
| B | small | optimized | 13/14 | – | 3 | 31 | 11 | 8.8 | 129/24 | 891 (9) | 4/13 |
| E | small | short | 11/12 | 2 image id | 2 | 31 | 7 | 7.5 | 136/32 | 42 (2) | 9/11 |
| C | medium | stand-in | 14/14 | – | 5 | 25 | 8 | 7.4 | 83/15 | 790 (8) | 6/14 |
| D | medium | optimized | 14/14 | – | 4 | 27 | 9 | 7.6 | 105/17 | 467 (7) | 7/14 |
| F | medium | short | 13/14 | – | 5 | 22 | 7 | 6.8 | 79/13 | 91 (7) | 6/13 |

The failures: E `cyber_2027` (`repairs_exhausted`), F `thales_spain_italy` (`no_tool_call`: a
proposed outline and "Peux-tu le valider ?"). In-run replies (the new harness call, E and F only):
mean 54 chars with 5/11 rebuilds (E), 83 chars with 5/13 rebuilds (F).

- **Short answer: holds.** Text replies fall from 790–895 chars (stand-in) and 467–891
  (optimized) to 42–91 chars, one sentence ("La présentation est prête.", "La présentation
  « Onboarding_7_etapes.pptx » (7 slides) est prête."), on both models.
- **But on small it turns the answer into a rebuild.** With the short prompt, mistral-small
  called the tool again after delivery on 9 of 11 replayed turns (A 2/13); each is a full extra
  build (400–850 output tokens in-run). Medium is unchanged (6/13 vs 6/14).
- **No invented figure: not followed.** Every cell invents the `cyber_2027` budget (the request
  asks for one and gives none): E 50/20/15/10 M€ as A, F 5/6/4 M€. On `thales_spain_italy`, E
  still writes "1 200+ employés", "30+ ans" (A: "18,1 milliards", "81 000"); F asked for an outline
  instead of building (C wrote one invented count, "80 000+"). No placeholder in F; one in E (a
  "+XX XXX XXX XXX" phone number on a closing slide). The eval has no team documents, where the rule is meant to act.
- **Build path:** small slightly worse (one more failure, first call 2 vs 3, same calls and
  variety, +3 % input tokens); medium neutral to better (first call 5 = 5, 22 vs 25 calls, decks
  ×3+ 7 vs 8, −5 % input tokens), with one outline question that costs the run.
- **Recommendation: do not ship the short prompt as the suggested prompt; the capability's own
  fragment with the stand-in stays the reference.** Its reply rule works but costs an extra build on
  mistral-small, the admin default; its figures rule does not change what either model writes here.
  If a shorter answer is wanted, the place to measure next is the delivery message itself (it already
  steers the model and is model-independent), not an author prompt.

## Results: WP29 (limits phrased in words)

Run on 2026-10-07 on `0342e5d3a` (words) and on `be7eefa06`, the commit before it (baseline: the
package's source at that commit, `git archive` into the scratchpad and put first on `PYTHONPATH`,
same venv), WP21's options (`eval/run_eval.py --no-builtin --modes rules --variety template_slide
--max-uses 1`, Paintress `~/fred-tmp/paintress.pptx`, 14 prompts, stand-in agent prompt, no contact
sheets), four processes strictly one after the other, no 429 or quota line in any log. A and C
(WP21) are not comparable as a baseline: WP23–WP28 changed the tool since (close-kind fallback,
message texts, renderer notes), so the baseline was re-run. One run per cell. Fit problems: counted
as in WP21 (a `needs_revision` entry split into its problems); "label elements" counts each
`items[i].label` named as too long on a figures slide.

| cell | model | code | success | apart | first call | tool calls | problem slides | figure labels too long (elements) | cover subtitle too long | decks ×3+ | max kind repeat (mean) | slides (mean) | tokens in/out (k) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (WP21) | small | WP21 | 13/13 | 1 image id | 3 | 30 | 24 | 6 | 3 | 7 | 6 (3.31) | 7.5 | 132/39 |
| base | small | `be7eefa06` | 11/11 | 3 image id | 2 | 28 | 24 | 9 (14) | 4 | 8 | 5 (3.18) | 7.8 | 126/35 |
| words | small | `0342e5d3a` | 11/11 | 3 image id | 4 | 23 | 10 | 4 (6) | 2 | 5 | 4 (2.27) | 6.8 | 109/25 |
| C (WP21) | medium | WP21 | 14/14 | – | 5 | 25 | 9 | 2 | 0 | 8 | 6 (3.00) | 7.4 | 83/15 |
| base | medium | `be7eefa06` | 14/14 | – | 7 | 23 | 8 | 1 (2) | 0 | 9 | 5 (2.93) | 7.0 | 80/17 |
| words | medium | `0342e5d3a` | 14/14 | – | 5 | 24 | 5 | 1 (3) | 0 | 8 | 5 (2.86) | 7.7 | 92/14 |

No failure in any cell; the "apart" runs are the eval's invented-image-id artifact (no
`document_content` port), on different prompts per run. Truncated, lost, leftovers and removed-by-check
are 0 in all four cells. Run dirs (not committed): `target/eval-wp29-{small,medium}-{base,words}`.

- **Small (the target):** every measure moves the right way. First call 2 → 4, build calls 28 →
  23, problem slides 24 → 10, too-long figure labels 9 → 4 problems (14 → 6 labels), cover
  subtitles 4 → 2, decks with a kind on 3+ slides 8 → 5, tokens −13 % in / −29 % out (fewer
  repair rounds outweigh the longer description).
- **Medium:** neutral. Same success, calls 23 → 24, problem slides 8 → 5, labels unchanged (1),
  first call 7 → 5 (WP21's C had 5: within one-run noise), input tokens +15 % (longer decks, 7.7
  vs 7.0 slides, and two more variety asks), output −18 %.
- **Cost:** the Paintress description grows 4 712 → 5 390 chars and the schema 4 601 → 4 973
  chars (≈ +300 tokens per model call); paid back on small by the saved rounds.
- **Wording, before → after** (Paintress): `label ≈12 chars` → `label 1 word (≈12 chars)`;
  `subtitle ≈32 chars` → `subtitle ≤4 words (≈32 chars)`; option `shorten items[1].label to
  ≈12 chars` → `shorten items[1].label to 1 word (≈12 chars)`; hint `Room: ≈71 chars; cover ≈12
  chars × 3 lines` → `Room: ≤10 words (≈71 chars); cover ≤3 words (≈12 chars × 3 lines)`.
- **Generic rule checked on two templates and the synthetic test inventories:** Paintress and
  the built-in deck read coherently (built-in: `title ≤8 words (≈56 chars)`, `items.number 1 word
  (≈7 chars)`); `test_builtin_rooms_read_as_words_then_chars` checks every room of the built-in
  description and schema leads with a budget within the rule. No template sample was usable as an
  example (D22).
- **Checks:** package `make code-quality` clean (pyright: the existing `builder_decks.py` `__all__`
  warning only), `make test` 433 passed, 5 skipped.
- **Recommendation: keep.** Clear gain on mistral-small (the admin default) on first-call success,
  calls, fit problems and variety, neutral on mistral-medium, no rendering regression.

## Results: WP31 (review fixes from live use)

Unit evidence only, no eval rerun (both fixes are deterministic):

- 31.1 `test_an_other_slide_given_a_kind_in_the_review_is_assigned`: a slide analysed
  `other` (`reusable: false`) yields `needs_revision`; with a `bullets` override it is
  assigned; re-kinded `other`, or a one-off given its own analysed kind, it stays unused.
- 31.2 `test_a_forced_cover_misfit_reads_once_without_a_close_kind_lead` asserts
  "the first slide is always the template's cover; closest fit, a 'cover' slide: title
  is 400 chars; …" (was "cover; ; closest close kind, closest fit, a 'cover' slide");
  `test_a_close_kind_misfit_names_why_and_the_close_kind_once` asserts "this template has
  no 'timeline' slide; closest close kind, a 'bullets' slide: …".
- Package `make code-quality` passed; `make test` 436 passed, 5 skipped.
- Not proven: the live review dialog round trip (the frontend already sends the kind
  override; no schema change).

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

- WP30 (template preparation guide, frontend and Help Center only, 2026-10-07):
  `npx tsc --noEmit -p .` clean; `npx prettier --check` clean on the touched files;
  `npx vitest run` on `helpCenter/`, `HelpCenterPage/` and `ppt_builder/`: 8 files,
  57 passed (new: `TemplateGuideLink` fr and en targets, new tab; the guide page
  resolves in both languages); full `npx vitest run`: 301 files passed, 1 skipped,
  3419 tests passed, 7 skipped. Not proven: the link and the page in a browser.
- WP26 (variety ask counts misfit slides by their closest fit): package `make code-quality`
  passed (basedpyright 0 errors, the 1 warning in `tests/builder_decks.py` untouched);
  `make test` 425 passed, 5 skipped (the reference-template tests). Added
  `test_slides_that_fit_nothing_repeat_on_their_closest_fit` (the live Paintress shape: a
  `label` on the items of two cards slides, max 1 → both problems and a `variety` entry for
  slides 2, 4; a timeline slide without a label zone not offered) and
  `test_slides_to_fix_that_repeat_are_asked_to_vary_in_the_same_round` (built-in template,
  max 1: labelled process slides → `slides` [2, 3] and `variety` [2, 3]; the fixed plan with
  kinds unchanged is built, the repeat only noted). Changed: the slide to fix now joins its
  closest fit's group in `test_repeats_are_found_beside_slides_that_fit_nothing` ([1, 2, 3, 4])
  and `test_a_first_call_with_fit_problems_carries_the_variety_ask` ([2, 3, 4, 5, 6]);
  `test_no_variety_ask_after_a_fit_repair` unchanged and green (no repeat detectable on its
  first call, so the repaired deck is built with the note). No LLM call, KPI or shared state
  touched: the closest fit was already computed for the problem text; the stand-in
  candidates add one beam pass entry per slide to fix, on a call that builds nothing.
  Not proven: the live mistral-small session re-run.
- WP28.4 (renderer findings forwarded, 2026-10-07): package `make code-quality` passed
  (basedpyright 0 errors, the 1 warning in `tests/builder_decks.py` untouched); `make test`
  431 passed, 5 skipped. New: `test_a_renderer_finding_reaches_the_model_in_the_review_notes`
  (showcase template, cover + 4-part agenda → delivered, `deck_delivered`
  true, the agenda line under "To review"), `test_a_table_the_render_cannot_fit_is_a_note_with_its_remedy`
  (6 columns forced on the 5-column table → the measured note, no `not placed: table`).
  Changed: the agenda, one-line, no-items and fixed-slide render tests assert the exact
  note text on `report.notes`. No LLM call, I/O or shared state touched (strings on the
  render worker, one log line per build). Not proven: a live small-model session acting
  on the forwarded agenda note.
- WP28 (close-kind fallback and actionable messages, 2026-10-07): package `make code-quality`
  passed (basedpyright 0 errors, the 1 warning in `tests/builder_decks.py` untouched);
  `make test` 429 passed, 5 skipped. New: `test_an_agenda_too_long_is_never_built_on_an_unrelated_kind`
  (the live shape: agenda max 8, team max 15, 9 items → `needs_revision` "items: 9 given; the
  largest 'agenda' slide holds 8", trim/split first, a bullets option, no team),
  `test_an_agenda_too_long_goes_to_a_close_kind_that_holds_it` (a process slide of 10 → built
  there, note with the fix), `test_an_agenda_written_as_bullets_goes_to_a_bullets_slide`.
  Changed: cover → section and closing → section/bullets notes now carry the remedy; a
  fixed closing given contact lines lands on `section` (first close kind) instead of
  `bullets`; process over capacity names the largest process slide (3), no longer the team
  slide (6); exact texts of the empty plan, repeated problem and review-note tests. The
  variety/first-call tests (merged ask, no ask after a fit repair, closest-fit count) are
  unchanged and green. No LLM call, I/O or shared state touched (a static table and string
  formatting on a call that already runs in `to_thread`). Not proven: the live
  mistral-small session re-run, and the first-call rate on the eval (a requested kind that
  used to land on an unrelated slide now asks for a revision).
- WP27 (parallel copies of a build call, 2026-10-07): new `test_a_parallel_copy_of_a_call_is_not_built_twice`; package `make code-quality` (0 errors) and `make test` 426 passed, 5 skipped. Live trigger: session 157140ab, mistral-small sent one call twice in parallel.
- PowerPoint (developer check, 2026-10-07): a deck delivered by the build tool opens in
  PowerPoint without a repair prompt, verifying the sections fix (`d1deb28ed`, 24.1).

- WP25 (platform review fixes): `make code-quality` passed in fred-sdk, fred-runtime,
  control-plane-backend, fred-capability-ppt-filler and fred-agents (basedpyright 0 errors;
  fred-runtime's 5 and ppt-filler's 1 warnings are in files this change does not touch).
  `make test`, one project at a time: fred-sdk 563 passed, 3 skipped; fred-runtime 1817
  passed, 11 skipped; control-plane 1587 passed; ppt-filler 423 passed, 5 skipped;
  fred-agents 121 passed, 6 xfailed. `alembic heads`: one head, `b8e1f4a2c6d9`. Frontend
  after regenerating the control-plane and runtime clients (`make generate-openapi` in each
  backend, then `npx @rtk-query/codegen-openapi` on `controlPlaneOpenApiConfig.json` and
  `runtimeOpenApiConfig.json`; only the `UIHints.widget` description changed):
  `npx tsc --noEmit -p .` clean, `npx vitest run` 3416 passed, 7 skipped (301 files).
  Tests added or changed: control-plane `test_suspension_detail_migration.py` (downgrade
  lifts pending rows only, drops the column); `test_capability_readiness.py`: older pod (404)
  reads as ready, 503 gives no verdict, a stale pending read never clears a revocation (fake
  store and a real SQLite `AgentInstanceStore`, `updated_at` unchanged), save with no verdict
  → pending without detail, config-invalid → pending in a single write, save answered ready
  clears pending, listing skips a failed preparation, listing rotates over the cap on one
  shared client; `test_agent_copy.py`: copy pending while preparing, caller's token used,
  destination routing sent; `test_product_api_authz.py`: readiness-check needs
  `CAN_UPDATE_AGENTS` and `require_own_credential`. fred-runtime
  `test_capability_route_team_authz.py`: 403 for a non-member on validate-config, readiness
  and copy-config, a member passes with `CAN_UPDATE_AGENTS` (save, both copy teams) and
  `CAN_USE_TEAM_AGENTS` (readiness), a secured save without `team_id` is 422;
  `test_capability_readiness_endpoint.py`: a raising hook is `pending`, an unreadable slice
  omitted; `test_capability_copy_config.py`: routing reaches the target save only;
  `test_capability_platform_ports.py`: a revoked model is used until the 30 s TTL, then
  not, one ReBAC query within it. fred-sdk: no module-level fastapi import outside the lazily
  loaded `_capability_route_deps.py`; ppt-filler's router tests pass on the lazy path.
  Not proven: against a real pod and Postgres (the compare-and-set is one conditional
  `UPDATE`, checked on SQLite); the readiness route does not bind `agent_instance_id` to the
  named team (the pod has no instance-to-team mapping), so a member of one team can learn
  another team's instance readiness state by id; the sweep calls the pod without a token, so
  on a secured pod its config-health and readiness checks get no verdict (unchanged, the
  sweep has no production host).
- WP25 `fred-performance-reviewer` (25.3, 25.4, 25.6): no blocking finding. No LLM call
  site, KPI or Prometheus label added. 25.4: listing readiness calls now share the
  control-plane runtime client (`app/context.py` `get_runtime_http_client`, httpx default
  pool of 100) instead of one `AsyncClient` per check, each still bounded at 2 s total,
  pool wait included (`asyncio.timeout` in `_fetch_capability_readiness`); failed rows are
  no longer re-checked, so a team with a failed analysis stops paying the 2 s worst case on
  every listing; over the cap a `SystemRandom` sample (stateless, replica-safe). Needs a load
  test: many concurrent listings with slow pods could fill the shared pool and delay session
  erasure calls on the same client by up to 2 s (bounded). 25.3: a capability save makes
  the same single readiness call as before (5 s bound) and now one conditional `UPDATE`
  instead of a clear plus a suspend; a copy adds that call per destination, inside its
  4-destination semaphore. 25.6: at most one ReBAC lookup per port every 30 s (a 20-slide
  vision analysis adds 2-4), serialized by the port's existing lock only while refreshing.
  Minor: readiness latency and no-verdict counts are logged, not metered.

- WP24-frontend (review fixes, committed before WP25): `a0cbeb10a` a nested Dialog owns
  Escape over its FullPageModal; `7fbd33d27` a pattern rename is kept when the review dialog
  closes on Enter or Escape; `d46137705` a running analysis keeps being polled after a failed
  poll; `6d2579c2b` the agent-list poll for a preparing agent backs off and stops;
  `b6b6f61da` a literal NUL in the part identity key replaced by an escape; `2a9b38202`
  keyboard focus stays on a pattern after toggling its inclusion; `6ef46ff47` a side panel
  shared by two capabilities is offered once; `5edf97cb7` COMPONENT-UX record corrected.
  Full `npx vitest run` 3416 passed (re-run green after WP25's client regeneration). Not
  proven: the keyboard and focus behaviour in a real browser.

- WP24 (review fixes): package `make code-quality` passed (ruff, import order, format,
  bandit, detect-secrets, basedpyright 0 errors); `make test` 423 passed, 5 skipped (the
  reference-template tests). 15 tests added, each checked to fail without its fix (24.9's
  test exercises the new `_assign_loadable`): `test_rendered_and_patterns_decks_carry_no_stale_sections`,
  `test_pptx_archive.py` (3), `test_a_turn_never_renders_a_template_other_than_the_analysed_one`,
  `test_an_outdated_inventory_whose_refresh_never_lands_is_served_from_memory`,
  `test_a_refresh_that_lands_here_replaces_the_cached_outdated_inventory`,
  `test_a_recovery_without_the_port_stores_rules_and_a_save_relabels`,
  `test_a_forced_refresh_without_the_port_is_not_mistaken_for_vision`,
  `test_a_cancelled_job_keeps_its_slot_until_its_thread_ends`,
  `test_background_work_leaves_heavy_slots_to_the_turns`,
  `test_a_rebuilt_row_returns_the_sha_of_the_file_it_analysed`,
  `test_uploading_the_same_file_again_keeps_its_analysis`,
  `test_a_kind_declared_by_a_shape_name_outranks_vision`,
  `test_an_image_id_that_does_not_load_leaves_a_framed_picture_empty`. The analysis tests now
  save with a model port (labelling faked), since a save without one stores `rules`.
  Not proven at the time: PowerPoint itself opening a rendered deck without a repair prompt
  (checked on the XML only; since verified in PowerPoint, see the 2026-10-07 entry); no `ANALYSIS_VERSION` bump, so analyses already labelled by vision keep a
  vision kind over a shape-name declaration until their next re-run.
- WP24 `fred-performance-reviewer` (turn path: 24.3, 24.4, 24.6, 24.9): no blocking finding.
  No LLM call site, KPI or Prometheus label touched. 24.3: the build's template is now an
  in-memory hit per pod (`_templates`, 4 entries by sha, immutable so replica-safe; worst case
  ~200 MB for four 50 MB templates) instead of one asset-store HTTP fetch per build; a miss is
  one async row read filtered on the sha. 24.4: an outdated inventory no longer costs every
  model call (`_resolve` in `awrap_model_call`) a row read plus a `model_validate_json` on the
  event loop; it is re-read at most every 60 s per pod (cross-replica staleness bounded by
  that). 24.6: background python-pptx work holds ≤ 2 of the 4 heavy-job slots; waiting jobs
  poll once a second (no thread, no DB); turns keep 2 slots against any refresh burst. 24.8
  keeps a cancelled job's slot until its thread ends, so the bound is real. 24.9: the
  pictures are fetched before the assignment (bounded-concurrency `_prefetch_image_bytes`,
  unchanged) and the template after it, no longer in one `gather`: with the template
  cached the added latency is nil; on a cache miss it is one row read, and a plan that needs
  revision now pays its picture fetches (only plans with pictures). The header check runs in
  the assignment's worker thread (0.009 ms per picture); `check_archive` reads the central
  directory only (0.16 ms on the built-in deck), always in a worker thread.

- WP23 `fred-performance-reviewer` (tool path, middleware, analysis store): no finding. The
  build tool loses an HTTP listing (it ran when an ask was possible) and gains an in-memory scan
  of the last model call's messages, only when an ask would follow: 16 µs on 300 messages. The
  middleware stores a reference to `request.messages` per model call (no copy, no I/O, nothing on
  the LLM call path). The outdated-analysis refresh adds no write per turn (claimability is
  checked in Python first, then one conditional `UPDATE` wins across replicas); the job runs in
  the existing background slot. An outdated inventory is served uncached, so while one exists
  (a refresh running, or after a failed one until the author re-runs) each turn of that agent
  does one primary-key `SELECT` and parses the inventory on the event loop (0.1 ms for the
  built-in template's 18 kB). No new KPI, label or shared client; `_ports` stays pod-local, as
  before.
- WP23.3 (D19 cap): documentation only. `_caps` in `assign.py` computes one cap per mode from
  the deck's content slides and the pool's content template slides (or kinds) since it was
  introduced (`8a2ddfa9e`); `test_assign.py::test_max_uses_is_raised_to_what_the_template_allows`
  already pins that behaviour ("four content slides on three template slides: one is used twice
  anyway"). D19 and the spec scenario now say so; no test added (behaviour unchanged).
- WP23.2 (outdated analysis refresh): package `make code-quality` passed; `make test` 407
  passed, 5 skipped. New in `test_analysis_job.py`: an analysis one `ANALYSIS_VERSION` behind
  stays `ready` under two concurrent readiness checks and a turn's read, exactly one job starts,
  the row stays `succeeded` with `current: true` while it runs, the old inventory serves the
  turn, and after the job the new version is stored and cached; a refresh whose analysis fails
  keeps the old inventory and version, spends `MAX_ATTEMPTS`, reports `current: false`, starts
  no second job on later checks, and a forced re-run starts one with the agent still ready. In
  `test_builder_capability.py` the re-run route on an outdated analysis keeps it `succeeded`.
  No schema change (no migration), no API field change (the `current` comment only), no
  frontend change: the existing "outdated" message and re-run button now show only after a
  failed refresh. Not proven: several real replicas racing on Postgres (the claim is one
  conditional `UPDATE`, as `claim_interrupted`).
- WP23.2 follow-up (vision-labelled refresh only with its model port): `make code-quality`
  passed; `make test` 408 passed, 5 skipped. New in `test_analysis_job.py`: a vision-keyed
  outdated row on a pod without a remembered port starts no job on readiness or a turn read,
  stays ready and reports `current: false`; once the port is remembered, one job starts with
  that port and stores the current version. Frontend: `analysis.outdatedVision` (fr/en) shown
  for an outdated vision-labelled analysis, re-run button unchanged; `npx tsc --noEmit` clean
  apart from the worktree's missing `oidc-client-ts` module (pre-existing, `src/security/`),
  prettier clean on the touched files. Not run: vitest (the worktree's `node_modules` lacks
  `oidc-client-ts`; the new `PptBuilderTemplatePanel.test.tsx` case is unverified).
- WP23.1 (first deck from the history): package `make code-quality` passed; `make test` 405
  passed, 5 skipped. `test_build_tool.py`: the two listing tests deleted with `_deck_delivered`
  and the `FsEntry`/`ls` fakes (tests and eval); new: a delivered deck's real text in the
  history → no ask, the repeated plan built with the note (template slide and kind modes); a
  history of a real `needs_revision`, a real error and another tool's "Delivered" text → still
  asked; both success texts (preview, download only) count, a template-load error does not;
  the preview build's own text is recognised. The first-deck ask now fires in production
  again (it never did since the port lost `ls`); not proven against a live pod transcript.
- WP21: package `make code-quality` passed; `make test` 400 passed, 5 skipped (new: framed
  picture misfit and fallback in `test_assign.py`, framed vs background in
  `test_builder_analysis.py`, field rooms in the schema in `test_build_tool.py`, "Build directly" in
  the fragment test, and the reference test `test_reference_image_cards_need_their_pictures`); with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 405 passed; on the Paintress deck the
  reference-bearing files (analysis, render, assign, table, build tool) 197 passed.
  `make builtin-inventory` regenerated (`ANALYSIS_VERSION` 11; `framed` on every zone, true on the
  built-in "Pairing text with a visual" picture). The dumped ppt_builder OpenAPI gained
  `Zone.framed`: slice regenerated (`fred_runtime dump-openapi ppt_builder` +
  `@rtk-query/codegen-openapi`), `npx tsc --noEmit` and prettier clean. Root cause of the grey band:
  `slide:266`'s layout "Images + 3 colonnes de texte" draws `Rectangle 2` (full width, 25–49 % of
  the height) behind its three picture placeholders; the renderer removed the empty placeholders
  and the layout's rectangle stayed; `_IMAGE_HOLE` could not avoid it since a requested kind is its
  slide's only tier and `slide:266` was the only `cards` variant holding that text.
  `fred-performance-reviewer` on the tool path: no new I/O, KPI or shared state; the schema cache
  stays a bounded pod-local `lru_cache(64)` keyed by content (kinds + hints), so replicas agree;
  `field_hints` runs per turn on the event loop, 0.13 ms on Paintress; tools build per turn 1.01 →
  1.16 ms (median of 50), cold schema 3.5 → 4.8 ms; tool parameters JSON 3 198 → 3 783 chars on
  Paintress (2 569 → 3 218 built-in), i.e. ≈150 more input tokens on every model call of a ppt
  turn, the one cost on the LLM path; the description is unchanged (4 651 chars). `assign` (in
  `asyncio.to_thread`) on a 29-slide Paintress plan 337 ms before / 339 ms after (median of 7 ×3).
  No finding.
- WP20: package `make code-quality` passed; `make test` 397 passed, 4 skipped (2 new in
  `test_assign.py`: max 1 takes another variant of the same kind, kept requested kind with one
  variant, `off` unchanged; caps raised to what the template allows, structural slides apart,
  `at_most` on the repeat; 1 new in `test_build_tool.py`: guide sentence per mode and max, none
  when off; the defaults test now covers `variety_max_uses` (2 when missing, 1..5, not in
  `labelling_key`, both fields owned by the widget); one existing test gained a second kind,
  since a one-slide template now raises the cap to the deck); with
  `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 401 passed; on the Paintress deck the
  reference-bearing files 181 passed. The dumped ppt_builder OpenAPI equals the committed slice:
  no regeneration. Frontend: `npx tsc --noEmit` clean, prettier clean, eslint clean on
  `ppt_builder/`; vitest on `ppt_builder/`, `src/locales` and `AgentFormModal/` 87 passed (4 new
  in `PptBuilderVarietySettings.test.tsx`: the sentence's labels, off saves `"off"` and disables
  the selects, on restores the last mode, on from a stored `off` gives `template_slide`, the max
  saves a number), Help Center 17 passed. Not proven: the row in a browser at narrow widths
  (CSS wraps the sentence; developer check). `fred-performance-reviewer` on the tool path: no
  new I/O, no shared state (the max is read from the turn's config when the tool is built);
  `assign` stays in `asyncio.to_thread`; the caps are one pass over the slides and the beam
  state gains one frozenset of content uses (beam still 32): assign on a 29-slide Paintress plan
  257 ms before, 257–262 ms after across modes and max values (median of 7, same host). The
  LLM-path cost is the asks' (table above). No finding.
- WP19: package `make code-quality` passed; `make test` 394 passed, 4 skipped (3 new in
  `test_assign.py`: structural slide apart on the small-model plan, figures capped by its
  variants, suggestions spread across kinds; 2 in `test_build_tool.py`: each mode's ask,
  default for a stored config without the field and not in `labelling_key`, manifest enum;
  existing kind-advice tests now pass `variety="kind"` and expect the capped suggestions);
  with `PPT_BUILDER_REFERENCE_TEMPLATE` on the corporate deck 398 passed; on the Paintress
  deck the reference-bearing files 178 passed. The dumped ppt_builder OpenAPI equals the
  committed slice (the config model is not in it): no regeneration. Frontend: fr/en labels;
  `npx tsc --noEmit` clean, prettier clean, vitest on `ppt_builder/`, `src/locales` and
  `AgentFormModal/` 79 passed; a throwaway render of `CapabilityConfigForm` with the four
  widget fields and `variety_check` showed the widget once and the select beside it (generic
  `TuningFieldRenderer` path, option labels from `fields.variety_check.options.*`).
  `fred-performance-reviewer` on the tool path: no new I/O, no shared state; the setting is
  read from the turn's config when the tool is built; `_repeats` (budget, spread) 0.4-0.5 ms
  on a 29-slide Paintress plan inside `assign`, which stays in `asyncio.to_thread`; assign
  365-372 ms vs 367 ms at WP18 on the same plan and host (median of 7). The LLM-path cost is
  the mode's: `kind` asks add model calls (+29 % in the table above). No finding.
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
