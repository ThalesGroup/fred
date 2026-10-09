## Purpose

PPT Filler lets authors define fields and instructions in PowerPoint templates and reliably fill those fields from an agent conversation.

## Requirements

### Requirement: Equivalent single and double brace markers

PPT Filler SHALL recognize `{key}` and `{{key}}` as the same case-sensitive key in slide content and authoring notes. Leading and trailing key whitespace SHALL be trimmed. Keys SHALL contain non-whitespace content and no braces. Only balanced single or double brace delimiters SHALL be recognized; malformed delimiters SHALL NOT yield partial matches.

#### Scenario: Syntax differs between slide and notes

- **WHEN** slide content uses `{name}` with notes headed `{{name}}:`, or the reverse
- **THEN** analysis associates the field with its description without a missing-key or missing-description error
- **AND** filling replaces the whole marker without leftover braces

#### Scenario: Both forms repeat the same field

- **WHEN** a slide contains `{name}` and `{{ name }}` and its notes describe `name`
- **THEN** analysis returns one field named `name`
- **AND** filling gives both occurrences the same value

#### Scenario: Malformed sequences

- **WHEN** slide content contains `{name`, `name}`, `{{name}`, `{name}}`, `{{{name}}}`, `{outer {inner}}`, `{}`, `{{}}`, or whitespace-only markers
- **THEN** these sequences do not create fields and are left unchanged during text filling

### Requirement: Notes headers use the same marker grammar

An authoring-note header SHALL consist only of one or more supported markers separated by commas, optional surrounding whitespace, and a final colon. Single and double brace markers SHALL be mixable in one header. Inline mentions SHALL remain description text. Content after the presenter-note separator SHALL remain untouched.

#### Scenario: Mixed multi-key header

- **WHEN** notes contain `{first}, {{last}}:` followed by a description and metadata
- **THEN** both fields receive the same description and metadata

#### Scenario: Inline mentions and presenter notes

- **WHEN** a description mentions `{name}` or `{{name}}` inside a sentence and presenter notes after `---` contain either form
- **THEN** inline mentions do not introduce headers
- **AND** presenter notes are preserved verbatim in the filled deck

### Requirement: Analysis and filling agree for text and image fields

Both marker forms SHALL work in existing supported locations and when split across text runs within a paragraph. Text filling SHALL preserve current formatting behavior. Image markers SHALL retain existing placement and location validation behavior. The normalized field schema and tool inputs SHALL remain compatible with existing valid double-brace templates.

#### Scenario: Split markers and text locations

- **WHEN** either marker form is split across runs in a text box, table cell, or grouped text shape
- **THEN** analysis discovers the same key that text filling replaces
- **AND** static surrounding text and current inline Markdown behavior are preserved

#### Scenario: Image marker syntax

- **WHEN** a supported shape uses either marker form for a field declared as an image
- **THEN** analysis and filling identify the same placement box and normalized key
- **AND** an image field in a table cell still reports the existing invalid-location error

### Requirement: Author help matches supported syntax

English and French PPT Filler help and the capability README SHALL document both marker forms, their equivalence across slide content and notes, mixed multi-key headers, image applicability, and balanced-delimiter limits. Existing examples using double braces SHALL remain valid.

#### Scenario: Author follows either syntax

- **WHEN** an author follows a documented single-brace or double-brace example for text or images
- **THEN** analysis recognizes the fields and notes as documented
- **AND** the documentation does not claim support for malformed or extra-brace markers
