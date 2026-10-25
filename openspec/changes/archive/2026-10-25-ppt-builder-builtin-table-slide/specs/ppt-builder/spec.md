## ADDED Requirements

### Requirement: The built-in template offers a data table slide

The built-in Fred template SHALL hold one example slide whose table the analysis reads as a data table: a header row flagged as such, empty or sample body cells, no merged cells, no per-cell fill, border or typeface, and the table style the deck declares as its default. Its stored analysis SHALL include that slide as a pattern of kind `table`. Tables sent for an agent without a configured template SHALL be filled on that slide under the same fit, column, row, shrink and continuation rules as a customer template's table, and SHALL NOT be refused for lack of a table slide.

#### Scenario: Built-in analysis lists a table slide

- **GIVEN** the shipped built-in template
- **WHEN** its stored analysis is regenerated
- **THEN** it holds an included pattern of kind `table` whose table zone has a header row and five columns, and no pattern is excluded for `table`

#### Scenario: Table field offered on the default configuration

- **GIVEN** an agent without a configured template
- **WHEN** the build tool's schema and description are produced
- **THEN** the slide schema has a `table` field and the description gives the table's columns and room

#### Scenario: Common comparison built on the built-in deck

- **GIVEN** an agent without a configured template
- **WHEN** the model sends a slide with a `table` of 5 columns (a criterion and four offers) and 6 rows of short cells
- **THEN** the deck is delivered with that table on the built-in table slide, header in the header row, and no `needs_revision`

#### Scenario: Table taller than the built-in slide

- **WHEN** the model sends more rows than one built-in table slide holds, but no more than two hold
- **THEN** the table continues on a second table slide with its header repeated, and the agent is told so

#### Scenario: Table wider than the built-in slide

- **WHEN** the model sends 6 columns on the built-in deck
- **THEN** no deck is built and `needs_revision` names the limit (columns given vs max 5)

#### Scenario: Built-in table follows the theme

- **WHEN** a table is rendered on the built-in deck
- **THEN** the delivered table references the deck's table style, carries no literal colour or typeface in its cells, and no template cell text remains
