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

## 3b. Unsourced figures said truthfully (owner decision 2026-10-17 overnight, design D6)

- [x] 3b.1 The unverified-figures refusal says never to resend made-up figures (ask the user instead); a slide built with `figures_unverified` adds a delivery line telling the agent to present its figures as to be confirmed, never as the user's (slides the call changed only). Test: `test_story_render.py::test_unverified_figures_are_built_on_the_resend_and_said`
- [x] 3b.2 Working rule: figures, names and dates exact when rewording, `source: user` only for what the user wrote, concrete figures the user did not give are asked for (with `ppt-builder-capability` WP53)

## 4. Evidence and close-out

- [ ] 4.1 `eval/prompts.py`: storytelling prompts (prompts added 2026-10-15; metrics and the run pending) with provided documents (the repro request, a "données indicatives" request, a "no titles" request, user-typed figures); metrics: takeaway present, kind and emphasis consistent with the takeaway, refusals per check, false spot-check refusals, first-call success, rounds per deck, tool-schema size before/after
- [ ] 4.2 Evidence PDFs on the built-in template with `mistral-medium`: the repro deck before / after (no mixed-unit chart, figures slide instead of a crammed subtitle, short titles with takeaways in the notes), an illustrative deck showing the caption, a `validate_plan` session (outline, correction, build)
- [x] 4.3 Help Center `features/capabilities.md` fr + en: takeaways and short titles, sources and illustrative data, the "Validate the plan before building" setting (non-technical wording)
- [x] 4.4 Package `README.md` storytelling section; a line in the capability's migration note (impact none)
- [x] 4.5 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright with its baseline; `fred-performance-reviewer` on the spot-check (per-call history scan); `openspec validate ppt-builder-storytelling --strict`
- [x] 4.6 Align `ppt-builder-intent-fields` phase C on this change's `takeaway` (2026-10-15): one field, zone placement only, no on-slide fallback; zone filled with the takeaway only when the user asks for key messages to be shown (O17)
- Verification: `verification.md` with test counts, eval numbers and PDFs, and what stays unverified (design D4)

## 5. Judgement moves to the LLM (owner decision 2026-10-18, design D7)

- [x] 5.1 (H9, H10, H11, M17, M3, §4 takeaway, spread and multi-chart titles) `story.py` keeps only the chart-unit check and the outline: takeaway checks, crammed title, spread, multi-chart titles, required source, illustrative allowance, spot-check, soft refusals and `Conversation` deleted; `tools.py` reads only whether a proposal was answered (`plan_answered`). Tests: `test_story_checks.py` (rewritten: dates/versions/standards in titles, any takeaway, figures without source or match, wide-range and untitled charts pass; units still refused), `test_story_render.py::test_figures_and_a_wide_range_are_built_as_sent`, `test_multi_chart_slides.py::test_each_chart_shows_one_measure_and_may_go_untitled`
- [x] 5.2 `figures_unverified`, `wide_range_chart`, `SlidePlan.story_notes`, the unverified notes line and delivery line deleted (backend, `DeckSummaryButton.tsx`, locales; `illustrative_data` no longer says "as you asked"). Tests: `DeckSummaryButton.test.tsx`
- [x] 5.3 (H12) The three word lists deleted: `show_takeaways` and `skip_plan` honoured as the model sends them, `illustrative` never refused; `_NOT_ASKED` and the skip-refused line deleted. Tests: `test_takeaway.py::test_the_flag_is_applied_whatever_the_user_s_language`, `test_plan_validation.py::test_skip_plan_is_the_model_s_call_in_any_language`, `test_story_render.py::test_illustrative_figures_are_said_in_caption_notes_and_summary` (German request)
- [x] 5.4 The `storytelling` test marker and its fixture deleted (every test runs the remaining check); README, Help Center `features/capabilities.md` (fr + en)
- [x] 5.5 Package checks; `openspec validate --strict`
- Not changed: L13 (the `source` value read as an exact phrase for the illustrative caption), M14 (chart readability caps), M20 (title words as a kind hint), M27, L10, L12: other rules, not this lot

## 6. Titles, sources and the outline's notes (owner decision 2026-10-18, design D8)

- [x] 6.1 Title = the slide's conclusion as a short sentence (description, `SlidePlan.title`, working rules); Help Center fr + en. Test: `test_build_tool.py::test_a_title_states_the_conclusion_and_the_takeaway_stays_in_the_notes`
- [x] 6.2 `source` for the user's documents or data, left out for general knowledge (description, field, working rules, README); Help Center fr + en. Test: `test_build_tool.py::test_source_is_asked_only_for_the_user_s_documents_or_data`
- [x] 6.3 The `plan_proposed` outline lists the assignment notes the build would give; Help Center fr + en. Test: `test_plan_validation.py::test_the_outline_carries_the_notes_its_build_would_give`; offline replay of 4fbe0531 call 10 with the gate on shows the cover fallback note
- [x] 6.4 Repeat note without alternative and split note end on their fix. Tests: `test_assign.py`, `test_table_slides.py`
- [x] 6.5 Package checks (933 passed); `openspec validate --strict`
