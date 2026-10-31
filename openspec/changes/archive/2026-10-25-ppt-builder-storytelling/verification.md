# Verification — ppt-builder-storytelling

Date: 2026-10-15, branch `feat/ppt-builder-capability`.

## Tests

- Package `make test`: 761 passed, 5 skipped (48 new).
  - `tests/test_story_checks.py` (31): takeaway missing / two words / question / equal to the title refused, a sentence accepted whatever the title, exempt kinds; three figures in a subtitle refused (cover too), years and two figures pass; the repro chart (45 / 2 800 / 9) refused once then accepted with `wide_range_chart` (this turn, and from an earlier turn's build result), `unit` and pie exempt; two written units refused on every send, bare numbers beside a unit pass; missing `source` on a chart, a numeric table and figure items; steps, years and text tables hold no figures; `illustrative` refused without an allowance word, accepted with "données fictives"; spot-check matches `2800`/`2 800`/`2,8 k`, `12,46 %`/`12,5 %`, `2,8 M€`/`2 800 000 €`, `2 784`/`2 800`, `1,234.5`, user-typed figures, a share (43 % of 1 200 / 2 800), a growth rate, a total of the slide's values, a sum within one tool result but not across two; figures related to nothing refused once then accepted with `figures_unverified`; the build tool's own answers are no source; scan and derived lookups bounded; an edit checks only the slides it touches.
  - `tests/test_story_render.py` (9, through `build_presentation` on the built-in template): notes = takeaway, `Source : …`, model notes; the title is the one sent, the takeaway never on the slide; no title sent leaves it unfilled; illustrative caption `(illustratif)`, notes line and `illustrative_data`; caption/notes language; unverified figures built on the resend with the note in summary and notes; wide-range chart built on the resend with `wide_range_chart`; an edit of `takeaway` changes the notes only; an edit is not refused over an untouched slide of an older deck without takeaway; two written units refused through the tool.
  - `tests/test_plan_validation.py` (8): setting off builds (and ignores `skip_plan`); on: `plan_proposed` with audience, main message and `N. kind — title — takeaway — source` lines, plan stored with `proposed`, nothing written; a second call before the answer gets the outline again; after a user message `slides` builds and `changes` (remove slide 3) apply to the proposed plan; `skip_plan` + "Construis-la directement, sans plan" builds, `skip_plan` without it gets the outline with the "does not ask to skip" line, the words without the argument get the outline; a delivered deck's edit never waits; a plan with problems gets `needs_revision`; working rules carry no setting-dependent text.
  - Existing suites unchanged in behaviour; they run with the storytelling checks off (`conftest.py`, marker `storytelling`) because their plans predate takeaways and sources. Expectations updated for the schema order (`takeaway` first), the title description, the edit-field list and the `changes` schema size budget (1 600 → 1 650 chars).
- `ruff check`, `ruff check --select I`, `ruff format --check`: clean. basedpyright with the baseline: 0 errors.
- Frontend: `tsc --noEmit` clean; `prettier --check` and `eslint` on the touched files clean; `vitest` on `PptBuilderPlanSettings.test.tsx` (3 new), `DeckSummaryButton.test.tsx` (1 new + codes list), `PptBuilderVarietySettings.test.tsx`, `PptBuilderTemplatePanel.test.tsx`: 29 passed.
- `make update-ppt-builder-capability-api`: no diff (the setting is a manifest field).
- `openspec validate ppt-builder-storytelling --strict`, `openspec validate ppt-builder-intent-fields --strict`: valid.

## Evidence (no LLM)

`storytelling.pdf` (scratchpad `charts-evidence/`, slides then notes pages), produced through `build_presentation` on the built-in template: with `validate_plan` on, the outline text; a cover subtitle "45 ans, 2 800 salariés, 9 sites" and a "12 % / 3 M€" chart refused (and refused again when resent identically); the corrected deck with a figures slide (45 ans, 2 800, 9), a one-unit bar chart (`unit: salariés`, highlight, sort), short titles, and notes pages starting with each takeaway then `Source : l'utilisateur`.

## Performance

- The checks run in the worker thread with the assignment; the conversation is read once per model call (cached on the history), its numbers only when a slide needs the spot-check.
- Bounds: 100 k chars per source, 1.5 M in all, 4 000 distinct numbers (latest sources first, scan stops at the cap), 20 000 derived lookups per slide (past it, found). Measured: 3.3 M chars of dense numbers 30 ms, 1.8 M chars of prose 33 ms; 20 slides checked against 4 000 numbers 55 ms.
- One extra deck-plan read per first build only with `validate_plan` on; one write per proposal. No model call, no new cross-replica state (the soft-refusal memory is the turn's tool instance plus the history).
- Tool schema: +1 204 chars for `takeaway`, `source`, `audience`, `main_message`, `skip_plan` (built-in template schema 11 138 chars); description and working rules each gain a short paragraph.

## Divergences from the design (justified)

- The notes and caption helpers live in `notes.py`, called by `render.py`: `story.py` needs the assigner, which imports the renderer.
- A hidden `SlidePlan.story_notes` keeps the codes a soft check accepted (`figures_unverified`, `wide_range_chart`), so the notes line and summary survive later edits of other slides.
- "Refused once" is keyed on the problem text (it names the values), remembered for the turn and found in earlier build results of the history; a soft-only refusal is not recorded by the identical-call guard, so the identical resend is evaluated and built.
- Takeaway checks add a final `?` and equality with the title (O13). A `quote` inferred from content (bullets without a title) is not exempt; only an asked `quote` is.
- Written units are taken from the call itself in `_sent` (they are not dumped), never carried through storage, so an edit never inherits stale units.
- Figures-slide options are worded template-neutrally ("one item per figure"): the built-in figures slide has no `label`.

## Task group 5 (2026-10-18): judgement moves to the LLM (design D7)

- Regression tests assert the new behaviour and failed on the code before (each case was a refusal there; the audit probed H9, H10, H12 offline): `test_story_checks.py::test_dates_versions_and_standards_stay_in_a_title`, `test_the_takeaway_is_never_refused` (incl. a CJK sentence), `test_figures_need_no_source_nor_a_match_in_the_conversation` (roadmap table, figures found nowhere, illustrative without allowance), `test_a_wide_range_and_untitled_charts_are_built_as_sent`; `test_story_render.py::test_figures_and_a_wide_range_are_built_as_sent`, `test_illustrative_figures_are_said_in_caption_notes_and_summary` (German request); `test_takeaway.py::test_the_flag_is_applied_whatever_the_user_s_language`; `test_plan_validation.py::test_skip_plan_is_the_model_s_call_in_any_language`; `test_multi_chart_slides.py::test_each_chart_shows_one_measure_and_may_go_untitled`. Kept: units refused on every send, per scatter axis, on touched slides only. Frontend `DeckSummaryButton.test.tsx` (8 passed), `tsc --noEmit` clean.
- Eval history (`~/fred-tmp/revision-evals/runs/`, 164 runs): 71 of 170 distinct `needs_revision` results, in 58 runs, were refused only by checks this group or `ppt-builder-capability` WP57 deleted (mostly a missing `source` or `takeaway`).
- Offline build on the built-in template, one slide `kind: bullets` titled "Comité du 18/10 : 3 décisions" with "Release 2.1 vs 3.0 vs 4.0", "ISO 27001", "Phase 2", no cover, no takeaway, no source: delivered on the first call (before: refused for the cover, the title's figures and the takeaway); LibreOffice render `~/fred-tmp/revision-evals/fixes/audit/lot3/one-slide/`, PNG looked at.
- Lines (package and frontend sources, commits 22a1041d1..22492297f): +113 / −833; tests +125 / −432. Prompt size (cl100k, built-in): working rules 584 → 584 (591 gated), tool description 3214 → 3215, args schema 4316 → 4314 (4373 → 4371 gated). No rule or description line added: each deleted check's ask was already in the working rules or a field description.
- Commands: ruff, `ruff check --select I`, ruff format, `make type-check` (0 errors, the baseline warning); `make test`: 916 passed, 5 skipped (941 before: the deleted checks' tests went with them); `openspec validate --strict`.
- Not proven: model behaviour without the refusals (fred-agents not restarted). Takeaways, sources and real figures now rest on the working rules alone.

## Not verified

- Any figure (design D7: the spot-check is deleted).
- Model behaviour: tasks 4.1 metrics (prompts added to `eval/prompts.py`, metrics not added) and 4.2 evidence with `mistral-medium` need a real LLM run; not done here.
- The plan's language is guessed from its words (fr/en only).

## 2026-10-18 — titles, sources, outline notes (D8)

- Package `make test`: 933 passed, 5 skipped; ruff (incl. `--select I`), format, basedpyright clean. Each new test fails on the code before its fix.
- Tokens (cl100k, Thales v3 inventory of 4fbe0531): description 3365 → 3387, schema 4371 → 4376, working rules 585 → 587.
- Offline replay of 4fbe0531 call 10 with `validate_plan` on (`~/fred-tmp/revision-evals/fixes/audit/review-4fbe0531/`): the outline now ends with the slide 1 cover → section note and the section repeat note "use fewer 'section' slides".
- Not verified: a live mistral-medium turn (titles as claims, no `source` on general knowledge) — judgement of the model.

## Live checks (2026-10-25)

- 9.2: the owner checked the plan approval card (outline, Approve button, free answer) in the browser.
- 10.2: the owner checked k€/M€ in the browser; chart eval `charts-r3` p07 (mixed k€) pass, M€ axis 0,5–3,0 M€.
- Still open: 4.1 (storytelling metrics in `eval/prompts.py` and their run) and 4.2 (evidence PDFs on the built-in template).
