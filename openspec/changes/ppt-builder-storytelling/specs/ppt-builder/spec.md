## ADDED Requirements

### Requirement: Every content slide has a takeaway

The system SHALL accept a `takeaway` on every plan slide: the conclusion the audience draws from the slide, as a sentence, asked for by the working rules on every slide whose kind is not `cover`, `agenda`, `section`, `closing` or `quote`. The system SHALL NOT refuse a slide for its takeaway (missing, short, a question, equal to the title) nor for numbers in its title or subtitle: judging them is the agent's. The system SHALL NOT write the takeaway on the slide unless the user explicitly asked for key messages to be shown (`ppt-builder-intent-fields`, requirement "Slide takeaway"). The system SHALL NOT derive the slide's title from the takeaway: it SHALL use the `title` the model sent, and leave the title unfilled when none is sent. The system MUST write the takeaway as the first line of the slide's speaker notes.

#### Scenario: Takeaway shapes the slide, title stays short

- **WHEN** the model sends a chart slide with `title: "Effectifs par pays"` and `takeaway: "L'Italie pèse deux fois l'Espagne en effectifs, le plan de recrutement doit commencer là"`
- **THEN** the slide's title reads "Effectifs par pays" and its speaker notes start with the takeaway

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

The system SHALL return `needs_revision` for a chart whose values are written with two different units, every time it is sent; a scatter or bubble chart SHALL be checked per axis. This check SHALL run before the slide assignment, and a `changes` call SHALL be checked on the slides it touches only. The system SHALL NOT refuse a chart for the spread of its values or, on a slide with several charts, for a missing chart title.

#### Scenario: Two written units

- **WHEN** a series holds "12 %" and "3 M€"
- **THEN** no deck is built and the problem names both units; **WHEN** the same chart is sent again **THEN** it is refused again

#### Scenario: Wide-range values

- **WHEN** the model sends a column chart with values 45, 2800, 9 and no unit
- **THEN** the chart is built as sent, without a note

### Requirement: Figures are sourced

The system SHALL write a slide's `source` to its speaker notes: a document name, `user` (figures the user typed in the conversation), or `illustrative`. When the source is `illustrative`, the system SHALL say so in the speaker notes, in the chart caption when the slide has a chart, and with an `illustrative_data` note in "What was built", and nowhere else on the slide. The system SHALL NOT refuse a slide for a missing source or an illustrative one, and SHALL NOT check the slide's figures against the conversation: where figures come from is the agent's, by the working rules. The system SHALL NOT claim to verify any figure.

#### Scenario: Illustrative data

- **WHEN** the model sends a chart with `source: "illustratif"`, whatever the user's language
- **THEN** the deck is built, the chart caption ends with "(illustratif)", the notes say the figures are illustrative and the summary holds `illustrative_data`

#### Scenario: Figures without a source or found nowhere

- **WHEN** the model sends a roadmap table (Phase 1, T3, Lot 3) or figures found in no message, with or without `source`
- **THEN** the deck is built as sent, without a note

### Requirement: Plan validation before the first build

The capability SHALL offer one setting, "Validate the plan before building", off by default. When it is off, the system SHALL behave as without it. When it is on and the conversation holds no delivered deck, the system SHALL answer a `build_presentation` call whose plan has no problem with a `plan_proposed` result holding an outline written by the code — audience, main message, and per slide its kind, title, takeaway and source — SHALL store that plan, and SHALL NOT build a deck until a user message follows that result. After that message, the system SHALL build a whole plan sent in `slides` or apply `changes` to the proposed plan. A plan with problems SHALL get `needs_revision` instead of an outline. The system SHALL build without an outline when the call carries `skip_plan` (the field asks the model to quote the user's request; the system SHALL NOT match the user's words against a word list), and SHALL return the outline when it is left out. Changes to a delivered deck SHALL NOT wait for validation. The working rules SHALL be the same whatever the setting.

#### Scenario: Setting off

- **WHEN** the setting is off and the model sends a sound plan
- **THEN** the deck is built in that call

#### Scenario: Outline first

- **GIVEN** the setting is on and no deck delivered in the conversation
- **WHEN** the model sends a sound five-slide plan
- **THEN** no deck is built, the result's status is `plan_proposed` and the outline lists five lines with kind, title, takeaway and source

#### Scenario: Second call before the user answers

- **WHEN** the model calls `build_presentation` again in the same answer after `plan_proposed`
- **THEN** no deck is built and the result repeats the proposal

#### Scenario: Built after the user's correction

- **GIVEN** a `plan_proposed` result followed by the user's "remove slide 3"
- **WHEN** the model sends `changes` deleting slide 3
- **THEN** the deck is built from the proposed plan without slide 3

#### Scenario: User asked to skip the plan

- **GIVEN** the setting is on and the latest user message says "hazlo directamente, sin plan"
- **WHEN** the model sends a sound plan with `skip_plan` quoting it
- **THEN** the deck is built in that call

#### Scenario: Skip not sent

- **GIVEN** the setting is on and the latest user message says "sans plan"
- **WHEN** the model sends a sound plan without `skip_plan`
- **THEN** no deck is built and the result is `plan_proposed`

#### Scenario: Edit of a delivered deck

- **GIVEN** the setting is on and a deck delivered in the conversation
- **WHEN** the model sends `changes` for slide 2
- **THEN** the deck is rebuilt without an outline
