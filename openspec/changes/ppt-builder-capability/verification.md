# Verification: ppt-builder-capability

Evidence for WP9, WP11, WP12, WP13, WP15, WP16, WP17, WP18, WP19, WP20, WP21, WP22, WP29, WP31, WP32 and WP33 (design D11). Run on 2026-10-05 on a developer laptop. This is
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

## Results: WP32 (changes against the previous plan, D23)

Run on 2026-10-07, strictly one eval process at a time, no 429 or quota line in any log. WP29's
options (`eval/run_eval.py --no-builtin --modes rules --variety template_slide --max-uses 1`,
Paintress `~/fred-tmp/paintress.pptx`, 14 prompts, stand-in agent prompt) plus `--edit-turn`: after
a delivered deck, a second user turn asks for a change (`eval/prompts.py` `EDITS`: an inserted
key-figures slide, a contact on the last slide, a removal, a title), served by a new tool instance
on the same conversation and base-plan store, as on another pod. Turn-1 tokens are counted apart
from the edit turn's. Three small runs, each after a fix the previous one found:

- run 1 (`dba8dd868`): the first implementation;
- run 2 (`8480e3814`): corrected resend applied to its own base, `slides: null` read, change slides
  out of the schema;
- run 3 (`7a0460d05`): slide fields named in the change-slides description.

**Turn 1, like for like.** WP29's small cell lost `country_comparison`, `process_onboarding` and
`training_12` to the eval's invented-image-id artifact (no `document_content` port), so small is
compared on the other 11 prompts; the WP32 runs lost some to the same artifact too (run 2:
`training_12`; run 3: `esg_report`, `options_comparison`), counted as failures below.

| cell (small, 11 prompts) | success | first call | tool calls | problem slides | tokens in/out (k) | decks ×3+ |
|---|---|---|---|---|---|---|
| WP29 words | 11/11 | 4 | 22 | 10 | 92/18 | 5 |
| WP32 run 1 | 11/11 | 3 | 21 | 10 | 122/12 | 6 |
| WP32 run 2 | 9/11 (2 outline asked, no tool call) | 4 | 16 | 6 | 78/11 | 4 |
| WP32 run 3 | 9/11 (2 image id) | 4 | 19 | 9 | 101/17 | 4 |

All 14 prompts, small: run 1 14/14, first call 3, 30 calls, 18 problem slides, 191k/23k; run 2
11/14, 5, 20, 7, 96k/17k; run 3 12/14, 5, 24, 12, 127k/25k. Revision calls sent as `changes`:
8/16, 5/9, 0/11.

| cell (medium, 14 prompts) | success | first call | tool calls | problem slides | tokens in/out (k) | decks ×3+ | slides (mean) |
|---|---|---|---|---|---|---|---|
| WP29 words | 14/14 | 5 | 24 | 5 | 92/14 | 8 | 7.7 |
| WP32 (`7a0460d05`) | 14/14 | 5 | 24 | 7 | 111/13 | 8 | 7.4 |

Medium revision calls sent as `changes`: 5/10. Truncated, lost, leftovers: 0 in every cell.

**Edit turn.**

| cell | edits delivered | first call | calls | calls with `changes` | earlier slides kept identical |
|---|---|---|---|---|---|
| small run 1 | 9/14 | 7 | 26 | 23 | 60/68 |
| small run 2 | 10/11 | 8 | 17 | 11 | 55/65 |
| small run 3 | 12/12 | 9 | 16 | 7 | 75/93 |
| medium | 14/14 | 11 | 19 | 18 | 97/104 |

- Run 1's five failed edits found two bugs, fixed before run 2: three refused inserts resent
  corrected as `insert` and stacked one more copy per call (now: same shape → applied to the
  refused call's own base), two `slides: null` beside `changes` refused by validation (now read).
  Run 2's one failure (item fields written at slide level in inserted slides) led to run 3's
  field list in the change-slides description.
- Run 1's input tokens (+33 % like for like) came from the schema: LangChain inlines `$ref`s, so
  change slides typed as the hinted slide model repeated the whole slide schema (converted
  schema 10 146 chars against ≈5 k); plain objects with a field list bring it to 5 965 chars.
  The remaining ≈+1 k chars (≈300 tokens per call) is the likely part of medium's +21 % input.
- An edit sent as `changes` costs 60–260 output tokens (medium 60–226, small 62–77) against
  260–2 336 for a whole-deck resend, and keeps every untouched slide byte-identical; whole-deck
  resends reworded some (small run 3: schedule 1/3 kept, training 10/15, quarterly 6/8).
- An out-of-range number is self-correcting: in a smoke run, small had sent 5 of the 9 slides it
  described; its `edit slide 9` got "the previous deck has 5 slides", and it resent the whole deck.

Run dirs (not committed): `target/eval-wp32-{small,small-2,small-3,medium}`.

**Unit evidence:** `tests/test_deck_changes.py` (20 tests): every operation numbered on the base,
inserts after one slide in order, edit paths (field, element, append, null removes, table cell),
every error text and conflict, small-model shapes and the dumped-change round trip, partial fix
after `needs_revision` rebuilt whole, later-turn edit in a new tool instance keeping the other
slides identical, numbers of a revision on the new plan, corrected and identical resends never
applied twice, a variety ask then the same changes built once, no base / both modes / bad changes
building nothing with the base unchanged, an error after evaluation keeping the base, a failed
write still delivering, the base shared through the real SQL table, null `slides` and one change
object, the schema-size guard. Package `make code-quality` clean (existing `builder_decks.py`
`__all__` warning), `make test` 455 passed, 5 skipped; fred-agents `make test` 121 passed, 6 xfailed;
`q8c2e3b4d5f6` single head, SQLite upgrade, `alembic check`, downgrade.

**Performance review** (turn path, `fred-performance-reviewer` checklist): no blocking finding. The
base-plan upsert (`deck_plans.py`) is async SQLAlchemy, once per evaluated build call, skipped when
the plan is unchanged; the read happens only on a `changes` call without a plan of the turn in
memory. Both share the pod's 5-connection, 30 s pool with the analysis store: low risk since builds
are rare against model calls; exhaustion under an analysis-refresh burst would need a load test.
No statement timeout of their own, as the analysis store. `apply_changes` runs inline on decks of
≤ ~30 slides (well under 1 ms). No new metric, client or module state; the turn's base lives in the
tool instance, the shared one in Postgres (replica-safe).

**Known gap:** `cap_ppt_builder_deck_plan` rows are never deleted with their conversation (a few KB
each; no deletion hook reaches a capability); per-instance capability data cleanup is tracked by
GitHub issue #2990.

**Recommendation: keep.** Turn 1 is unchanged within one-run noise on both models (small: first
call and success at WP29's level, problem slides ≤; medium: same success, first call and calls,
input +21 % from the larger schema and description). The edit turn is where it pays: medium sent
18 of 19 edit calls as `changes`, 14/14 delivered, 97/104 earlier slides kept identical; small
delivered every edit in run 3, but sends `changes` for about half of them and rarely for first-deck
revisions (whole-deck resends stay correct, only costlier and prone to rewording).

## Results: WP33 (an overflowing list continues on a slide of the same kind, D24)

**Live case, deterministic** (Paintress `~/fred-tmp/paintress.pptx`, `template_slide` max 1, no
model): cover, a `Sommaire` agenda of 9 unnumbered entries (the SOMMAIRE slide holds 8), three
content slides. Rendered as 6 slides: `Sommaire (1/2)` and `Sommaire (2/2)` both on SOMMAIRE (5 + 4,
second part numbered `06`…`09`), plan numbers `[1, 2, 2, 3, 4, 5]`, note "Slide 2: its 9 items
continue on a second 'agenda' slide (5 + 4, titles marked (1/2) and (2/2)): the largest 'agenda'
slide holds 8. Nothing to do; to keep one slide, send at most 8 items.", and one agenda gap note
counting the split agenda once ("announces 9 parts but only 3 slide(s) follow it"). Before WP33
this plan was `needs_revision` (D21) or built on a process slide.

**Benchmark** (`7ed2c87d3` + `405c057ec`, run 2026-10-07, alone, no 429 or quota line): WP32's
settings (`--no-builtin --modes rules --variety template_slide --max-uses 1`, Paintress, 14 prompts,
stand-in prompt, `--edit-turn`, `mistral-small`), compared with WP32 small run 3 on the same 11
prompts (the same script reproduces run 3's figures).

| cell (small, 11 prompts) | success | first call | tool calls | problem slides | tokens in/out (k) |
|---|---|---|---|---|---|
| WP32 run 3 | 9/11 | 4 | 19 | 9 | 101/17 |
| WP33 | 10/11 (1 image id) | 3 | 21 | 9 | 102/13 |

All 14: 12/14 (one invented image id, `training_12` answered without a tool call), first call 3,
26 calls, 10 problem slides, 125k/18k (run 3: 12/14, 5, 24, 12, 126k/25k). One list split
(`many_items`: 9 cards over a 6-card slide → 5 + 4, delivered with the note); none of the 14
prompts sends an agenda over 8. No problem in either run was a count a split would have fixed but
did not: `quarterly_review`'s 6 figures over a 4-figure slide also had item headings the figures
slide cannot show, so it stayed `needs_revision` (the split needs each part to fit) with the
`trim`/`split` options; every other problem is a too-long label or cover subtitle (D22), untouched
by WP33. Edit turn: 12/12 delivered, first call 9, 15 calls all sent as `changes`, 82/88 earlier
slides kept identical, 88k/2k (run 3: 12/12, 9, 16 calls, 7 with `changes`, 75/93). Truncated,
lost, leftovers: 0. Run dir (not committed): `target/eval-wp33-small`.

**Unit evidence:** `test_assign.py` (a 9-entry agenda split 5 + 4 on one template slide before the
process fallback, the plan untouched, numbers continued `06`…`09` or kept as sent, steps numbered
from 6 needing no number zone while years still do, an unrequested kind split on its first inferred
kind, a list its kind holds never split, a text too long never split, bullets never split, the cap:
17 entries over 8 → close kind or `needs_revision` with the two-slide options, a split list never
asked for variety in either mode, a continuation kept on its first part's slide at max 1, other
slides on that template slide still counted); `test_table_slides.py` (22 rows → 11 + 11 with the
header on each, rendered; 60 rows still `needs_revision`); `test_build_tool.py` (a split agenda
counted once by the gap check, notes after a split on the plan's numbers); `test_deck_changes.py`
(the stored base is the plan as sent; a later `changes` numbered on it). Package `make
code-quality` clean (existing `builder_decks.py` `__all__` warning), `make test` 470 passed,
5 skipped; with `PPT_BUILDER_REFERENCE_TEMPLATE` on Paintress 475 passed.

**Recommendation: keep.** Turn 1 is at run 3's level within one-run noise (success +1, first call
−1, calls +2, same problem slides, fewer output tokens), the only split in the benchmark delivered
a deck that would otherwise have been trimmed or refused, and the live agenda case now builds on
its own agenda slide in one call. The benchmark rarely exercises overflowing lists; the
deterministic and unit evidence carry the feature.

## Results: WP34 ("What was built" beside the deck download, D25)

**Payload.** `PptPreviewPart.summary` (optional, `None` on `ppt_filler` parts): one entry per
rendered slide, `{number, part, parts, title, kind, template, notes: [{code, count?, kind?}]}`.
Recorded by the renderer as it builds each slide (`DeckReport.built`) and completed by the tool
with the pictures dropped before the assignment (`_summary`); nothing comes from the model's
reply. A 20-slide deck with one note per slide serialises to about 4.4 KB.

**Backend unit evidence:** `test_builder_render.py::test_the_user_summary_records_each_rendered_slide_and_what_changed`
(a cut text → `text_shortened`, title with inline Markdown stripped, template label; a picture
missing at render → `image_unusable` 1; items over the group → `items_left_out` 2);
`test_build_tool.py::test_the_delivered_part_summarises_what_was_built` (cover, a 6-entry agenda
split over two agenda slides → `(2, 1, 2)` and `(2, 2, 2)` titled `Agenda (1/2)` / `Agenda (2/2)`,
each with `list_continued`; a `timeline` slide built as `bullets` → `other_kind` with `timeline`;
a text document given as a picture → `image_unusable` 1 on its slide; no English prose in the
dumped summary; a `ppt_filler`-style part has `summary is None`). Package `make code-quality`
clean (existing `builder_decks.py` `__all__` warning), `make test` 472 passed, 5 skipped.

**Frontend evidence:** `DeckSummaryButton.test.tsx` with the real fr/en locale files (no button
without a summary or with an empty one; accessible name and `aria-haspopup`; the dialog lists the
4 slides with kind labels, the continuation wording on each part, the template label for an
untitled slide, `other_kind` with both kind labels, a plural count; an unknown code skipped;
French strings; every backend code has a wording in both locales);
`PptPreviewCardRenderer.test.tsx` (the card offers the button only with a summary).
`npx vitest run src/rework/features/capabilities/` 32 files, 276 passed; Help Center tests 18
passed; `npx tsc --noEmit -p .` clean; `prettier --check` and `eslint` clean on the touched files.
History replay: the summary is a field of the persisted part, read by the same card on replay.

Not covered: a manual check in the running app (the dialog was exercised in happy-dom only).

## Results: WP35 (live-session fixes)

Found in live session `2a1d9857-…`: the variety ask came back on turn 3 for slides delivered on
turn 1; a split made the file 14 slides for a 13-slide stored plan, so `changes` on the file's
numbers missed; a `replace` meant only to change the closing slide's text moved it to another
template slide; a `replace` arrived with its slide fields beside `op`.

**Root cause of the re-ask.** `CheckpointHygieneMiddleware` (first middleware of the platform
frame) passes the model request through `strip_message_names`, so every `ToolMessage` a capability
middleware sees has `name=None`; `deck_delivered` required `name == "build_presentation"` and never
matched, in any turn. Turn 2 escaped only because its first call failed on a slide number before
the assignment. Now matched by the `tool_call_id` of the `AIMessage` call naming the tool.

**Unit evidence:** `test_build_tool.py::test_a_deck_delivered_in_an_earlier_turn_is_seen_with_names_stripped`
(names cleared and block content, through the middleware: built, no ask; another tool's text: no
deck), `test_notes_after_a_split_name_the_files_slide_numbers` (agenda gap on slide 4 of the file),
`test_the_delivered_part_summarises_what_was_built` (numbers 1..5 with parts (2, 1, 2), (3, 2, 2)),
the description's `edit` sentence; `test_deck_changes.py::test_a_split_list_is_stored_as_the_delivered_deck`
(stored deck equals the rendered one, kinds set, a later edit of slide 4 neither splits nor
suffixes, parts identical), `test_a_text_replace_keeps_the_replaced_slides_design` (pinned section
variant kept on a text replace, a `quote` replacement reassigned),
`test_a_replacement_inherits_the_replaced_slides_template_slide`,
`test_a_new_slide_written_in_the_change_itself_is_read_as_its_slide`,
`test_slide_fields_beside_slides_or_on_another_op_say_where_they_go`,
`test_a_flattened_replace_is_built_as_its_slide`; `test_assign.py::test_a_delivered_split_rebuilds_as_it_was_and_still_counts_once`,
`test_a_delivered_slide_keeps_its_template_slide_while_it_fits_its_kind`,
`test_delivered_notes_name_the_files_slide_numbers`.

`.venv/bin/pytest -q tests/test_build_tool.py tests/test_deck_changes.py tests/test_assign.py`:
129 passed. Package `make code-quality` clean (existing `builder_decks.py` `__all__` warning),
`make test` 481 passed, 5 skipped (472 before WP35).

Not covered: a live re-run of the session's three turns; the frontend `types.ts` change is a doc
comment only (no frontend check run). A rebuilt stored split reports its parts as 1/1 in the
summary (no `list_continued` note on later builds).

## Results: WP36 ("same design as slide N", changes that change nothing)

Found in live session `a854d9b3-…`: bullets slides 4–7, the variety spreading put slide 5 on
template slide `slide:260` and slide 7 on `layout:18`. Asked "for slide 7, use the same layout as
slide 5", the model sent `edit` slide 7 `kind` = `bullets` and `edit` slide 7 `bullets` = the same
bullets: a no-op; the pin kept `layout:18`, the tool answered "Delivered" and the model told the
user it was done.

**Unit evidence** (`tests/test_deck_changes.py`):
`test_like_gives_a_slide_the_design_of_another` (the reproduction on the showcase template: slides
5 and 7 delivered on different template slides, `like` 5 rebuilds slide 7 on slide 5's, the stored
deck pins both on it, hidden fields cleared), `test_a_design_the_slide_cannot_take_is_a_revision`
(items on a bullets design: `needs_revision` "the slide does not fit slide 5's design…", the misfit
option and "or drop the `like` change"; a `quote` kind set in the same call: "holds 'bullets'
content, but the slide asks for kind 'quote'"), `test_bad_like_references_say_why_and_what_to_send`
(not a number, out of range, itself, removed target, second `like`, a plan never delivered),
`test_like_asks_for_the_referenced_slides_delivered_design` (resolved against the base when the
referenced slide is replaced in the same call; `like` shorthand; on a replaced slide; kind kept
when the call sets it), `test_a_design_asked_for_is_never_a_variety_ask` (five slides asked on one
design at max 1: all on it, no repeat), `test_changes_that_leave_the_deck_as_is_build_nothing`
(the session's exact no-op, an identical replace, a `like` on the design already held: error
"No deck was built: nothing changed", no render, write or store; a new file name still builds).
`test_change_slides_do_not_repeat_the_slide_schema` still holds the `changes` schema under 1600
chars with the `like` text.

`.venv/bin/pytest -q tests/test_build_tool.py tests/test_deck_changes.py tests/test_assign.py`:
135 passed. Package `make code-quality` clean (existing `builder_decks.py` `__all__` warning),
`make test` 487 passed, 5 skipped (481 before WP36).

Not covered: a live re-run of the session with a real model (whether it picks `like` from the
description); a `like` on a slide whose referenced design was removed from the template after
delivery is handled (`needs_revision`) but untested.

## Results: WP37 (designs named in the delivered message)

Same session `a854d9b3-…`: asked "for slide 7, use the same layout as slide 5", the model saw two
bullets slides and answered they were already the same, without a call. The success text now ends
its first paragraph with one line; on the showcase template (cover, a 5-step process split 3 + 2,
an agenda, three bullets slides):

`Designs: 1 'Title Slide' · 2 'Process' · 3 'Process' · 4 'Agenda' · 5 'Title and Content (11)' ·
6 'Silent notes' · 7 'Free text'. Slides with different names look different; to give slide N the
design of slide M, send {"op": "edit", "slide": N, "field": "like", "value": M}.`

**Unit evidence** (`tests/test_build_tool.py`):
`test_the_delivered_text_names_each_file_slides_design` (file numbers with the split process list,
three bullets slides on three template slides read as three names, the `like` sentence, no
template id), `test_two_template_slides_sharing_a_label_get_distinct_names` (`slide:269` relabelled
'Free text': `'Free text'` and `'Free text #2'`), `test_a_long_design_name_is_cut` (cut to 28 chars
with "…"). The tool description is unchanged (its `like` guidance already fits); no size budget
applies to the success text.

`.venv/bin/pytest -q tests/test_build_tool.py tests/test_deck_changes.py tests/test_assign.py`:
138 passed. Package `make code-quality` clean (existing `builder_decks.py` `__all__` warning),
`make test` 490 passed, 5 skipped (487 before WP37).

Not covered: a live re-run of the session with a real model (whether it now answers "same layout"
with `like`); the `#2` suffix is shown to the model only, so the review and summary dialog still
show two identical labels for those template slides.

## Results: WP38 (review fixes)

| Finding | Fix | Evidence |
| --- | --- | --- |
| A refused plan became the next turn's base | Only a delivered deck is written to `cap_ppt_builder_deck_plan`; a refused plan stays the turn's in-memory base | `test_a_refused_plan_is_never_the_next_turns_base`, `test_the_same_changes_resent_are_never_applied_twice` (store empty) |
| Corrected-resend rule fired after a delivery | A delivery clears the parent and shape | `test_the_same_changes_after_a_delivery_are_a_new_change` (insert A, insert B: both present) |
| Model could set hidden fields | `_sent` drops `HIDDEN_FIELDS` from every sent slide | `test_design_fields_sent_by_the_model_are_ignored` |
| Pin ignored after a kind substitution | `_kept` keeps the pin whenever it is among the best-ranked kind's fits | `test_a_substituted_kind_keeps_its_template_slide` |
| One cut name for two designs | Duplicates counted on the shown label | `test_a_long_design_name_is_cut` |
| Variety ask re-fired with a trimmed history | Never asked when the call has a base | `test_a_change_to_a_delivered_deck_is_never_asked_to_vary` |
| Continuation numbers frozen in the stored deck | Numbered at render from `Assignment.starts` | `test_a_continuation_is_numbered_at_render_from_its_first_part`, `test_items_without_numbers_continue_the_count_on_the_second_slide` |
| A malformed call used up the variety ask | `called` set after the assignment | `test_a_malformed_first_call_does_not_use_up_the_variety_ask` |
| `RenderResult.warnings` only fed a log line | Deleted; render tests read `DeckReport` through `_issue_line` | `tests/test_builder_render.py` (`_findings`) |
| Info button larger than its neighbours, gap between them | `size="small"`; gapless `.tools` group in card and pane headers | `DeckSummaryButton.test.tsx` (`btn-small`) |

The new tests for findings 2, 3, 4 and 9 were also run against the code before their fix and failed there.

Commands (package root `libs/capabilities/fred-capability-ppt-filler`):
`.venv/bin/pytest -q tests/test_build_tool.py tests/test_deck_changes.py tests/test_assign.py`:
144 passed. `make code-quality` clean (existing `builder_decks.py` `__all__` warning).
`make test`: 496 passed, 5 skipped (490 before WP38).

Frontend (`apps/frontend`, node from fnm, no make target): `npx tsc --noEmit -p .` clean;
`npx prettier --check` on the six touched files clean; `npx eslint` on the three touched `.tsx`
clean; `npx vitest run src/rework/features/capabilities/ppt_filler`: 7 files, 49 tests passed.

Not covered: a live re-run with a real model; the gapless header group (CSS) has no automated
check; a refused plan from before this change still in the table can be read as a base once (it
is not `delivered`, so the "nothing changed" check skips it).

## Results: WP39 (live-session fixes: kind edit, drop options, identical resends)

Session `b9e7ec4d`: slide 10 (`bullets`) edited to `two_columns` with columns, its bullets left; twelve `needs_revision` (`drop bullets`), mostly identical calls; the thirteenth blocked by the turn's tool-call cap (12) and shown as the runtime's generic failure.

| Finding | Fix | Evidence |
| --- | --- | --- |
| A kind edit kept fields the new kind cannot show | Cleared unless the call sets them; noted in the result | `test_a_kind_edit_clears_the_fields_the_new_kind_cannot_hold` (the session's three edits), `test_a_kind_edit_keeps_what_the_same_call_sets_and_what_the_kind_holds` |
| `drop bullets` gave no way to drop | The exact `edit` in `changes` mode | `test_a_drop_option_gives_its_exact_change` |
| The same refused call resent until the cap | Answered without evaluation, `replace` suggested | `test_a_call_identical_to_a_refused_one_is_not_evaluated_again` |

Commands (package root `libs/capabilities/fred-capability-ppt-filler`): `make code-quality`
clean (existing `builder_decks.py` `__all__` warning); `make test`: 500 passed, 5 skipped
(496 before WP39). `openspec validate ppt-builder-capability` valid.

Not covered: a live re-run with a real model; the runtime's cap message (no runtime change).


## Results: WP40 (live-session fixes: parallel fragments, fragment remedy, identical resend)

Session `028c5af3` (`mistral-small`): one deck sent as several different `build_presentation` calls in one round; cover+agenda delivered, the fragments refused with "add a cover slide before it", which led to more splitting; later the delivered deck resent as is and rebuilt (~14 s, one of the 12 tool calls).

| Finding | Fix | Evidence |
| --- | --- | --- |
| Fragments of one deck sent in parallel | The middleware runs the first call of the assistant message, refuses the others before the tool | `test_parallel_build_calls_of_one_round_build_only_the_first` (three fragments gathered, one write, exact refusal), `test_a_single_build_call_or_a_copy_in_parallel_is_handled_once` |
| "Add a cover slide before it" after a delivery | Only option: `changes` (`insert` after N, `replace`) | `test_a_fragment_after_a_delivered_deck_is_pointed_to_changes` (both option lists) |
| The delivered deck resent and rebuilt | "unchanged, deck already delivered as '<file>'", no render/upload/preview | `test_resending_the_delivered_deck_rebuilds_nothing` (render counter unchanged, one write), `test_a_parallel_copy_of_a_call_is_not_built_twice` (updated: the copy answered as unchanged) |

Commands (package root `libs/capabilities/fred-capability-ppt-filler`): `make test`: 608 passed,
5 skipped; `ruff check`, `ruff check --select I`, `ruff format --check` clean; `basedpyright
--baseline-file .baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py`
`__all__` warning). `openspec validate ppt-builder-capability --strict` valid.

Not covered: a live re-run with a real model; agent loops that do not run the capability
middleware (none expose `ppt_builder` today).


## Results: WP41 (live-session fixes: revisions are not errors, the next call, parallel sections)

Session `a9429766` (`mistral-medium`): a 14-slide deck with 4 charts got a variety `needs_revision` (Italy and Spain sections mirroring each other: figures at 4/8, timeline at 6/10). Returned as `is_error`, it made the runtime count a failed call; the model planned the fix, ended the turn without the call, and its answer was replaced by the raw revision text and JSON.

| Finding | Fix | Evidence |
| --- | --- | --- |
| A revision was a failed tool call | `_answer` (non-error) for fit/variety `needs_revision`, identical resend, round refusal, nothing changed, already delivered; `_error` kept for real failures | `test_a_slide_that_fits_nothing_builds_nothing_and_says_what_to_change` (`not is_error`, block text = result text), `test_the_first_deck_is_asked_to_vary_once_and_a_resend_is_built`, `test_each_variety_check_mode_asks_for_its_own_repeat`, `test_parallel_build_calls_of_one_round_build_only_the_first`, `test_a_call_identical_to_a_refused_one_is_not_evaluated_again` (loop breaker: one evaluation, not an error), `test_changes_that_leave_the_deck_as_is_build_nothing`, `test_resending_the_delivered_deck_rebuilds_nothing`; still errors: `test_empty_plan_is_an_error_the_user_can_read`, `test_no_base_both_modes_and_bad_changes_build_nothing` |
| The turn ended after a revision | Revision texts and working rules require the next message to be the fixed call | the fit and variety texts above; `test_builder_capability.py` system-prompt assertion |
| Alternatives the content cannot fill | Framed-picture template slides never offered to slides without an image | `test_variety_never_offers_a_variant_needing_pictures_the_slides_lack`, `test_a_fit_remedy_never_names_a_kind_needing_a_missing_picture` |
| Parallel sections asked to vary | Mirrored places counted once in the ask and the beam | `test_parallel_sections_repeating_one_structure_are_not_a_repeat`, `test_a_repetition_inside_one_section_is_still_a_repeat`, `test_an_agenda_splits_the_deck_into_sections_without_section_slides` |

Commands (package root `libs/capabilities/fred-capability-ppt-filler`): `make test`: 630 passed,
5 skipped (625 before WP41, 5 tests added); `ruff check`, `ruff check --select I`, `ruff format
--check` clean; `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors
(existing `builder_decks.py` `__all__` warning). `openspec validate ppt-builder-capability
--strict` and `openspec validate ppt-builder-charts --strict` valid. Frontend untouched: no
`ppt_builder` component reads the tool error flag.

Not covered: a live re-run with a real model; the runtime's own handling of error results
(`libs/fred-runtime` untouched).

## Results: WP42 (the variety limit per section, `repeat_layout`)

Owner decision 2026-10-14: the per-template-slide limit counts within each section, a later section may reuse an earlier one's slides in any order, and identical slides in a row are made only when the user asks (D27, rewritten).

| Rule | Evidence |
| --- | --- |
| Limit per section, counts reset | `test_the_limit_counts_within_each_section` (Italy at 2/4, Spain at 1/3, cap 2: no ask, Spain keeps the same designs; flat: slides 2, 4, 5, 7 asked), `test_three_uses_inside_one_section_are_still_revised` (slides 2, 4, 6, `at_most` 2), `test_an_agenda_splits_the_deck_into_sections_without_section_slides` (unchanged) |
| No three in a row, across a boundary | `test_three_identical_slides_in_a_row_are_revised_across_sections` (agenda sections, slides 3–5, `in_a_row`), `test_repetition_is_allowed_and_reported_on_a_one_archetype_template` (run note; off mode keeps the old note), `test_no_three_identical_slides_in_a_row_when_an_alternative_fits` (unchanged) |
| `repeat_layout` | `test_identical_slides_the_user_asked_for_are_built_and_noted`, `test_repeat_layout_keeps_the_previous_template_slide_outside_the_cap`, `test_repeat_layout_the_content_cannot_keep_is_noted`, `test_repeat_layout_is_an_edit_with_loose_names_and_values`, `test_the_delivered_part_summarises_what_was_built` (summary codes); frontend `DeckSummaryButton.test.tsx` (fr/en wording for every code) |
| Wording | `test_the_choice_guide_states_the_authors_max`, `test_the_first_deck_is_asked_to_vary_once_and_a_resend_is_built` (the section rule in the ask) |

Commands (package root `libs/capabilities/fred-capability-ppt-filler`): `make test`: 635 passed,
5 skipped (630 before WP42: 2 tests of the mirrored rule removed, 7 added); `ruff check`, `ruff
check --select I`, `ruff format --check` clean; `basedpyright --baseline-file
.baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py` `__all__` warning).
Frontend (`apps/frontend`): `npx tsc --noEmit -p .` clean; `npx vitest run
src/rework/features/capabilities/ppt_builder src/rework/features/capabilities/ppt_filler
src/rework/features/helpCenter`: 15 files, 108 tests passed; prettier and eslint clean on the
touched files. `openspec validate ppt-builder-capability --strict` valid.

Not covered: a live re-run with a real model.

## Results: WP43 (library slides excluded, D28)

Owner decision 2026-10-14: a library slide is never a design; reusing its icons is a later change.

| Rule | Evidence |
| --- | --- |
| Icon and fonts sheets excluded as `library`; four icons beside text, a row of 24 preset dots and a "Thank you" asking for attribution kept | `test_library_slides_are_excluded_and_designs_with_icons_kept` (synthetic deck, `build_library_template`) |
| Resource-page titles, not "Human resources" nor "3 icônes + texte" | `test_library_titles` (11 cases) |
| The former icon bank is a library slide | `test_library_chart_and_table_are_excluded_by_default`, the showcase summary test |

Owner templates (read-only copies of the stored `.pptx`, analysed locally at version 13):

- Paintress Cyan (Slidesgo, 32 slides): before, only three table slides (12, 22, 24) excluded; `Fonts` (cards), `Nature`/`Educational`/`Business`/`Help & support`/`SEO & marketing icons` (section), `Creative process icons` (process) and the instructions pages were designs. After, 16 slides excluded as `library`: 2 `Contents of this template`, 15-16 `Instructions for use`, 17 `Fonts`, 18 `Presentation Maker`, 19 `Use our editable graphic resources...`, 25-31 icon sheets (51 to 100 icons each). Slide 14 `Thank you` stays `closing`; slides 1-13 keep their kinds. Summary: 22 patterns, 21 excluded.
- The second stored template (37 slides): slides 29-33 (`Base d'icônes`) move from `icon_bank` to `library`; `3 icônes + texte` and `6 icônes + texte` stay `cards` designs; nothing else changes.

Commands (package root): `make test`: 691 passed, 5 skipped; `ruff check`, `ruff check --select I`, `ruff format --check` clean; `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py` `__all__` warning). `make builtin-inventory` (version bump only). `openspec validate ppt-builder-capability --strict` valid.

Frontend client (43.2, commit 2a1f39b92): `cd apps/frontend && make update-ppt-builder-capability-api`; only `pptBuilderCapabilityOpenApi.ts` changed (`library` added to `exclusion_reason`).

Not covered: Slidesgo's untitled resource pages (infographics, maps; Paintress 20-24, 32) stay `other`, not reusable, so never chosen, but are not marked `library`.

## Results: WP44 (a list over its zone's entry limit says so)

Live case: "the 'bullets' slide does not fit (bullets: 3 entries, 59 chars; this zone holds ≤14 words (≈101 chars) (longest: bullets[2], 21 chars)) [...] keep bullets within ≤14 words (≈101 chars): shorten or drop entries". The zone has 1 line, so at most 1 entry fits (each entry a paragraph, `floor(1 / 0.7)`); the agent shortened instead of merging. Replayed on the stored template inventory, the same slide now reads "bullets: 3 entries; this zone holds 1 line (≈101 chars): at most 1 entry", option "merge bullets into at most 1 entry, or use another kind"; the 2-line variants read "at most 2 entries".

| Rule | Evidence |
| --- | --- |
| Entry count over the limit named, not chars (1-line, 2-line, a column) | `test_too_many_entries_for_a_one_line_zone_name_the_entry_limit_not_chars`, `test_too_many_entries_for_a_two_line_zone`, `test_too_many_column_entries_name_the_column_list` |
| Count fits, entries wrap: lines taken vs held | `test_entries_few_enough_but_too_long_get_a_length_message`; the two `999 chars` misfit tests updated |
| Description quotes lines and max entries | `test_a_list_field_room_quotes_its_lines_and_entry_limit`; the variety-note tests updated |

The five new tests fail on the previous code (old message, no entry limit in the description). Commands (package root): `make test`: 696 passed, 5 skipped; `ruff check`, `ruff check --select I`, `ruff format --check` clean; `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py` `__all__` warning). `openspec validate ppt-builder-capability --strict` valid.

Not covered: a live re-run with a real model.

## Results: WP45 (a re-run's new analysis reaches the review dialog)

Live case: after "Re-run analysis" on an outdated analysis the dialog kept the old inventory. The status answered `succeeded`, `current: true` with the old inventory during the refresh, and the form polls only `pending`/`running`: its last GET came before the refresh ended, none after.

| Rule | Evidence |
| --- | --- |
| `refreshing` during a refresh, false after it and after a failed one | `test_an_outdated_analysis_stays_ready_and_is_refreshed_once`, `test_a_failed_refresh_keeps_the_old_analysis_and_is_not_retried` (asserts added) |
| Re-run route answers `refreshing: true`, then false with the new version | `test_rerun_restarts_a_failed_or_interrupted_analysis_only` |
| The form polls while refreshing and swaps in the new inventory | `polls an outdated analysis while it is refreshed, then shows the new inventory` (usePptBuilderAnalysis.test.tsx) |
| Status line while refreshing, no re-run button | `says an outdated analysis is being read again while it is refreshed` |
| Excluded section unfolded for analysis exclusions, folded for author-only | PatternReviewDialog.test.tsx section tests |
| Analysis reason kept under an author exclusion | `keeps the analysis' reason when the author excludes a slide it already set aside` |

Commands: package `make test`: 696 passed, 5 skipped; `ruff check`, `--select I`, `format --check` clean; basedpyright on `analysis_job.py`: 0 errors. Frontend (no make target): `tsc --noEmit` clean, prettier and eslint clean on touched files, `vitest run` on the ppt_builder folder: 6 files, 43 tests passed.

Not covered: a live re-run in the browser.

## Results: WP46 (heuristic kinds for Google Slides exports)

Why vision did not label Paintress Cyan (and Paintress): both agents have `use_vision: true`, `labelling_model: chat.mistral.medium`, and vision did label Cyan at its creation (2026-10-14 15:29 UTC, 30/31 slides). The stored rows carry `labelling_key = rules` because the version-13 refresh was started from the form's "Re-run analysis" (`POST /analysis/{id}/rerun`, 16:21 UTC) after a fred-agents restart: that route has no save context, the per-process model port cache was empty, so `run_analysis` ran with no port and stored `rules` (Paintress's row was already `rules` when a chat turn refreshed it at 16:27). A save with the port (or a restart-free re-run) relabels. The heuristics below make the rules result usable on their own.

Synthetic Google-style deck, old rules → new: cards slide `cover` → `cards` 3×[heading, body]; two ideas `cover` → `two_columns` (heading, body ×2); big figures `cover` → `figures` 2×[number, label]; big number `cover` → `figures` 1 item; numbered grid `cover` → `cards` 6×[number, body]; staircase `bullets` → `timeline` 5×[number, body]; paragraph subtitle `cover` → `bullets`; graphic sheet and promo `other` → excluded `library`; empty slide stays `other`.

| Rule | Evidence |
| --- | --- |
| TITLE/SUBTITLE pairs become cards | `test_repeated_title_subtitle_pairs_are_cards` |
| Two pairs stay headed columns | `test_two_stacked_pairs_are_headed_columns` |
| Figures paired with the caption in their column, `label` role | `test_big_figures_pair_with_the_caption_in_their_column` |
| Lone big number | `test_a_lone_big_number_is_a_one_item_figures_slide` |
| Numbered grid is cards, not process | `test_numbered_texts_on_a_grid_are_cards_not_a_process`; `test_pairing_leaves_the_existing_designs_alone` (process kept) |
| Staircase of dates, left to right; reused entry kept | `test_a_staircase_of_dates_is_a_timeline_read_left_to_right` |
| Paragraph subtitle is a body | `test_a_paragraph_sized_subtitle_is_a_body_not_a_cover` |
| Graphic sheet and promo are `library`, empty slide not | `test_text_free_graphic_and_promo_slides_are_library` |
| Figure lexicon | `test_figures_lexicon` |

Per-template classification, HEAD rules vs new (every pattern compared):

- Paintress Cyan: `Three ideas` cover → cards 3×[heading, body]; `Six different ideas` cover → cards 6×[number, body]; `333,000` cover → figures 2×[number, label]; layout `BIG_NUMBER` cover → figures 1 item; `Let's have a look` cover → bullets (body); `Our history` bullets → timeline 5×[number, body]; `Two ideas` stays two_columns with heading/body roles instead of four subtitles; `Table of contents` stays agenda, now 8×[number, heading]; slides 20, 21, 23, 32 `other` → excluded `library`. Excluded slides 2, 12, 15-17 only change zones.
- Paintress, the built-in Fred template and the corporate reference deck: no change (kinds, zones, groups, exclusions identical). The built-in inventory changes only by its version (`make builtin-inventory`).

Render evidence (no LLM, `assign` then `render_deck` on the Cyan template; a Thales Italy/Spain plan: cover, agenda, two bullets, figures, cards, timeline, two columns, closing). Old rules: four problems ("no 'figures' / 'cards' / 'timeline' slide", "columns: 2 given, max 0"), then once rewritten as bullets every list falls back to `image_text`/`two_columns` ("at most 1 entry"). New rules: one problem (the figures slide has no title zone, "drop title"), then every slide on its kind: agenda 4 of 8 entries, cards, staircase timeline, headed columns. PDFs: `scratchpad/charts-evidence/cyan-classification.pdf` (new), `cyan-classification-before.pdf` (old).

Commands (package root): `make test`: 713 passed, 5 skipped; `ruff check`, `ruff check --select I`, `ruff format --check` clean; `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py` `__all__` warning). `openspec validate ppt-builder-capability --strict` valid. The reference-template tests fail on Paintress and the corporate deck before and after alike (they expect a `chart` exclusion neither holds).

Not covered: the vision run itself; the 1-line capacity of Cyan's timeline texts; Cyan's figures slide has no title zone.

## Results: WP47 (re-runs go through the save)

Root cause of the rules labelling seen in WP46: the model port only reaches the capability on a save (`_build_capability_save_services`, fred-runtime) and is cached per process (`analysis_job._ports`). The re-run route had no save context, and turns and readiness checks carry no port either, so after a restart `run_analysis` ran without one and stored `rules`. The route is deleted; the form tells the author to save, and a save re-runs failed, interrupted and outdated analyses with the port it carries.

| Rule | Evidence |
| --- | --- |
| A save after a restart re-runs failed and outdated vision analyses with the port | `test_a_save_after_a_restart_reruns_with_vision` |
| An interrupted vision analysis is not recovered without the port; a save relabels it | `test_an_interrupted_vision_analysis_waits_for_a_save_without_the_port` |
| A vision job without a port warns and stores `rules` | `test_a_vision_job_without_the_port_stores_rules_and_warns` |
| Rules-labelled interrupted analyses still recover on readiness | `test_interrupted_analysis_is_reported_and_recovered` |
| No re-run route, editors still gated on status and thumbnails | `test_a_non_editor_is_refused_everywhere` |
| The status line has no button; the outdated hint says to save | `shows the error and no action of its own: a save re-runs the analysis`, `tells the author a save refreshes an outdated analysis` |

Commands: package `make test`: 713 passed, 5 skipped; `ruff check`, `--select I`, `format --check` clean; `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors (existing `builder_decks.py` warning). Client regenerated with `make update-ppt-builder-capability-api` (the rerun mutation removed). Frontend (no make target): `tsc --noEmit` clean, prettier and eslint clean on touched files, `vitest run` on the ppt_builder folder: 6 files, 42 tests passed. `openspec validate ppt-builder-capability --strict` valid.

Not covered: a live save-based re-run in the browser.

## Results: WP48 (the preparing banner says what is being prepared)

Path chosen: a frontend locale key per capability, `capability.<id>.preparing`, like the manifest's `capability.<id>.name`. `CapabilityReadiness.pending()` was not given a detail: `suspension_detail` being null is how the listing re-check and the UI tell pending from failed, and which capability is pending is not stored, so carrying it would need a new column and a contract change. The text is shown only when exactly one of the agent's capabilities declares a key; otherwise the generic text. No backend, OpenAPI or frozen-contract change.

| Rule | Evidence |
| --- | --- |
| One declaring capability gives its key; a deselected slice is ignored; two or none give nothing | `capabilityPreparingKey` (3 tests) |
| The card names the pending work, else falls back to the generic text; a failure still shows its message | `AgentCard capability readiness` (4 tests) |

Commands (apps/frontend, no make target): `tsc --noEmit` clean; prettier and eslint clean on touched files (locales and Help Center pages included); `vitest run` on the helper, `AgentCard` and the `AgentFormModal` folder: 14 files, 136 tests passed. fred-sdk `ruff check` / `ruff format --check` clean on the docstring change. `openspec validate ppt-builder-capability --strict` valid.

Not covered: the banner and the form message in the browser.

## Results: built-in deck swap (task 7.1, 2026-10-16)

Deck: the owner's `fred-default-showcase.pptx` (45 slides, "Fred …" layouts). Owner decision A: `ppt/slides/slide33.xml` ("Fred Table") rewritten by a one-off lxml script, every other part copied byte for byte: header row kept, the 18 body cells (6 rows × 3 columns) emptied, each keeping its `tcPr` and an `a:endParaRPr sz="1400" b="0"` (the run's properties, as in `ppt-builder-builtin-table-slide` D2). Saved as `fred-default-showcase-table-vide.pptx` beside the original, then copied over `assets/fred_template.pptx`; `make builtin-inventory`. Decision B: `ppt-builder-kicker-label`.

| Kind offered | Built-in slide(s) |
| --- | --- |
| cover | Fred Title (slide 1) |
| agenda / section | Fred Agenda; Fred Section ×4, Title Only layouts |
| bullets, two_columns, comparison, cards | Title and Content…; Two Content, Code; Comparison, Before After; Three Columns, Four/Six Cards, Three Images, Matrix |
| quote, image_text | Fred Quote ×2; Title Image, Content with Image, Image Left, Full Image, Two Images, Screenshot |
| timeline, process, team | Fred Timeline; Process ×2; Team |
| table | Fred Table (3 columns, header + ≈6 lines) |
| chart | Fred Chart (takeaway card), Chart Full (caption), Two Charts, Chart and Figures |
| figures, closing | Key Figures ×2; Closing ×2 |

Assignment fix found by the swap (commit `fix(#2679): count a list left without items…`): "Fred Chart and Figures" (chart + a two-figure list) won every bare chart, because a list given no items counted no empty zone in `_weigh`, and the render then removed the list with a `left_empty` note. A list left without items now counts its zones as unfilled (`_EMPTY_ZONE` each). Test: `test_a_chart_without_items_avoids_the_slide_whose_list_would_stay_empty` (fails without the fix); the old deck's suite was unchanged by it.

Test expectations changed as consequences of the deck only: pattern ids and names (`slide:266` → `slide:288` table, "Fred Chart Wide" → "Fred Chart Full" with its caption body, two more chart slides), the table's 3 columns (two-offer comparison, 10-row continuation, "4 columns given, max 3"), the example chart's design (no series colour, literal gridlines `E3E5EF`, plot-wide value labels; a fresh chart checked with an area chart, the style-part test's second chart a line for the full slide's example), takeaway and figure placeholders found by their layout names, the full chart slide's caption taking the bullet when the card shows the takeaway (told, `intent_not_shown`), the figures slide holding 4, no chart-capable content placeholder, and a section list added in the test (the deck has none).

Commands: package `make test`: 890 passed, 5 skipped; `ruff check`, `--select I`, `format --check` clean; basedpyright with baseline 0 errors. Preview: a 16-slide showcase built in process on the new deck and converted by LibreOffice, `~/fred-tmp/builtin-new/showcase-built.pdf`.

Seen in the preview, not fixed (owner to decide):
- A `section` plan lands on a quote slide: the section slides' `section_number` body ("01", 88 pt) sits before the title and takes the subtitle, which misfits.
- An `agenda` with items lands on a process slide: Fred Agenda holds one body, no list.
- Timeline dates are top-level bodies outside the milestone list: items' `number` has no place (dates fit as headings); 4 items leave the fifth dot drawn.
- Four Cards with 3 items keeps the fourth card's box (decoration) empty.
- Statement and Big Number slides stay `bullets` (kicker change Follow-ups).
- The table is 3 columns: a 4-offer comparison (5 columns) now gets `needs_revision`; the old deck had 5.

## Results: built-in deck v3 and unused-item decoration (WP49, 2026-10-17)

Deck: `fred-default-v3.pptx` (beside the owner's files; v1 and v2 kept as iterations), derived from `fred-default-showcase-table-vide.pptx` by an lxml script that rewrites only the slides, layouts and notes it edits. Same 45 slides, colours, fonts and pictures.

| Iteration | Changed | Seen in the showcase PDF |
| --- | --- | --- |
| v1 | agenda list, section names, timeline dates, 5-column table, statements as quotes, KPI samples, item heights, cover/process/other notes; render lifts layout decoration | agenda, section, timeline 3/4/5, table and four cards right; a numbered tile left over a removed column; empty takeaway cards beside bare charts |
| v2 | marks and connectors follow their item; takeaway card as the zone's fill; Three Images items carry their picture | LibreOffice draws a filled layout placeholder the slide left out (prompt text in an empty card) |
| v3 | the fill on the slide's zone only; chart captions kept (a bullet beside a shown takeaway still has a place) | no empty box, orphan decoration, leftover example text or overflow |

Kinds and slides offered (rules analysis): cover ×3 (Title, Title Image, Title Light), agenda (7 entries), section ×4 (+2 title-only layouts), bullets, two_columns, comparison ×2, cards ×6 (Three Columns, Four, Six, Three Images, Matrix with takeaway), quote ×4 (Quote, Quote Image, Statement, Statement Accent), image_text ×5, figures ×2 (3 and 4, trend arrows), process ×3 (4 steps, 3 arrows, 4-step dark flow), timeline (5), team (photos), table (5 columns × 8 rows), chart ×4 (takeaway card, full, two charts, chart with two figures), closing ×2. Set aside: Code, Big Number, blanks, the palette sheet.

| Rule | Evidence |
| --- | --- |
| Frame, mark and connector fates | `test_item_decoration.py` (4 unit tests) |
| Four Cards with 3 items: 3 cards, 3 tiles, master marks and slide number kept; all 4 used: layout untouched | `test_cards_drawn_on_the_layout_leave_with_their_unused_item`, `test_a_full_set_of_items_leaves_the_layout_as_it_is` |
| Timeline: dates in the items, 4 dots and the line for 4 milestones | `test_a_timeline_keeps_a_dot_per_milestone_and_each_date_in_its_item` |
| Process with 3 steps: the layout's tiles 1–3 on the slide, no "4" | `test_builtin_process_with_three_steps_drops_the_fourth` |

Test expectations changed for the deck only: 5 table columns ("2 to 5 columns"), the continuation test at 16 rows (10 now fit), "6 columns given, max 5", and the process slide's lifted step numbers. A pre-existing basedpyright error in `test_chart_slides.py` (a `str` role) typed. The secrets baseline takes the new template digest.

Commands: package `make code-quality` clean (basedpyright 0 errors); `make test`: 897 passed, 5 skipped. Showcase: three decks built in process through `build_presentation` (57 slides), `~/fred-tmp/default-template/v3/showcase-v3.pdf`.

Remaining, recommended, not done: a big number beside a title is no one-item `figures` slide (`_lone_figure` takes exactly two shapes, so the slide is set aside); a section's number zone is never filled (left out); a filled picture placeholder (cover image, team photo) is fitted inside its box rather than cropped to its shape; a bare chart alternates between the full-width slide and the takeaway slide with its card removed.

## WP50 (2026-10-17): section numbers, cropped pictures, team photos recentred once

`tests/test_section_and_picture_fill.py`, all four failing on the code before and passing after: sections numbered 01, 07 (given), 03; four wide team photos cropped 25 % each side, no geometry of their own (the layout's ellipse), alt text kept; cover and image_text pictures fill their frames at the picture's aspect ratio; three team photos each centred on its name (before: off by 1 421 091 EMU, moved twice). `test_deck_changes.py`: the slide field list names `number`.

Showcase re-rendered on the built-in template (`~/fred-tmp/default-template/v3-fixes/`, PNG looked at): sections 01/02/03 with the title under the number, section image, cover image, image_text and Two/Three Images pictures filling their frames, team photos round, centred on their names.

Commands: package `make code-quality` clean (ruff, `--select I`, format, bandit, detect-secrets; basedpyright 0 errors, the pre-existing `builder_decks.py` warning); `make test`: 903 passed, 5 skipped; `openspec validate --strict` on the three changes.

Not proven: PowerPoint's rendering of the crop (LibreOffice only); a template whose image zone is a plain shape (picture over its box with the shape's preset geometry, not tested).
