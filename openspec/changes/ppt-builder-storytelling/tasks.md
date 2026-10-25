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

## 7. The outline's notes are the user's to decide (owner decision 2026-10-20, design D9)

- [x] 7.1 A proposal's notes word each fix as the user's choice ("If the user wants …: …") instead of "call again and …", "To vary them, recast one …", "To keep one slide, send at most …"; the delivery notes keep their wording; the proposal says the notes are for the user and not a fix to make now. Tests: `test_assign.py::test_an_agenda_too_long_goes_to_a_close_kind_that_holds_it`, `test_an_agenda_one_entry_too_long_continues_on_a_second_agenda_slide`, `test_every_note_numbers_slides_as_its_outline_does`, `test_plan_validation.py::test_the_outline_carries_the_notes_its_build_would_give` (extended)
- [x] 7.2 With the plan gate on, the working rules say a proposed plan ends the answer: show the outline and its notes, never call the tool again in that answer to address a note. Test: `test_plan_validation.py::test_a_proposed_plan_ends_the_answer_even_with_notes`
- [x] 7.3 Package checks; `openspec validate --strict`
- [x] 7.4 Live A/B (B settings, mistral-medium, reasoning replay, ≤4 parallel): build calls per base turn and turns ending on the call cap, before / after. Result 2026-10-20 (`~/fred-tmp/leak-study/FIX23.md`, 14 valid runs): improved, not fixed. Build calls per base turn median 7.5–8 → 4; base turns on the call cap 15/24 → 6/14; re-call after a proposal with notes 96% → 78%; 0/179 leaked calls; 13/14 decks (1 infra failure). Reasoning still treats the user-facing notes as fixes to make now, so the `tool_choice="none"` guard is still needed. New: 2/14 confirm turns re-built the delivered deck 6–8 times, chasing delivery variety notes
- [x] 7.5 Superseded (owner decision 2026-10-23): a proposal carries no notes, only the outline; `Assignment.plan_notes` and the "If the user wants" wording deleted; delivery notes unchanged. Tests: `test_plan_validation.py::test_the_outline_carries_no_notes_the_delivery_tells_them`, `::test_a_proposed_plan_ends_the_answer`
- Not changed (pending owner decision): the turn-scoped cap message (`~/fred-tmp/leak-study/PLAN-REPEAT.md` fix 4); fixes 1 and 5 are section 8

## 8. A proposal or a delivery ends the answer (owner decision 2026-10-20, design D10)

- [x] 8.1 After a `plan_proposed` or delivered result, the builder middleware sends the next model calls of the answer with `tool_choice="none"`; a revision, an error or the user's next message leaves the tools. Tests: `test_plan_validation.py::test_a_proposal_or_a_delivery_closes_the_answer_until_the_user_speaks`, `test_the_model_call_after_a_proposal_gets_no_tool`
- [x] 8.2 The runtime's tool-call text recovery skips a call sent with `tool_choice="none"`. Test: `libs/fred-runtime` `test_tool_call_recovery.py::test_a_reply_only_call_keeps_tool_call_text_as_text`
- [x] 8.3 The working rules say a delivered deck or a proposed plan ends the answer (cuts and notes told to the user); "the same for cuts that matter" removed
- [x] 8.4 `skip_plan` honoured only when its quote is in the user's latest message, word for word. Tests: `test_plan_validation.py::test_a_skip_quote_the_user_never_wrote_proposes_the_plan`, `test_skip_plan_is_the_model_s_call_in_any_language`
- [x] 8.5 Package checks: ppt-filler `make code-quality` + `make test` (942 passed), fred-runtime `make code-quality` + `make test` (2216 passed); `openspec validate --strict`
- [x] 8.6 Live check, same scenarios as 7.4: build calls per base turn, cap hits, re-call after a proposal, delivery rebuilds in confirm turns, `skip_plan` forcing, fixes applied on confirm, a failed build retried. Evidence (14 runs, 2026-10-20): median 2 builds/base turn, 0 cap hits, 0/14 re-calls after a proposal, 0 confirm rebuilds, 0 `skip_plan` calls (refusal covered by 8.4 tests only), both fix confirms applied, 15 turns retried after needs_revision, 14/14 decks, 0/141 leaks

## 9. Plan approval with a button (owner decision 2026-10-23, design D11)

- [x] 9.1 With `ask_user` offered, a proposal forces the approval question; the middleware replaces its choices by "Approuver"/"Approve" plus a free answer; only that choice approves, a free answer revises, a skip ends the answer; an approval forces the build call. Without `ask_user`, the user's reply still answers. Tests: `test_plan_validation.py::test_only_the_approve_button_approves_a_plan`, `::test_the_approve_button_builds_and_a_free_answer_revises`, `::test_with_ask_user_a_proposal_asks_and_an_approval_builds`, `::test_the_approval_question_offers_approve_and_a_free_answer`, `::test_a_proposal_or_a_delivery_closes_the_answer_until_the_user_speaks` (updated)
- [ ] 9.2 Live check once fred-agents runs this code: the card shows the outline with the Approve button and the free answer

## 10. Amounts in one scale (owner decision 2026-10-23, design D12)

- [x] 10.1 A category chart's k€/M€/Md€ (k$, M$, K/M/B/bn/Md) values are converted to one scale (most values 1-999, the chart's `unit` when it names one); single-unit amounts from 10 000 are shown in k€/M€/Md€ (bn in English); the one-measure check runs after it. Amounts of 10 000 or more written in slide text (bullets, columns, items, table cells, title, takeaway) with a €/$/£ sign are shortened the same way (520 000 € → 520 k€, $1,250,000 → $1.25M); smaller, already scaled and non-currency numbers stay as written. Tests: `test_story_checks.py::test_amounts_in_several_scales_of_one_unit_are_put_in_one`, `::test_a_billion_scale_is_spelled_in_the_deck_s_language`, `::test_other_measures_or_unscaled_numbers_still_mix_units`, `::test_large_amounts_written_in_text_are_rescaled_too`, `::test_short_or_scaled_amounts_and_other_numbers_are_left_in_text`, `::test_text_amounts_are_spelled_in_the_deck_s_language`, `test_story_render.py::test_k_and_m_euros_in_one_chart_are_drawn_in_one_scale`
- [x] 10.3 The largest value sets the scale (2 450 000 € → 2,45 M€); the decimals come from the converted values; an axis's 0 reads "0" (`number_format(ticks=True)`). Tests: `test_story_checks.py::test_amounts_in_several_scales_of_one_unit_are_put_in_one`, `test_chart_slides.py::test_the_decimals_come_from_the_scaled_values`, `::test_values_carry_their_unit_and_pies_their_percentages`
- [ ] 10.2 Live check once fred-agents runs this code
