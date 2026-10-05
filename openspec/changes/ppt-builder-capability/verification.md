# Verification: ppt-builder-capability

Evidence for WP9 (design D11). Run on 2026-10-05 on a developer laptop. This is
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
  - `builtin`: the interim built-in theme (`theme.py`), rules only.

Two full matrices: **run 1** before the kind-enum fix below, **run 2** after it.
One run per cell: an LLM at temperature 0 still varies between runs, so read
single-cell differences as noise.

## Results

Run 2 (current code):

| template | mode | runs | success | avg repairs | cover once@1 | 3-in-a-row | distinct/slides | leftovers | truncated | lost | avg wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| builtin | rules | 10 | 10 | 1.2 | 100% | 2 | 0.72 | 0 | 0 | 0 | 23 |
| corporate | rules | 10 | 9 | 1.8 | 100% | 0 | 0.74 | 0 | 0 | 0 | 35 |
| corporate | vision | 10 | 7 | 1.5 | 100% | 0 | 0.75 | 0 | 0 | 0 | 29 |
| prism | rules | 10 | 10 | 1.8 | n/a (no cover) | 0 | 0.36 | 0 | 0 | 0 | 69 |
| prism | vision | 10 | 7 | 1.7 | 100% | 36 | 0.30 | 0 | 0 | 0 | 55 |

Run 1: 49/50 successful, same cover/closing results, distinct/slides 0.68
(builtin), 0.70 / 0.76 (corporate rules / vision), 0.34 / 0.31 (prism).

Analysis: corporate vision labelling 44-47 s for 20 slides (20/20 labelled); prism
72-74 s (7/8 labelled, one invalid answer kept its heuristic label). Rules only:
about 1 s.

## Targets

| Target | Result |
|---|---|
| Cover exactly once at slide 1 in 100% of successful decks | **Met**: 72/72 successful decks on templates with a cover (prism rules finds no cover) |
| Closing at most once and last | **Met**: 92/92 |
| Zero 3-in-a-row | **Met on corporate** (0 in run 2, 1 in run 1). **Missed on prism** (36) and builtin (2): the assigner allows a repeat only when no other slide fits (and says so to the agent); prism has a single usable `bullets` slide and no usable layout |
| distinct/slides ≥ 0.5 on rich templates | **Met**: corporate 0.70-0.76; builtin 0.68-0.72. Prism (0.30-0.36) is not a rich template |
| Zero leftover template text | **Met**: 0 in both runs. Run 1 showed 7, all step numbers ("1", "2"…) the renderer writes and that equal the samples: a metric false positive, now excluded |
| Success after repairs | 92/100 (run 1 49/50, run 2 43/50). No failure produced a wrong deck: each one ended on `needs_revision` |
| Average repairs | 1.5 per successful run. Only 10/100 runs succeeded on the first call |

Truncation and lost content are 0 everywhere: the fit check refuses a slide
whose text would need a cut, so it shows up as repairs instead.

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

## Notable failures and diagnosis

- **Repair loops that do not converge** (7 of 8 failures): the model resends the
  same plan. Examples: "comparison slide: no place for column 3" three times in a
  row; "cards slide: bullets too long (≤19 chars)" repeated 7 times without saying
  which bullet. The problem text does not name the offending entry, and the
  options are sometimes generic. Proposed follow-up: give the index of the too-long
  bullet or item and its length, and group repeated reasons.
- **Prism vision labels disagree with the slots**: the slide labelled `cover`
  holds only a slot read as `columns.heading` ("a 'cover' slide takes:
  columns.heading"), and the `bullets` slide has no bullets slot ("closest
  'bullets' slide: no place for bullets"). Vision decides the kind, geometry
  decides the slots, and nothing checks that they agree. Proposed follow-up: after
  the merge, check that the kind fits its slots (cover needs a title, bullets
  needs a body), or let the author fix it in the review panel.
- **Most repairs come from content shape, not from the assigner**: a subtitle on
  a bullets slide that has none, item headings on a cards slide without heading
  slots, text over capacity, more items than the largest slide holds. This is
  intended (no silent fallback). The cost is about 1.5 extra LLM calls per deck
  with Mistral Small.
- **A requested kind the template lacks is still an error** (19 in run 2) even
  when the content alone would fit another kind. Inferring the kind from the
  content in that case would remove these repairs. That changes D7's rule, so it is
  left to the developer.
- **Prism previews time out**: every rendered prism deck exceeds the 60 s
  LibreOffice limit, so in a pod it would be delivered as a download only, without
  a preview. The 55-69 s wall time per prism run is mostly that timeout. Not
  changed: the limit protects a live turn.
- One run 2 failure is a harness artifact: the model invented an image id and the
  harness provides no `document_content` port.
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

## Checks (9.3)

- `make code-quality` in the package: passed (ruff, format, bandit,
  detect-secrets, basedpyright 0 errors; `eval/` added to the type-checked paths).
- `make test` in the package: 326 passed, 3 skipped (the reference-template tests,
  which pass with `PPT_BUILDER_REFERENCE_TEMPLATE` pointing at the corporate deck:
  3 passed).
- fred-sdk, fred-runtime and frontend suites were not re-run in WP9 (they were
  last run in WP1/WP10/WP8, and WP9 does not touch them).
- `fred-performance-reviewer` on the tool path and the background job: findings
  are listed in the WP9 report; fix 3 above is the one applied.
