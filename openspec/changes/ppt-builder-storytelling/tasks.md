## 1. Plan fields and checks

- [x] 1.1 `plan.py`: `SlidePlan.takeaway` (first in the schema), `SlidePlan.source`, `DeckPlan.audience` / `main_message` / hidden `proposed`; loose spellings and aliases (slide `message`, `key_message`, `key_takeaway` → `takeaway`; deck `message` → `main_message`; `sources`, `data_source` → `source`); one-line descriptions (design D2, D4, D6)
- [x] 1.2 `lexicon.py`: exempt kinds, illustrative-allowance words, skip-plan words, source words (fr/en)
- [x] 1.3 `story.py`: takeaway presence, four-word floor, final `?`, equal to the title (O13), numbers in title/subtitle, chart units (always) and spread (refused once, resend built with `wide_range_chart`, O18), source presence, illustrative allowance, conversation spot-check (user messages and tool results; reading variants, rounding, derived values; second-send rule); problems in the assigner's shape (D1–D4)
- [x] 1.4 `tools.py`: run `story.py` before the assignment on `slides` and on the slides `changes` touch; merge into `needs_revision`
- Verification: `tests/test_story_checks.py` — the repro chart (45 / 2 800 / 9) refused once then built unchanged with `wide_range_chart`, same values with `unit` accepted, mixed written units refused on every send, pie exempt; missing, two-word, question and title-equal `takeaway` refused, a sentence accepted whatever the title, exempt kinds pass; three figures in a subtitle refused, a date not counted; missing `source` refused; `illustrative` refused without an allowance word and accepted with "données fictives"; spot-check passes for a figure typed by the user, `2 800` vs `2800` / `2,8 k`, `12,5 %` vs `12.46`, `2,8 M€` vs `2 800 000`, a total of the slide's values, a share and a growth rate of two found numbers; values related to nothing refused once then built with `figures_unverified`; an edit of slide 3 not refused over slide 7

## 2. Rendering and edits

- [x] 2.1 `render.py`: notes start with the takeaway, then `Source:` / illustrative / unverified lines in the plan's language, then the model's notes; chart caption suffix in the plan's language; title untouched by the takeaway
- [x] 2.2 `changes.py`: `takeaway`, `source` paths; deck fields kept from the base when omitted; `unchanged` compares them
- [x] 2.3 `fill.py` / `checks.py`: `illustrative_data`, `figures_unverified`, `wide_range_chart` note codes
- Verification: `tests/test_story_render.py` — title is the sent title (never the takeaway), no title sent leaves the zone unfilled, notes order, caption suffix fr/en, edit of `takeaway` updates the notes only; existing `test_build_tool.py`, `test_deck_changes.py`, `test_chart_slides.py` green

## 3. Plan validation setting

- [x] 3.1 `capability.py`: `validate_plan: bool = False` in `PptBuilderConfig` and its `FieldSpec` (plugin widget); working rules gain the storytelling paragraph (D2), no setting-dependent text (D5)
- [x] 3.2 `tools.py`: gate (no delivered deck, setting on), outline text, `proposed` plan stored, answered-proposal detection from `history()`, `changes` against the proposed plan, `skip_plan` honoured only on a skip-lexicon match in the latest user message
- [x] 3.3 Frontend `ppt_builder/`: toggle in the config widget, `types.ts` key, `DeckSummaryButton.tsx` wording of the three notes, `locales/{en,fr}`
- [x] 3.4 Generated client: run `make update-ppt-builder-capability-api` in `apps/frontend` and confirm no diff (the setting is a manifest field); commit the regeneration only if it changes
- Verification: `tests/test_plan_validation.py` — setting off builds directly; on: first call returns `plan_proposed` with every slide's kind, title, takeaway and source and stores the plan; a second call in the same turn gets the same answer; after a user message `slides` builds and `changes` apply to the proposed plan; `skip_plan` with "construis directement, sans plan" in the latest user message builds, `skip_plan` without it gets the outline; a delivered deck's edit is never gated; a plan with problems gets `needs_revision`, not the outline. Frontend: toggle test beside `PptBuilderVarietySettings.test.tsx`, `DeckSummaryButton.test.tsx` notes; `tsc`, `prettier`, `eslint`, `vitest`

## 4. Evidence and close-out

- [ ] 4.1 `eval/prompts.py`: storytelling prompts (prompts added 2026-10-15; metrics and the run pending) with provided documents (the repro request, a "données indicatives" request, a "no titles" request, user-typed figures); metrics: takeaway present, kind and emphasis consistent with the takeaway, refusals per check, false spot-check refusals, first-call success, rounds per deck, tool-schema size before/after
- [ ] 4.2 Evidence PDFs on the built-in template with `mistral-medium`: the repro deck before / after (no mixed-unit chart, figures slide instead of a crammed subtitle, short titles with takeaways in the notes), an illustrative deck showing the caption, a `validate_plan` session (outline, correction, build)
- [x] 4.3 Help Center `features/capabilities.md` fr + en: takeaways and short titles, sources and illustrative data, the "Validate the plan before building" setting (non-technical wording)
- [x] 4.4 Package `README.md` storytelling section; a line in the capability's migration note (impact none)
- [x] 4.5 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright with its baseline; `fred-performance-reviewer` on the spot-check (per-call history scan); `openspec validate ppt-builder-storytelling --strict`
- [x] 4.6 Align `ppt-builder-intent-fields` phase C on this change's `takeaway` (2026-10-15): one field, zone placement only, no on-slide fallback; zone filled with the takeaway only when the user asks for key messages to be shown (O17)
- Verification: `verification.md` with test counts, eval numbers and PDFs, and what stays unverified (design D4)
