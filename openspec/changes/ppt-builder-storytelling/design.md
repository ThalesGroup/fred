## Context

`ppt_builder` (change `ppt-builder-capability`, D1–D28; charts `ppt-builder-charts`; intents `ppt-builder-intent-fields`) validates a plan before rendering: `assign.py` maps slides to template slides and returns problems, `tools._needs_revision` sends them as `{status: "needs_revision", slides: [{index, problem, options}]}` (a non-error answer, D27), the identical-call guard breaks loops, and `deck_plans.py` stores the conversation's last delivered `DeckPlan` (base of `changes`). The tool reads the messages the model was sent (`history()`, used by `deck_delivered`). `PlanSeries` already keeps the unit written next to each value (`units`); `PlanChart.unit` is chart-wide (one value axis). `SlidePlan.notes` becomes the speaker notes. Settings live in `PptBuilderConfig` and render in the plugin widget (`variety_check`, `variety_max_uses`).

Not covered today: what a slide is meant to say, whether a chart's numbers belong on one axis, where figures come from. The working rules (`_BUILD_INSTRUCTIONS`) ask to build directly and ground content in documents, nothing more.

## Goals / Non-Goals

**Goals:** a deck whose titles say something, whose charts compare like with like, and whose figures come from the user or the documents, with each check deterministic, cheap and actionable for a weak model; one optional plan review before the first build.

**Non-Goals:** proving figures true (no hallucination-proofing); checking that a title is a well-formed assertion beyond length; dual-axis charts; a storytelling call or tool of its own; more than one new setting.

## Decisions

### Owner decisions (2026-10-14)

- **O1.** Data checks are always on, no option: one unit/measure per chart series; figures from the documents or the conversation, illustrative data only when the user explicitly allows it, and then said in the deck.
- **O2.** A key message per content slide, always on; by default the title states it as an assertion. The user's request on titles wins; the message then stays in the speaker notes.
- **O3.** One setting, "Validate the plan before building", default off. On: before the first build of a new deck, the agent presents audience, main message and one line per slide (kind, key message, data source) and waits. Off: today's behaviour. Edits never need re-validation.
- **O4.** One toggle only: every option doubles the test matrix and Mistral is sensitive to prompt variants.

### D1. Checks before the assignment, as `needs_revision` problems

A new `story.py` runs on the plan before `assign.py` (no template fetch, no render) and returns problems in the assigner's shape (`index`, `problem`, `options`), merged into the same `needs_revision` list. So the model sees one revision per call, the D27 next-call rule, the "repeated" flag and the identical-call guard apply unchanged. Checks run on every slide of `slides`, and on the slides a `changes` call inserts, replaces or edits only: an edit is never refused over a slide it does not touch.

### D2. `message` and title (O2)

- `SlidePlan.message: str` — "the one sentence the audience must remember, as an assertion ('Italy weighs twice Spain in headcount', not 'Headcount')". First in the slide schema.
- Exempt kinds: `cover`, `agenda`, `section`, `closing`, and `quote` (its text is the message). The kind is the one the assigner works with (`kind`, else inferred from content).
- Problems: no message on a non-exempt slide; a message under four words ("Présentation générale"). The option names the remedy and a filled example from the slide's own content. Whether a sentence asserts something is not verified.
- Deck-level `titles: message | custom | none`, default `message`. `message`: the title states the message; a `title` sent on a content slide is not used and the agent note says so (never silent). `custom` (user asked for their own wording): `title` is used and the message goes to the notes. `none` (user asked for no titles): the title zone is left unfilled like any unused zone and the message goes to the notes. The description says "only when the user asked"; the code cannot verify it.
- Notes: when the title does not state it, the notes start with `Key message: …`, before the model's notes.
- **Supersedes `takeaway`.** `ppt-builder-intent-fields` phase C (not started) plans an optional `takeaway`, defined as "the slide's key message". Two fields for one meaning would confuse a weak model, so `message` is the one field; phase C keeps its takeaway-zone detection and, if kept, places `message` there when the title does not state it. Phase C is amended in that change, not here.
- Figures crammed into text: a title or subtitle with three or more numbers (years 1900–2099 not counted) is a problem whose option is a `figures` slide (items `number` + `label`), else a table.

### D3. One measure per chart (O1)

Deterministic, per chart:

1. **Written units.** Two different non-empty units among a chart's written values (`45 ans`, `9 sites`; `%` and `M€`) → problem. A bare number does not conflict.
2. **Spread.** On `column`, `bar`, `line`, `area`, `stacked_column`, a chart without `unit` whose non-zero absolute values span 100× or more → problem: "values from 9 to 2 800 on one axis: if they measure different things, show them as figures (items: number + label); if they are one measure, set `unit`". `pie`/`doughnut` exempt (small slices are normal).

The repro chart (45, 2 800, 9, no unit) fails rule 2. Setting `unit` is the escape for a real wide-range measure; a model can also misuse it — not verified.

### D4. Sourced figures (O1)

- **`SlidePlan.source`**, required when the slide holds figures: a `chart`, a `table` with a numeric body cell, or an item with a `number`. Values: a document name, `user`, or `illustrative`; loose spellings read through `lexicon` (`utilisateur`, `conversation` → `user`; `illustratif`, `fictif`, `exemple` → `illustrative`). Missing → problem. Written to the notes as `Source: …`. The document name is free text: not matched against the library.
- **`illustrative`** is accepted only when a user message of the conversation allows it: a fr/en lexicon (`illustrati*`, `fictif/fictive`, `exemple de données`, `invente/inventé`, `dummy`, `fake`, `sample data`, `made-up`, `placeholder`, `mock`). Otherwise a problem: "the user did not ask for illustrative figures: take them from the documents, or ask the user". Accepted, it is said three ways: notes (`Illustrative figures, not from the documents.`), the chart caption suffixed `(illustrative)` / `(illustratif)` in the plan's language, and an `illustrative_data` note in "What was built". Tables and figure slides carry no on-slide mark (no zone for it).
- **Spot-check.** Numbers are read (`read_number`, value equality: `2 800` = `2800` = `2,800`) from the text the model received — user messages and tool results in `history()`, so documents read, searched or attached as delivered to the model. A non-illustrative slide none of whose figures appears there is a problem once. Resent with the same figures, it is built with a `figures_unverified` note (summary, and notes `Figures not found in the documents read.`): never a dead end (computed values such as growth rates legitimately appear nowhere), never silent. A pie's raw values pass where computed shares would not; the option says to send the raw figures.
- **Verified:** a source is stated; illustrative only with the user's allowance; at least one figure per slide appears in the conversation. **Not verified:** every figure; that the named document holds them; computed values; numbers in bullets.
- Cost: one pass over the history text per build call, numbers collected once per call; no I/O, no model call.

### D5. Plan validation: the tool turns the first build into an outline (O3)

`PptBuilderConfig.validate_plan: bool = False`. With it on, and the conversation holding no delivered deck (`deck_delivered(history())` or a stored delivered base), a build call:

1. Runs every check and the assignment (no render). Problems → the usual `needs_revision`: the outline shown is a sound plan.
2. No problem and no proposal answered yet → stores the plan in `cap_ppt_builder_deck_plan` with `proposed = true`, `delivered = false`, and answers (non-error) `status: plan_proposed` with a code-written outline: audience, main message, then `N. kind — message — source` per slide. The text: "Nothing was built. Show this outline to the user in their language and ask them to validate or correct it; end your answer; do not call build_presentation again in this answer."
3. A proposal is answered when a user message follows the `plan_proposed` result in `history()`. Then the call builds: the whole deck in `slides`, or `changes` applied to the proposed plan. Any reply counts: the agent applies corrections. A second call before a reply gets the same `plan_proposed` answer (the identical-call guard).

Once a deck is delivered, `changes` and new decks of the conversation never wait. With the setting off nothing changes.

**One prompt for both settings.** The working rules do not mention the setting: the gate's instructions arrive in the tool result, only when it applies. The rule "ask to validate an outline only when the user asked" stays, so off keeps today's behaviour and on adds no prompt variant (O4).

Rejected:

- **Prompt only** ("present the plan and wait"): weak models build anyway; nothing enforces it.
- **A `plan_validated` flag set by the model**: self-certified; Mistral would set it on the first call.
- **A separate `propose_plan` tool**: a second large plan schema in every call, one more tool to choose wrongly, and the plan written twice; the outline-as-first-build costs the same number of model calls as today plus the user's reply.

### D6. Deck fields, edits, summary

- `DeckPlan.audience`, `DeckPlan.message` (optional; the outline shows them, `—` when absent), `DeckPlan.titles`; top-level build arguments, kept from the base when a `changes` call omits them (as `file_name`).
- `changes.py`: `message`, `source` in `_FIELDS`; `unchanged` compares them.
- `BuildNoteCode` gains `illustrative_data`, `figures_unverified`; frontend `types.ts`, `DeckSummaryButton.tsx`, locales.
- Working rules gain one storytelling sentence (always): decide the deck's main message and each slide's key message before writing; titles state it; every figure from the documents or the user, with `source`; never invent figures unless the user asked for illustrative data.

## Risks / Trade-offs

- [More revision rounds on weak models] → checks run before the assignment and share one revision; each option is a concrete edit; measured in the eval (first-call success, rounds per deck).
- [False refusals: wide-range real data, computed figures] → `unit` escape (D3), second send built with a note (D4).
- [Longer titles overflow] → the existing title fit check refuses with the room in words.
- [Schema growth: `message`, `source`, three deck fields] → one-line descriptions; tool-schema size measured.
- [Allowance lexicon misses a wording] → the revision tells the agent to ask the user, whose answer then holds the word.

## Migration Plan

No table or setting migration: `validate_plan` defaults off, `proposed` is a JSON field of the stored plan. Unreleased capability: a line in its migration note (impact none). Plans stored before this change have no `message`/`source`; per D1, a `changes` call checks only the slides it touches.

## Open Questions

None blocking. To confirm by the owner: D2 (`message` supersedes intent-fields phase C's `takeaway`; `quote` exempt; four-word floor), D3 (100× threshold), D4 (second send built with `figures_unverified`; caption-only on-slide mark), D5 (a user asking to skip validation still gets the outline once).
