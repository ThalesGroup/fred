# Verification: ppt-builder-capability

Evidence for WP9, WP11 and WP12 (design D11). Run on 2026-10-05 on a developer laptop. This is
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
  - `builtin`: the interim built-in theme (`theme.py`, deleted in WP7), rules only.

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
