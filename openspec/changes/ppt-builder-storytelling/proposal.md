## Why

`ppt_builder` (GitHub issue #2679) checks a deck's form (fit, variety, sections) but never its substance, and the model has no storytelling phase: it writes the plan and builds in one `build_presentation` call. Real tests with `mistral-medium` (2026-10-14) produced:

- a column chart mixing 45 (years), 2 800 (headcount) and 9 (sites) on one axis;
- pie percentages labelled "répartition indicative", invented although documents were provided;
- key figures crammed into one subtitle string instead of a figures slide;
- slides with no point to make: topic titles ("Présentation générale") over content chosen without a conclusion in mind.

The builder's rule stays: the model writes content and intent, the code picks the template slide and the look, and refuses with `needs_revision` rather than build something wrong. This change extends that rule from form to substance.

## What Changes

- **Takeaway per slide (always on).** Each content slide carries `takeaway`: the conclusion the audience draws when looking at it, as a full sentence. It designs the slide (kind, what to show, what to emphasise), is the first line of the speaker notes and feeds the plan outline; it does not appear on the slide unless the user asks for key messages to be shown (`ppt-builder-intent-fields` phase C) and is not the title. The model writes a short title from it (none if the user asked for no titles). Cover, agenda, section, closing and quote slides are exempt. A missing takeaway, a takeaway under four words (a topic label), ending with `?` or equal to the title, and a title or subtitle holding three or more figures are `needs_revision` problems.
- **Data checks (always on).** One measure per chart: a series whose written units differ is refused with the remedy (a figures slide); values spanning 100× or more on a unit-less axis are refused once with a question (one measure → set `unit`; else a figures slide), and the same chart resent unchanged is built with a `wide_range_chart` note. Every slide holding figures (a chart, a numeric table, items with numbers) carries `source`: a document name, `user` (typed in the chat), or `illustrative`. `illustrative` is accepted only when the user's messages allow illustrative data, and is then said in the notes, the chart caption and "What was built". The tool spot-checks that at least one of the slide's figures relates to a number in the user's messages or the tool results (formatting variants, rounding and simple derived values match; ambiguity builds); a slide with none is refused once, and a resend is built with a `figures_unverified` note.
- **One option: "Validate the plan before building" (default off).** When on, the first build of a conversation's first deck returns a code-generated outline (audience, main message, one line per slide: kind, title, takeaway, source) instead of a deck; the agent shows it and waits. The next build, after the user's reply, builds. The plan is skipped only when the user's latest message explicitly asks (`skip_plan`, checked against a fr/en lexicon). Edits of a delivered deck never wait. When off: today's behaviour.
- **Deck fields** `audience` and `main_message` (optional), shown in the outline.
- **Summary notes** `illustrative_data`, `figures_unverified`, `wide_range_chart`.
- **2026-10-18 (owner decision: judgement moves to the LLM, design D7).** Every check above except a chart's written units is deleted, with the three word lists and the two notes `figures_unverified` and `wide_range_chart`; `takeaway` and `source` stay fields written to the notes, asked for by the working rules.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: requirements "Every content slide has a takeaway", "A chart holds one measure", "Figures are sourced", "Plan validation before the first build". Applied after `ppt-builder-capability`, `ppt-builder-charts` and `ppt-builder-intent-fields` phases A–B; owns the `takeaway` field, whose on-slide placement is `ppt-builder-intent-fields` phase C (design D2).

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: new `story.py` (takeaway, figure, unit and source checks; conversation figures); `plan.py` (`SlidePlan.takeaway`, `SlidePlan.source`, `DeckPlan.audience`/`main_message`/`proposed`); `tools.py` (checks before the assignment, outline result, gate, `skip_plan`, schema descriptions); `render.py` (notes lines, illustrative caption); `changes.py` (`takeaway`, `source` paths); `capability.py` (`validate_plan` setting, working rules); `fill.py` / `checks.py` (note codes); `lexicon.py` (illustrative-allowance, skip-plan and source words, fr/en).
- Frontend `apps/frontend/src/rework/features/capabilities/ppt_builder/`: the toggle in the config widget, `types.ts`, `DeckSummaryButton.tsx` notes, `locales/{en,fr}`; Help Center `features/capabilities.md` (fr + en). No generated client change expected (the setting is a manifest field, not a router model).
- No new table, migration or dependency: the proposed plan uses the existing `cap_ppt_builder_deck_plan` row. Migration note: a line in the capability's note (unreleased feature, impact none).
