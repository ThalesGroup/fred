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

## Not verified

- Every figure, that the named document holds them, numbers in bullets (design D4).
- Model behaviour: tasks 4.1 metrics (prompts added to `eval/prompts.py`, metrics not added) and 4.2 evidence with `mistral-medium` need a real LLM run; not done here.
- The plan's language is guessed from its words (fr/en only).
