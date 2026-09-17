## MODIFIED Requirements

### Requirement: Generation from a typed plan

The system SHALL expose to the agent one tool that renders a deck from a plan: an ordered list of slides, each naming one pattern of the inventory and carrying its content (title, subtitle, body bullets, columns, items, image choices, speaker notes, optional emphasis), plus an optional file name. The tool description SHALL list the available patterns with their intent, label, zones and limits so the agent never guesses a pattern.

A slide SHALL be rendered either from a pattern of the template — a layout instantiated or an example slide duplicated, its zones filled by role — or, when no included pattern of the template can carry the slide's content, composed on the template's blank canvas from the template's own design system. The renderer SHALL never draw anything whose colour, typeface, size or position is not derived from that design system: a composed slide is as much within the charter as one the designer drew.

#### Scenario: Layout pattern rendered

- **WHEN** the plan uses a layout pattern
- **THEN** a new slide is instantiated from that layout and its placeholders are filled from the plan by role, leaving every other layout shape untouched

#### Scenario: Example slide pattern rendered

- **WHEN** the plan uses an example-slide pattern
- **THEN** that slide is duplicated with its shapes, background and pictures, its zones are filled from the plan, and every zone the plan does not fill is emptied or removed so no sample text survives

#### Scenario: A template pattern is preferred whenever one fits

- **WHEN** an included pattern of the template can show the content the slide carries
- **THEN** that pattern is used and nothing is composed, so a deck built on a rich corporate template is unchanged by this capability

## ADDED Requirements

### Requirement: A design system is read from the template

The analysis SHALL extract, besides the pattern inventory, the design system the template is built on: the theme's colour palette with the role of each colour, the typeface and size of each text level, and the usable area and margins the master defines. It SHALL be persisted with the inventory and SHALL be what every composed slide is drawn from.

#### Scenario: A plain template still yields a design system

- **WHEN** a template holds no example slide and only a title layout, a blank layout and a closing slide
- **THEN** the analysis still reports a palette, a type scale and a usable area, and the blank layout is offered as a canvas rather than excluded for holding no placeholder

#### Scenario: The author sees and can refuse composed patterns

- **WHEN** the inventory is reviewed before saving
- **THEN** composed patterns appear beside the template's own, each with its intent and a preview, and the author can relabel, re-intent or exclude any of them

#### Scenario: An author can turn composition off for the agent

- **WHEN** the agent is configured to use only the slides of its template
- **THEN** no slide is ever composed, whatever the plan asks for, and content the template cannot carry is reported as lost exactly as it is today; the setting survives a re-analysis of the template

### Requirement: Composition when the template cannot carry the content

The system SHALL compose a slide when, and only when, no included pattern of the template can show what the slide carries. The decision SHALL follow the same measure of fit that pattern resolution already uses, so that what is composed is exactly what would otherwise have been lost.

#### Scenario: A blank template no longer collapses onto its cover

- **WHEN** the template's only pattern with a text zone is its cover, and the plan asks for content, cards and a statement
- **THEN** each of those slides is composed on the blank canvas in the template's palette and type scale, and none of them is rendered on the cover

#### Scenario: Composed slides carry the template's own design

- **WHEN** a slide is composed
- **THEN** every colour comes from the template's palette, every typeface and size from its type scale, and every box sits inside the master's usable area, and the result reports which slides were composed rather than taken from the template

#### Scenario: Composition is reported, never silent

- **WHEN** a deck holds composed slides
- **THEN** the tool result names them, so the agent can tell the user which slides the template did not provide

### Requirement: Emphasis without leaving the charter

The plan SHALL be able to ask for emphasis on a slide's text — a level of prominence and an accent — by role only. The agent SHALL NOT be able to name a colour value, a typeface or a point size; the renderer SHALL resolve every emphasis through the template's design system.

#### Scenario: Emphasis resolved through the palette

- **WHEN** a plan marks content as accented or prominent
- **THEN** the rendered text takes a colour and weight drawn from the template's palette and type scale for that role

#### Scenario: An unknown emphasis degrades to plain text

- **WHEN** a plan asks for an emphasis the design system has no role for
- **THEN** the text is rendered plain and the result says the emphasis was ignored, and the deck is never refused for it
