## ADDED Requirements

### Requirement: Every content slide has a takeaway

The system SHALL accept a `takeaway` on every plan slide: the conclusion the audience draws from the slide, as a sentence, asked for by the working rules on every slide whose kind is not `cover`, `agenda`, `section`, `closing` or `quote`; the working rules and the field descriptions ask for the content slide's title as that conclusion in a short sentence (a claim, not a topic). The system SHALL NOT refuse a slide for its takeaway (missing, short, a question, equal to the title) nor for numbers in its title or subtitle: judging them is the agent's. The system SHALL NOT write the takeaway on the slide unless the user explicitly asked for key messages to be shown (`ppt-builder-intent-fields`, requirement "Slide takeaway"). The system SHALL NOT derive the slide's title from the takeaway: it SHALL use the `title` the model sent, and leave the title unfilled when none is sent. The system MUST write the takeaway as the first line of the slide's speaker notes.

#### Scenario: Takeaway shapes the slide, title states it short

- **WHEN** the model sends a chart slide with `title: "L'Italie pèse deux fois l'Espagne"` and `takeaway: "L'Italie pèse deux fois l'Espagne en effectifs, le plan de recrutement doit commencer là"`
- **THEN** the slide's title reads "L'Italie pèse deux fois l'Espagne" and its speaker notes start with the takeaway

#### Scenario: User asked for no titles

- **WHEN** the model sends content slides with takeaways and no `title`
- **THEN** the slides are built without a title and each slide's speaker notes start with its takeaway

#### Scenario: The takeaway is the agent's

- **WHEN** the model sends a bullets slide with no takeaway, or with `takeaway: "Présentation générale"`
- **THEN** the slide is not refused for it

#### Scenario: Dates, versions and standards in a title

- **WHEN** the model sends the title "Release 2.1 vs 3.0 vs 4.0" or "Top 10 risks for 5G and ISO 27001"
- **THEN** the slide is not refused for it

### Requirement: A chart holds one measure

Before that check, the system SHALL put a category chart's amounts in one scale of their unit: values written with scale prefixes of one base unit (k€, M€, Md€; k$, M$; K, M, B, bn, Md) SHALL be converted to the scale that puts the largest value between 1 and 999 (the chart's own `unit` when it names one of them), and amounts of a single unit reaching 10 000 or more (1 250 000 €), or 1 000 or more of a unit that already carries a scale (2 500 k€), SHALL be shown in such a scale, a stacked chart measured by its largest stacked total, and a chart title naming the old unit naming the new one; the converted values carry that unit in their number format, data labels included, its billion prefix spelled in the deck's language (Md in French, bn in English), with the decimals the converted values carry (at most 2, none when all are whole); an axis's ticks SHALL be round, at most five intervals, with the decimals of their step (200, not 200,00), and its 0 SHALL read "0". An amount of 10 000 or more written in slide text with a currency sign SHALL be shortened to that scale too, in the deck's decimal separator (520 000 € → 520 k€). A bare number beside several scales SHALL NOT be converted. The system SHALL return `needs_revision` for a chart whose values are still written with two different units, every time it is sent; a scatter or bubble chart SHALL be checked per axis. This check SHALL run before the slide assignment, and a `changes` call SHALL be checked on the slides it touches only. The system SHALL NOT refuse a chart for the spread of its values or, on a slide with several charts, for a missing chart title.

#### Scenario: Two written units

- **WHEN** a series holds "12 %" and "3 M€"
- **THEN** no deck is built and the problem names both units; **WHEN** the same chart is sent again **THEN** it is refused again

#### Scenario: Two scales of one unit

- **WHEN** a series holds "500 k€" and "2 M€"
- **THEN** the deck is built and the chart plots 0.5 and 2 with the number format `M€`

#### Scenario: Large plain amounts

- **WHEN** a series holds "1 250 000 €" and "800 000 €" in a French deck
- **THEN** the chart plots 1.25 and 0.8 in `M€`; "1 500 €" and "2 300 €" are plotted as written

#### Scenario: A stacked chart is scaled by its totals

- **WHEN** a stacked bar chart titled "CA (k€)" in `k€` holds parts of at most 1 200 whose totals reach 1 940
- **THEN** it plots them in `M€` and its title reads "CA (M€)"

#### Scenario: The largest amount sets the scale

- **WHEN** a chart in `€` holds 2 450 000, 1 380 000, 640 000, 215 000 and 48 500
- **THEN** it plots them in `M€` (2,45 M€, not 2 450,0 k€) and its value axis starts at "0"

#### Scenario: Wide-range values

- **WHEN** the model sends a column chart with values 45, 2800, 9 and no unit
- **THEN** the chart is built as sent, without a note

### Requirement: Figures are sourced

The system SHALL write a slide's `source` to its speaker notes: a document name, `user` (figures the user typed in the conversation), or `illustrative`. When the source is `illustrative`, the system SHALL say so in the speaker notes, in the chart caption when the slide has a chart, and with an `illustrative_data` note in "What was built", and nowhere else on the slide. The system SHALL NOT refuse a slide for a missing source or an illustrative one, and SHALL NOT check the slide's figures against the conversation: where figures come from is the agent's, by the working rules. The system SHALL NOT claim to verify any figure. The working rules and field descriptions SHALL ask for `source` only for content from the user's documents or data, and SHALL ask to leave it out for general knowledge.

#### Scenario: Illustrative data

- **WHEN** the model sends a chart with `source: "illustratif"`, whatever the user's language
- **THEN** the deck is built, the chart caption ends with "(illustratif)", the notes say the figures are illustrative and the summary holds `illustrative_data`

#### Scenario: Figures without a source or found nowhere

- **WHEN** the model sends a roadmap table (Phase 1, T3, Lot 3) or figures found in no message, with or without `source`
- **THEN** the deck is built as sent, without a note

### Requirement: Plan validation before the first build

The capability SHALL offer one setting, "Validate the plan before building", off by default. When it is off, the system SHALL behave as without it. When it is on and the conversation holds no delivered deck, the system SHALL answer a `build_presentation` call whose plan has no problem with a `plan_proposed` result holding an outline written by the code — audience, main message, and per slide its kind, title, takeaway and source, followed by the assignment notes the build of that plan would give (the delivery's notes, each fix worded as the user's choice — "If the user wants …" — never as a call to make now, its slides numbered as the outline numbers them) — SHALL store that plan, and SHALL NOT build a deck until the user approved it. Where the model call offers the platform `ask_user` tool, the plan SHALL be approved only by the approval choice of the question that follows the proposal ("Approuver" or "Approve", in the plan's language, beside a free answer); a free answer SHALL be read as the changes the user wants and SHALL never approve the plan. Without `ask_user`, a user message following the result SHALL be the answer. Once approved, the system SHALL build a whole plan sent in `slides` or apply `changes` to the proposed plan. A plan with problems SHALL get `needs_revision` instead of an outline. The system SHALL build without an outline when the call carries `skip_plan` and its quote appears, word for word, in the user's latest message (ignoring case, spacing, quote marks and punctuation; the system SHALL NOT match the user's words against a word list), and SHALL return the outline when it is left out or quotes words the user did not write. Changes to a delivered deck SHALL NOT wait for validation. With the setting on, the working rules and the `plan_proposed` result SHALL tell the agent to ask for approval with `ask_user`, the outline as its question, or, without it, to show the outline, end its answer, and never call `build_presentation` again in that answer.

#### Scenario: Setting off

- **WHEN** the setting is off and the model sends a sound plan
- **THEN** the deck is built in that call

#### Scenario: Outline first

- **GIVEN** the setting is on and no deck delivered in the conversation
- **WHEN** the model sends a sound five-slide plan
- **THEN** no deck is built, the result's status is `plan_proposed` and the outline lists five lines with kind, title, takeaway and source

#### Scenario: Outline with a fallback note

- **GIVEN** the setting is on and no deck delivered in the conversation
- **WHEN** the model sends a plan whose second slide asks for kind `closing`
- **THEN** the outline lists that slide as `section` and the result holds the note the delivery would give, its fix worded for the user ("built as 'section' instead of 'closing' … If the user wants it as the closing slide: move it to the end")

#### Scenario: Second call before the user answers

- **WHEN** the model calls `build_presentation` again in the same answer after `plan_proposed`
- **THEN** no deck is built and the result repeats the proposal

#### Scenario: Built after the user's correction

- **GIVEN** a `plan_proposed` result followed by the user's "remove slide 3"
- **WHEN** the model sends `changes` deleting slide 3
- **THEN** the deck is built from the proposed plan without slide 3

#### Scenario: Approved with the button

- **GIVEN** a `plan_proposed` result and the model call offers `ask_user`
- **WHEN** the agent's next model call is sent
- **THEN** it can only call `ask_user`, whose choices are replaced by the one approval choice and a free answer
- **WHEN** the user picks the approval choice
- **THEN** the next model call can only call `build_presentation`, and the deck is built

#### Scenario: Free answer to the approval question

- **GIVEN** a `plan_proposed` result and the user's free answer "remove slide 3" to its approval question
- **WHEN** the model sends `changes` deleting slide 3
- **THEN** no deck is built and the revised plan is proposed for approval

#### Scenario: User asked to skip the plan

- **GIVEN** the setting is on and the latest user message says "hazlo directamente, sin plan"
- **WHEN** the model sends a sound plan with `skip_plan` quoting it
- **THEN** the deck is built in that call

#### Scenario: Skip quote the user never wrote

- **GIVEN** the setting is on and the latest user message does not say "sans validation intermédiaire"
- **WHEN** the model sends a sound plan with `skip_plan` "Prépare la présentation sans validation intermédiaire"
- **THEN** no deck is built and the result is `plan_proposed`

#### Scenario: Skip not sent

- **GIVEN** the setting is on and the latest user message says "sans plan"
- **WHEN** the model sends a sound plan without `skip_plan`
- **THEN** no deck is built and the result is `plan_proposed`

#### Scenario: Edit of a delivered deck

- **GIVEN** the setting is on and a deck delivered in the conversation
- **WHEN** the model sends `changes` for slide 2
- **THEN** the deck is rebuilt without an outline

### Requirement: A proposal or a delivery ends the answer

After a `build_presentation` result that delivers a deck, or proposes a plan without `ask_user` offered, every later model call of the same answer SHALL be sent with `tool_choice="none"`, so the agent can only reply to the user; the user's next message SHALL lift it. A proposal with `ask_user` offered SHALL be followed by its approval question (see Plan validation); a skipped question SHALL end the answer the same way. A `needs_revision` result or an error SHALL NOT end the answer, so the agent can still call again.

#### Scenario: Plan proposed

- **GIVEN** a `plan_proposed` result, no `ask_user` offered and no user message after it
- **WHEN** the agent's next model call is sent
- **THEN** it carries `tool_choice="none"` and the agent answers with the outline

#### Scenario: Deck delivered with variety notes

- **GIVEN** a delivered deck whose result carries variety notes, and no user message after it
- **WHEN** the agent's next model call is sent
- **THEN** it carries `tool_choice="none"`, so the deck is not rebuilt in that answer

#### Scenario: Revision or failure

- **GIVEN** a `needs_revision` or error result in the current answer
- **WHEN** the agent's next model call is sent
- **THEN** its tools are unchanged and it can call `build_presentation` again

#### Scenario: Next user message

- **GIVEN** a proposal or a delivery in an earlier answer
- **WHEN** the user sends a new message
- **THEN** the model call for that message has the tools again
