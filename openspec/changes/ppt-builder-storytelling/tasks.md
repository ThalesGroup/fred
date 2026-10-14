## 1. Plan fields and checks

- [ ] 1.1 `plan.py`: `SlidePlan.message` (first in the schema), `SlidePlan.source`, `DeckPlan.titles` / `audience` / `message` / hidden `proposed`; loose spellings and aliases (`key_message`, `takeaway` → `message`; `sources`, `data_source` → `source`); one-line descriptions (design D2, D4, D6)
- [ ] 1.2 `lexicon.py`: exempt kinds, illustrative-allowance words, source words (fr/en)
- [ ] 1.3 `story.py`: message presence and four-word floor, numbers in title/subtitle, chart units and spread, source presence, illustrative allowance, conversation spot-check with the second-send rule; problems in the assigner's shape (D1–D4)
- [ ] 1.4 `tools.py`: run `story.py` before the assignment on `slides` and on the slides `changes` touch; merge into `needs_revision`
- Verification: `tests/test_story_checks.py` — the repro chart (45 / 2 800 / 9) refused, same values with `unit` accepted, mixed written units refused, pie exempt; missing and two-word `message` refused, exempt kinds pass; three figures in a subtitle refused, a date not counted; missing `source` refused; `illustrative` refused without an allowance word and accepted with "données fictives"; a slide whose figures appear in a tool result passes, none found refused once then built with `figures_unverified`; an edit of slide 3 not refused over slide 7

## 2. Rendering and edits

- [ ] 2.1 `render.py`: title from `message` under `titles: message` (a sent title noted to the agent), `custom` / `none` behaviour, notes lines `Key message:` / `Source:` / illustrative and unverified lines before the model's notes, chart caption suffix in the plan's language
- [ ] 2.2 `changes.py`: `message`, `source` paths; deck fields kept from the base when omitted; `unchanged` compares them
- [ ] 2.3 `fill.py` / `checks.py`: `illustrative_data`, `figures_unverified` note codes
- Verification: `tests/test_story_render.py` — title equals the message, `custom` keeps the title and puts the message in the notes, `none` leaves the title unfilled, notes order, caption suffix fr/en, edit of `message` re-renders the title; existing `test_build_tool.py`, `test_deck_changes.py`, `test_chart_slides.py` green

## 3. Plan validation setting

- [ ] 3.1 `capability.py`: `validate_plan: bool = False` in `PptBuilderConfig` and its `FieldSpec` (plugin widget); working rules gain the storytelling sentence, no setting-dependent text (D5, D6)
- [ ] 3.2 `tools.py`: gate (no delivered deck, setting on), outline text, `proposed` plan stored, answered-proposal detection from `history()`, `changes` against the proposed plan
- [ ] 3.3 Frontend `ppt_builder/`: toggle in the config widget, `types.ts` key, `DeckSummaryButton.tsx` wording of the two notes, `locales/{en,fr}`
- [ ] 3.4 Generated client: run `make update-all-apis` in `apps/frontend` and confirm no diff (the setting is a manifest field); commit the regeneration only if it changes
- Verification: `tests/test_plan_validation.py` — setting off builds directly; on: first call returns `plan_proposed` with every slide's kind, message and source and stores the plan; a second call in the same turn gets the same answer; after a user message `slides` builds and `changes` apply to the proposed plan; a delivered deck's edit is never gated; a plan with problems gets `needs_revision`, not the outline. Frontend: toggle test beside `PptBuilderVarietySettings.test.tsx`, `DeckSummaryButton.test.tsx` notes; `tsc`, `prettier`, `eslint`, `vitest`

## 4. Evidence and close-out

- [ ] 4.1 `eval/prompts.py`: storytelling prompts with provided documents (the repro request, a "données indicatives" request, a "no titles" request); metrics: message present, title = message, refusals per check, first-call success, rounds per deck, tool-schema size before/after
- [ ] 4.2 Evidence PDFs on the built-in template with `mistral-medium`: the repro deck before / after (no mixed-unit chart, figures slide instead of a crammed subtitle, message titles), an illustrative deck showing the caption, a `validate_plan` session (outline, correction, build)
- [ ] 4.3 Help Center `features/capabilities.md` fr + en: key-message titles, sources and illustrative data, the "Validate the plan before building" setting (non-technical wording)
- [ ] 4.4 Package `README.md` storytelling section; a line in the capability's migration note (impact none)
- [ ] 4.5 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright with its baseline; `fred-performance-reviewer` on the spot-check (per-call history scan); `openspec validate ppt-builder-storytelling --strict`
- [ ] 4.6 Coordinate with `ppt-builder-intent-fields` phase C: replace its `takeaway` field by `message` (design D2), in that change
- Verification: `verification.md` with test counts, eval numbers and PDFs, and what stays unverified (design D4)
