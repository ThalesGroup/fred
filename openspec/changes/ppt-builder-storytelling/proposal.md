## Why

`ppt_builder` (GitHub issue #2679) checks a deck's form (fit, variety, sections) but never its substance, and the model has no storytelling phase: it writes the plan and builds in one `build_presentation` call. Real tests with `mistral-medium` (2026-10-14) produced:

- a column chart mixing 45 (years), 2 800 (headcount) and 9 (sites) on one axis;
- pie percentages labelled "répartition indicative", invented although documents were provided;
- key figures crammed into one subtitle string instead of a figures slide;
- topic titles ("Présentation générale") instead of titles that state the slide's point.

The builder's rule stays: the model writes content and intent, the code picks the template slide and the look, and refuses with `needs_revision` rather than build something wrong. This change extends that rule from form to substance.

## What Changes

- **Key message per slide (always on).** Each content slide carries `message`: one sentence stating its point. By default the slide's title states it. A deck-level `titles: message | custom | none` lets the user's request win (own wording, or no titles); the message then goes to the speaker notes. Cover, agenda, section, closing and quote slides are exempt. A missing or topic-like message (under four words) and a title or subtitle holding three or more figures are `needs_revision` problems.
- **Data checks (always on).** One measure per chart: a series whose written units differ, or whose values span 100× or more on a unit-less axis, is refused with the remedy (a figures slide, or a `unit` if it really is one measure). Every slide holding figures (a chart, a numeric table, items with numbers) carries `source`: a document name, `user`, or `illustrative`. `illustrative` is accepted only when the user's messages allow illustrative data, and is then said in the notes, the chart caption and "What was built". The tool spot-checks that at least one of the slide's figures appears in the text the model received; a slide with none is refused once, and a resend is built with a `figures_unverified` note.
- **One option: "Validate the plan before building" (default off).** When on, the first build of a conversation's first deck returns a code-generated outline (audience, main message, one line per slide: kind, key message, source) instead of a deck; the agent shows it and waits. The next build, after the user's reply, builds. Edits of a delivered deck never wait. When off: today's behaviour.
- **Deck fields** `audience` and `message` (optional), shown in the outline.
- **Summary notes** `illustrative_data`, `figures_unverified`.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: requirements "Every content slide states its key message", "A chart holds one measure", "Figures are sourced", "Plan validation before the first build". Applied after `ppt-builder-capability`, `ppt-builder-charts` and `ppt-builder-intent-fields`; supersedes the `takeaway` field of `ppt-builder-intent-fields` phase C (design D2).

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: new `story.py` (message, figure, unit and source checks; conversation figures); `plan.py` (`SlidePlan.message`, `SlidePlan.source`, `DeckPlan.titles`/`audience`/`message`/`proposed`); `tools.py` (checks before the assignment, outline result, gate, schema descriptions); `render.py` (title from message, notes lines, illustrative caption); `changes.py` (`message`, `source` paths); `capability.py` (`validate_plan` setting, working rules); `fill.py` / `checks.py` (note codes); `lexicon.py` (illustrative-allowance and source words, fr/en).
- Frontend `apps/frontend/src/rework/features/capabilities/ppt_builder/`: the toggle in the config widget, `types.ts`, `DeckSummaryButton.tsx` notes, `locales/{en,fr}`; Help Center `features/capabilities.md` (fr + en). No generated client change expected (the setting is a manifest field, not a router model).
- No new table, migration or dependency: the proposed plan uses the existing `cap_ppt_builder_deck_plan` row. Migration note: a line in the capability's note (unreleased feature, impact none).
