## Context

`ppt_builder` (change `ppt-builder-capability`, D1–D28; charts `ppt-builder-charts`; intents `ppt-builder-intent-fields`) validates a plan before rendering: `assign.py` maps slides to template slides and returns problems, `tools._needs_revision` sends them as `{status: "needs_revision", slides: [{index, problem, options}]}` (a non-error answer, D27), the identical-call guard breaks loops, and `deck_plans.py` stores the conversation's last delivered `DeckPlan` (base of `changes`). The tool reads the messages the model was sent (`history()`, used by `deck_delivered`). `PlanSeries` already keeps the unit written next to each value (`units`); `PlanChart.unit` is chart-wide (one value axis). `SlidePlan.title` is optional (an absent title leaves the zone unfilled). `SlidePlan.notes` becomes the speaker notes. Settings live in `PptBuilderConfig` and render in the plugin widget (`variety_check`, `variety_max_uses`).

Not covered today: what a slide is meant to make the audience conclude, whether a chart's numbers belong on one axis, where figures come from. The working rules (`_BUILD_INSTRUCTIONS`) ask to build directly and ground content in documents, nothing more.

## Goals / Non-Goals

**Goals:** slides designed around what the audience should conclude, charts that compare like with like, figures from the user or the documents, with each check deterministic, cheap and actionable for a weak model; one optional plan review before the first build.

**Non-Goals:** proving figures true (no hallucination-proofing); judging the quality of a takeaway or a title; dual-axis charts; a storytelling call or tool of its own; more than one new setting.

## Decisions

### Owner decisions (2026-10-14)

- **O1.** Data checks are always on, no option: one unit/measure per chart series; figures from the documents or the conversation, illustrative data only when the user explicitly allows it, and then said in the deck.
- **O2.** A key message per content slide, always on. (Its "the title states it" part is superseded by O7.)
- **O3.** One setting, "Validate the plan before building", default off. On: before the first build of a new deck, the agent presents audience, main message and one line per slide and waits. Off: today's behaviour. Edits never need re-validation.
- **O4.** One toggle only: every option doubles the test matrix and Mistral is sensitive to prompt variants.

### Owner decisions (2026-10-15)

- **O5.** One field, named `takeaway`; it is the `takeaway` of `ppt-builder-intent-fields` phase C, whose zone detection stays there.
- **O6.** `quote` slides are exempt.
- **O7.** The takeaway is the message that forms in the audience's head when they look at the slide. It guides the slide's design (kind, what to show, what to emphasise); it need not appear on the slide and is not the title. The title is short, written from the takeaway. No `titles` deck field; a user asking for no titles is followed through the plan.
- **O8.** Figures spot-check kept (refused once, then built with `figures_unverified`), but never abusive: figures the user typed count as found; formatting variants, rounding and derived values match; ambiguity builds.
- **O9.** Illustrative data: no on-slide marking beyond the chart caption suffix (D4).
- **O10.** With the setting on, the plan is skipped only when the user explicitly asks; default stays plan first.
- **O11.** Deck-level optional `audience` and main message: confirmed, the latter named `main_message`.

### Owner decisions (2026-10-15, final answers)

- **O12.** Takeaway as the unlabelled first notes line, other notes lines (`Source:`, illustrative, unverified) in the plan's language: confirmed (D2, D6).
- **O13.** The takeaway is a real sentence, the conclusion the audience draws, not a topic label. The four-word floor stays the cheap guard; one light extra check only where it is reliable across languages (D2). Detecting a verbless noun phrase is not attempted.
- **O14.** Figures crammed into a title or subtitle: refused, a figures slide offered — confirmed (D2).
- **O15.** Spot-check: 1 % tolerance and sums/differences only from one message or tool result — confirmed (D4).
- **O16.** `skip_plan` needs the argument and an explicit skip request in the latest user message — confirmed (D5).
- **O17.** The takeaway is not shown on the slide by default. A template's takeaway zone keeps today's filling (slide content); the takeaway goes into it only when the user explicitly asks for key messages to be shown (deck flag checked against the user's words, `ppt-builder-intent-fields` phase C, its D9).
- **O18.** The 100× spread rule refused real charts: softened to refused once with an actionable question, the same chart resent unchanged is built with a note (D3). Two written units in one series stay a refusal.

### D1. Checks before the assignment, as `needs_revision` problems

A new `story.py` runs on the plan before `assign.py` (no template fetch, no render) and returns problems in the assigner's shape (`index`, `problem`, `options`), merged into the same `needs_revision` list. So the model sees one revision per call, the D27 next-call rule, the "repeated" flag and the identical-call guard apply unchanged. Checks run on every slide of `slides`, and on the slides a `changes` call inserts, replaces or edits only: an edit is never refused over a slide it does not touch.

### D2. `takeaway` and title (O2, O5–O7)

- `SlidePlan.takeaway: str`, first in the slide schema so the model decides it before the content: "what the audience concludes when they look at this slide, as a full sentence ('Italy weighs twice Spain in headcount, so the hiring plan should start there'). It shapes the slide; it is not the title and need not appear on it." Aliases: `message`, `key_message`, `key_takeaway`.
- Exempt kinds: `cover`, `agenda`, `section`, `closing`, `quote`. The kind is the one the assigner works with (`kind`, else inferred from content).
- Problems (minimal): no takeaway on a non-exempt slide; a takeaway under four words, i.e. a topic label ("Présentation générale"), not a sentence; a takeaway ending with `?` (a question is a topic, not a conclusion); a takeaway equal to the slide's title once normalised (the title points to the takeaway, it is not one) (O13). The option names the remedy with an example built from the slide's own content. **Checked:** presence, word count, final `?`, equality with the title. **Not checked:** whether it holds a verb or asserts anything (no reliable cross-language test for a verbless noun phrase), its length beyond the floor, its truth, its relevance to the slide.
- **Title.** `title` stays the model's: short, written from the takeaway, fitted by the existing title fit check. The code never derives a title from the takeaway. A user who asks for no titles is followed by the model omitting `title` (already optional; the zone stays unfilled). A deck field would only certify the same model decision, so none is added.
- **Speaker notes.** The takeaway is always the first line of the notes, unlabelled, before `Source:` and the model's notes. It also feeds the plan outline (D5).
- **On-slide placement** belongs to `ppt-builder-intent-fields` phase C (its D9, amended 2026-10-15): by default the takeaway is on the slide nowhere but the notes, and a template's takeaway zone is filled as before from the slide's content. Only when the user explicitly asks for key messages to be shown (O17) does the takeaway fill that zone, when the chosen slide has one and it fits. No fallback, no refusal for it.
- **Figures crammed into a title.** A title or subtitle holding three or more numbers (years 1900–2099 not counted) is a problem whose option is a `figures` slide (items `number` + `label`), else a table. It is about titles carrying data, so it stays.

**Prompt guidance** (working rules, always, one paragraph): decide the deck's main message, then each slide's takeaway before its content. Let the takeaway design the slide: the kind that shows it (a comparison → a chart; one striking number → a figures slide with that number big; a trend → a line), only the content that supports it, and the emphasis that proves it (`chart.highlight`, `chart.sort`, `table.total_row`, `items[].trend`). Then write a short title, a few words that point to the takeaway, not the takeaway itself. Leave titles out only when the user asked. Every figure from the documents or the user, with `source`; never invent figures unless the user asked for illustrative data.

### D3. One measure per chart (O1)

Deterministic, per chart:

1. **Written units.** Two different non-empty units among a chart's written values (`45 ans`, `9 sites`; `%` and `M€`) → problem, every time. A bare number does not conflict.
2. **Spread (refused once, O18).** On `column`, `bar`, `line`, `area`, `stacked_column`, a chart without `unit` whose non-zero absolute values span 100× or more → problem the first time, worded as a question: "values from 9 to 2 800 on one axis: do they measure the same thing? If yes, set `unit` (or send the chart again unchanged); if not, split them into a figures slide (items: number + label)". The same chart sent again unchanged (same categories and values, still no `unit`) is built, with a `wide_range_chart` note in "What was built". The "sent before" memory is the one of `figures_unverified` (D4): the previous call's refused slides, read from `history()`. `pie`/`doughnut` exempt (small slices are normal).

The repro chart (45, 2 800, 9, no unit) is refused once by rule 2; a weak model that resends it unchanged gets it built with the note, the user sees the note. Setting `unit` is the escape for a real wide-range measure; a model can also misuse it — not verified.

### D4. Sourced figures (O1, O8, O9)

- **`SlidePlan.source`**, required when the slide holds figures: a `chart`, a `table` with a numeric body cell, or an item with a `number`. Values: a document name, `user` (figures the user typed in the chat), or `illustrative`; loose spellings read through `lexicon` (`utilisateur`, `conversation`, `chat` → `user`; `illustratif`, `fictif`, `exemple` → `illustrative`). Missing → problem. Written to the notes as `Source: …`. The document name is free text: not matched against the library.
- **`illustrative`** is accepted only when a user message of the conversation allows it: a fr/en lexicon (`illustrati*`, `fictif/fictive`, `exemple de données`, `invente/inventé`, `dummy`, `fake`, `sample data`, `made-up`, `placeholder`, `mock`). Otherwise a problem: "the user did not ask for illustrative figures: take them from the documents, or ask the user". Accepted, it is said in the notes (`Illustrative figures, not from the documents.`), as the chart caption's suffix `(illustrative)` / `(illustratif)` in the plan's language, and as an `illustrative_data` note in "What was built". Nothing else on the slide (O9).
- **Spot-check.** Numbers are collected once per call from every user message and every tool result in `history()` (documents read, searched or attached as delivered to the model). A slide passes when at least one of its figures is found; ambiguity always counts as found:
  - **Reading.** `read_number`, extended: space, thin and non-breaking space as thousands separators; comma or dot decimals (a string that reads both ways, `1.234`, counts under both); `%`, currency and unit text ignored; `k`, `M`/`million`, `Md`/`Mds`/`milliard`/`bn` both scaled and as written (`2,8 M€` matches `2.8` and `2 800 000`).
  - **Rounding.** A slide value matches a found one when they are equal once the more precise is rounded to the other's decimals, or within 1 % (`2 784` matches `2 800`, `12.46` matches `12.5`).
  - **Derived.** A slide value also matches when it is the sum of the slide's other values (a total); a share `a/b` or change `(a−b)/b` as a percentage of two found numbers; or the sum or difference of two found numbers from the same message or tool result. Each lookup is a bisection in the sorted found numbers: O(F log F) per slide figure.
  - A non-illustrative slide with none found is a problem once. Resent with the same figures, it is built with a `figures_unverified` note (summary, and notes `Figures not found in the documents read.`): never a dead end, never silent.
- **Verified:** a source is stated; illustrative only with the user's allowance; at least one figure per slide relates to a number the model received. **Not verified:** every figure; that the named document holds them; numbers in bullets. The check is lenient by design: it targets a slide whose figures relate to nothing the model read.
- Cost: one pass over the history text per build call; no I/O, no model call.

### D5. Plan validation: the tool turns the first build into an outline (O3, O10)

`PptBuilderConfig.validate_plan: bool = False`. With it on, and the conversation holding no delivered deck (`deck_delivered(history())` or a stored delivered base), a build call:

1. Runs every check and the assignment (no render). Problems → the usual `needs_revision`: the outline shown is a sound plan.
2. No problem, no proposal answered yet and no valid skip → stores the plan in `cap_ppt_builder_deck_plan` with `proposed = true`, `delivered = false`, and answers (non-error) `status: plan_proposed` with a code-written outline: audience, main message, then `N. kind — title — takeaway — source` per slide. The text: "Nothing was built. Show this outline to the user in their language and ask them to validate or correct it; end your answer; do not call build_presentation again in this answer."
3. A proposal is answered when a user message follows the `plan_proposed` result in `history()`. Then the call builds: the whole deck in `slides`, or `changes` applied to the proposed plan. Any reply counts: the agent applies corrections. A second call before a reply gets the same `plan_proposed` answer (the identical-call guard).

**Explicit skip (O10).** A top-level build argument `skip_plan: str`, described "only when the user's latest message explicitly asks to build without a plan; quote their words". The gate honours it only when the latest user message in `history()` matches a fr/en skip lexicon, through the same lexicon match as the illustrative allowance (`sans plan`, `pas de plan`, `sans valider`, `construis directement`, `no plan`, `without a plan`, `skip the plan`, `build directly`). Else the outline is returned with one added line: "the user's latest message does not ask to skip the plan". A skip is never inferred from the lexicon alone: without the argument, plan first.

Once a deck is delivered, `changes` and new decks of the conversation never wait. With the setting off nothing changes and `skip_plan` is ignored.

**One prompt for both settings.** The working rules do not mention the setting: the gate's instructions arrive in the tool result, only when it applies; `skip_plan` is a schema line. The rule "ask to validate an outline only when the user asked" stays, so off keeps today's behaviour and on adds no prompt variant (O4).

Rejected:

- **Prompt only** ("present the plan and wait"): weak models build anyway; nothing enforces it.
- **A `plan_validated` flag set by the model**: self-certified; Mistral would set it on the first call. `skip_plan` differs: the user's own words must hold the request.
- **A separate `propose_plan` tool**: a second large plan schema in every call, one more tool to choose wrongly, and the plan written twice.

### D6. Deck fields, edits, summary

- `DeckPlan.audience`, `DeckPlan.main_message` (optional; alias `message` at deck level; the outline shows them, `—` when absent); top-level build arguments, kept from the base when a `changes` call omits them (as `file_name`).
- `changes.py`: `takeaway`, `source` in `_FIELDS`, `takeaway` in `_SLIDE_KEYS` and `CLEARABLE`; `unchanged` compares them. An edit of `takeaway` re-renders the notes only.
- `BuildNoteCode` gains `illustrative_data`, `figures_unverified`, `wide_range_chart`; frontend `types.ts`, `DeckSummaryButton.tsx`, locales.
- Notes lines (`Source:`, illustrative, unverified) are written in the plan's language, like the caption suffix.

### D6. Unsourced figures said truthfully (owner decision 2026-10-17 overnight)

Revision evals (mistral-small) showed invented figures tagged `source: user` and replies claiming "no assumption": the second send of an unverified slide is built (D4), and the agent was never told again. The refusal now says not to resend made-up figures, and the delivery carries one line per such slide (those the call changed) telling the agent to present them as to be confirmed. One rule, consistent with D3: concrete figures the user did not give are asked for, never invented, unless illustrative data was asked for. No new check: the soft spot-check stays soft (real derived figures still build).

## Risks / Trade-offs

- [More revision rounds on weak models] → checks run before the assignment and share one revision; each option is a concrete edit; measured in the eval (first-call success, rounds per deck).
- [False refusals: wide-range real data, computed figures] → `unit` escape and second send built with a note (D3); lenient matching and second send built with a note (D4).
- [Takeaway written but not used to design the slide] → not verifiable; the eval compares kind and emphasis choices with and without takeaways.
- [Schema growth: `takeaway`, `source`, `audience`, `main_message`, `skip_plan`] → one-line descriptions; tool-schema size measured.
- [Allowance or skip lexicon misses a wording] → illustrative: the revision tells the agent to ask the user; skip: the user gets the outline and can answer "build it".

## Migration Plan

No table or setting migration: `validate_plan` defaults off, `proposed` is a JSON field of the stored plan. Unreleased capability: a line in its migration note (impact none). Plans stored before this change have no `takeaway`/`source`; per D1, a `changes` call checks only the slides it touches.

## Open Questions

None: the owner's answers of 2026-10-15 (O12–O18) closed D2, D3, D4 and D5.
