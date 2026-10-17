## ADDED Requirements

### Requirement: Every content slide has a takeaway

The system SHALL require a `takeaway` on every plan slide whose kind is not `cover`, `agenda`, `section`, `closing` or `quote`: the conclusion the audience draws from the slide, as a sentence. The system SHALL return `needs_revision` for that slide when the takeaway is missing, shorter than four words, ends with a question mark, or equals the slide's title once normalised, and SHALL NOT judge it further. The system SHALL NOT write the takeaway on the slide unless the user explicitly asked for key messages to be shown (`ppt-builder-intent-fields`, requirement "Slide takeaway"). The system SHALL NOT derive the slide's title from the takeaway: it SHALL use the `title` the model sent, and leave the title unfilled when none is sent. The system MUST write the takeaway as the first line of the slide's speaker notes. The system SHALL return `needs_revision` for a title or subtitle holding three or more numbers (years not counted), offering a figures slide. These checks SHALL run before the slide assignment, and a `changes` call SHALL be checked on the slides it touches only.

#### Scenario: Topic label as takeaway

- **WHEN** the model sends a bullets slide with `takeaway: "Présentation générale"`
- **THEN** no deck is built and the `needs_revision` entry for that slide asks for what the audience should conclude, as a sentence

#### Scenario: Takeaway that repeats the title

- **WHEN** the model sends a bullets slide with `title: "Our results in 2025"` and `takeaway: "Our results in 2025"`
- **THEN** no deck is built and the slide's problem asks for the conclusion the audience draws, the title pointing to it

#### Scenario: Takeaway shapes the slide, title stays short

- **WHEN** the model sends a chart slide with `title: "Effectifs par pays"` and `takeaway: "L'Italie pèse deux fois l'Espagne en effectifs, le plan de recrutement doit commencer là"`
- **THEN** the slide's title reads "Effectifs par pays" and its speaker notes start with the takeaway

#### Scenario: User asked for no titles

- **WHEN** the model sends content slides with takeaways and no `title`
- **THEN** the slides are built without a title and each slide's speaker notes start with its takeaway

#### Scenario: Exempt kinds

- **WHEN** the model sends a cover and a section slide without `takeaway`
- **THEN** neither slide is refused for it

#### Scenario: Figures crammed into a subtitle

- **WHEN** the model sends a cover subtitle "45 ans, 2 800 salariés, 9 sites"
- **THEN** no deck is built and the slide's options include a figures slide with those numbers as items

### Requirement: A chart holds one measure

The system SHALL return `needs_revision` for a chart whose values are written with two different units, every time it is sent. The system SHALL return `needs_revision` once for a `column`, `bar`, `line`, `area` or `stacked_column` chart without `unit` whose non-zero values span a ratio of 100 or more, asking whether the values measure the same thing and offering a `unit` for one measure or a figures slide for different ones; when the same chart is sent again unchanged, the system SHALL build it and record a `wide_range_chart` note in "What was built". Pie and doughnut charts SHALL be exempt from the spread rule.

#### Scenario: Mixed measures on one axis

- **WHEN** the model sends a column chart with categories "Years", "Employees", "Sites" and values 45, 2800, 9 and no unit
- **THEN** no deck is built and the slide's problem asks whether the values measure the same thing, with a figures slide or a unit naming the one measure as options

#### Scenario: Wide-range chart confirmed by a resend

- **GIVEN** a column chart refused for its spread
- **WHEN** the model sends the same chart again unchanged
- **THEN** the deck is built and the summary holds `wide_range_chart`

#### Scenario: One wide-range measure

- **WHEN** the same values are sent with `unit: "employees"`
- **THEN** the chart is built

#### Scenario: Two written units

- **WHEN** a series holds "12 %" and "3 M€"
- **THEN** no deck is built and the problem names both units; **WHEN** the same chart is sent again **THEN** it is refused again

### Requirement: Figures are sourced

The system SHALL require a `source` on every slide holding a chart, a table with a numeric body cell, or an item with a number: a document name, `user` (figures the user typed in the conversation), or `illustrative`, and SHALL write it to the speaker notes. The system SHALL accept `illustrative` only when a user message of the conversation allows illustrative data, and SHALL then say so in the speaker notes, in the chart caption when the slide has a chart, and with an `illustrative_data` note in "What was built", and nowhere else on the slide. The system SHALL count a slide's figure as found when it matches a number of any user message or tool result the model received, tolerating thousands separators, comma or dot decimals, units, scale suffixes (k, M, Md, bn) and rounding, or when it is the total of the slide's other values, a share or change of two found numbers, or the sum or difference of two found numbers from one message or tool result; a reading that is ambiguous SHALL count as found. The system SHALL return `needs_revision` once for a non-illustrative slide none of whose figures is found, and SHALL build the same figures sent again with a `figures_unverified` note in "What was built" and in the speaker notes, and a line in the delivery telling the agent to present them to the user as to be confirmed, never as the user's. The system SHALL NOT claim to verify every figure or the named document.

#### Scenario: Missing source

- **WHEN** the model sends a chart slide without `source`
- **THEN** no deck is built and the slide's problem asks for the document the figures come from, `user`, or illustrative data if the user asked for it

#### Scenario: Illustrative data not allowed

- **GIVEN** a conversation whose user messages never ask for illustrative or made-up data
- **WHEN** the model sends a pie with `source: "illustrative"`
- **THEN** no deck is built and the problem tells the agent to take the figures from the documents or ask the user

#### Scenario: Illustrative data allowed

- **GIVEN** the user asked "mets des données fictives"
- **WHEN** the model sends a chart with `source: "illustratif"`
- **THEN** the deck is built, the chart caption ends with "(illustratif)", the notes say the figures are illustrative and the summary holds `illustrative_data`

#### Scenario: Figures found nowhere

- **GIVEN** a conversation whose only numbers are "2 800" and "9"
- **WHEN** the model sends a pie with those values and `source: "rapport 2025"`
- **THEN** no deck is built the first time, the refusal saying never to resend figures the model made up; **WHEN** it sends the same values again **THEN** the deck is built, the summary holds `figures_unverified` and the delivery tells the agent to present them as to be confirmed

#### Scenario: Figures from a document

- **GIVEN** a tool result in the conversation containing "2 800 salariés"
- **WHEN** the model sends a figures slide with an item numbered "2800" and `source: "rapport 2025"`
- **THEN** the slide passes the check

#### Scenario: Figures typed by the user

- **GIVEN** the user wrote "on a fait 12,5 % de croissance et 3,2 M€ de CA"
- **WHEN** the model sends a figures slide with items `12.5 %` and `3 200 000 €` and `source: "user"`
- **THEN** the slide passes the check

#### Scenario: Computed share

- **GIVEN** a tool result holding "Italie 1 200" and "total 2 800"
- **WHEN** the model sends a pie with the value 43 % for Italy
- **THEN** the slide passes the check

### Requirement: Plan validation before the first build

The capability SHALL offer one setting, "Validate the plan before building", off by default. When it is off, the system SHALL behave as without it. When it is on and the conversation holds no delivered deck, the system SHALL answer a `build_presentation` call whose plan has no problem with a `plan_proposed` result holding an outline written by the code — audience, main message, and per slide its kind, title, takeaway and source — SHALL store that plan, and SHALL NOT build a deck until a user message follows that result. After that message, the system SHALL build a whole plan sent in `slides` or apply `changes` to the proposed plan. A plan with problems SHALL get `needs_revision` instead of an outline. The system SHALL build without an outline when the call carries `skip_plan` and the latest user message explicitly asks to build without a plan, and SHALL return the outline when `skip_plan` is sent without such a request. Changes to a delivered deck SHALL NOT wait for validation. The working rules SHALL be the same whatever the setting.

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

- **GIVEN** the setting is on and the latest user message says "construis-la directement, sans plan"
- **WHEN** the model sends a sound plan with `skip_plan` quoting it
- **THEN** the deck is built in that call

#### Scenario: Skip not asked

- **GIVEN** the setting is on and the latest user message does not ask to skip the plan
- **WHEN** the model sends a sound plan with `skip_plan`
- **THEN** no deck is built and the result is `plan_proposed`

#### Scenario: Edit of a delivered deck

- **GIVEN** the setting is on and a deck delivered in the conversation
- **WHEN** the model sends `changes` for slide 2
- **THEN** the deck is rebuilt without an outline
