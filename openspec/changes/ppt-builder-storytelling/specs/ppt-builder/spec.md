## ADDED Requirements

### Requirement: Every content slide states its key message

The system SHALL require a `message` on every plan slide whose kind is not `cover`, `agenda`, `section`, `closing` or `quote`, and SHALL return `needs_revision` for that slide when the message is missing or shorter than four words. With the deck's `titles` at its default `message`, the system SHALL write the message as the slide's title and SHALL tell the agent when a sent `title` was not used. With `titles: custom` the system SHALL use the slide's `title`, and with `titles: none` it SHALL leave the title unfilled; in both cases the system MUST write the message at the start of the speaker notes. The system SHALL return `needs_revision` for a title or subtitle holding three or more numbers (years not counted), offering a figures slide. These checks SHALL run before the slide assignment, and a `changes` call SHALL be checked on the slides it touches only.

#### Scenario: Topic title

- **WHEN** the model sends a bullets slide with `message: "Présentation générale"`
- **THEN** no deck is built and the `needs_revision` entry for that slide asks for the slide's point as a sentence

#### Scenario: Message becomes the title

- **WHEN** the model sends a chart slide with `title: "Effectifs"` and `message: "L'Italie pèse deux fois l'Espagne en effectifs"`
- **THEN** the slide's title reads the message and the agent note says the sent title was not used

#### Scenario: User asked for no titles

- **WHEN** the model sends a deck with `titles: none`
- **THEN** content slides are built without a title and each slide's speaker notes start with its key message

#### Scenario: Exempt kinds

- **WHEN** the model sends a cover and a section slide without `message`
- **THEN** neither slide is refused for it

#### Scenario: Figures crammed into a subtitle

- **WHEN** the model sends a cover subtitle "45 ans, 2 800 salariés, 9 sites"
- **THEN** no deck is built and the slide's options include a figures slide with those numbers as items

### Requirement: A chart holds one measure

The system SHALL return `needs_revision` for a chart whose values are written with two different units, and for a `column`, `bar`, `line`, `area` or `stacked_column` chart without `unit` whose non-zero values span a ratio of 100 or more. The revision SHALL offer a figures slide for values that measure different things and a `unit` for values that are one measure. Pie and doughnut charts SHALL be exempt from the spread rule.

#### Scenario: Mixed measures on one axis

- **WHEN** the model sends a column chart with categories "Years", "Employees", "Sites" and values 45, 2800, 9 and no unit
- **THEN** no deck is built and the slide's options are a figures slide or a unit naming the one measure

#### Scenario: One wide-range measure

- **WHEN** the same values are sent with `unit: "employees"`
- **THEN** the chart is built

#### Scenario: Two written units

- **WHEN** a series holds "12 %" and "3 M€"
- **THEN** no deck is built and the problem names both units

### Requirement: Figures are sourced

The system SHALL require a `source` on every slide holding a chart, a table with a numeric body cell, or an item with a number: a document name, `user`, or `illustrative`, and SHALL write it to the speaker notes. The system SHALL accept `illustrative` only when a user message of the conversation allows illustrative data, and SHALL then say so in the speaker notes, in the chart caption when the slide has a chart, and with an `illustrative_data` note in "What was built". The system SHALL return `needs_revision` once for a non-illustrative slide none of whose figures appears in the user messages or tool results the model received, and SHALL build the same figures sent again with a `figures_unverified` note in "What was built" and in the speaker notes. The system SHALL NOT claim to verify every figure or the named document.

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

- **GIVEN** a document read in the conversation that holds none of the values 30, 45, 25
- **WHEN** the model sends a pie with those values and `source: "rapport 2025"`
- **THEN** no deck is built the first time; **WHEN** it sends the same values again **THEN** the deck is built and the summary holds `figures_unverified`

#### Scenario: Figures from a document

- **GIVEN** a tool result in the conversation containing "2 800 salariés"
- **WHEN** the model sends a figures slide with an item numbered "2800" and `source: "rapport 2025"`
- **THEN** the slide passes the check

### Requirement: Plan validation before the first build

The capability SHALL offer one setting, "Validate the plan before building", off by default. When it is off, the system SHALL behave as without it. When it is on and the conversation holds no delivered deck, the system SHALL answer a `build_presentation` call whose plan has no problem with a `plan_proposed` result holding an outline written by the code — audience, main message, and per slide its kind, key message and source — SHALL store that plan, and SHALL NOT build a deck until a user message follows that result. After that message, the system SHALL build a whole plan sent in `slides` or apply `changes` to the proposed plan. A plan with problems SHALL get `needs_revision` instead of an outline. Changes to a delivered deck SHALL NOT wait for validation. The working rules SHALL be the same whatever the setting.

#### Scenario: Setting off

- **WHEN** the setting is off and the model sends a sound plan
- **THEN** the deck is built in that call

#### Scenario: Outline first

- **GIVEN** the setting is on and no deck delivered in the conversation
- **WHEN** the model sends a sound five-slide plan
- **THEN** no deck is built, the result's status is `plan_proposed` and the outline lists five lines with kind, key message and source

#### Scenario: Second call before the user answers

- **WHEN** the model calls `build_presentation` again in the same answer after `plan_proposed`
- **THEN** no deck is built and the result repeats the proposal

#### Scenario: Built after the user's correction

- **GIVEN** a `plan_proposed` result followed by the user's "remove slide 3"
- **WHEN** the model sends `changes` deleting slide 3
- **THEN** the deck is built from the proposed plan without slide 3

#### Scenario: Edit of a delivered deck

- **GIVEN** the setting is on and a deck delivered in the conversation
- **WHEN** the model sends `changes` for slide 2
- **THEN** the deck is rebuilt without an outline
