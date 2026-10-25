## ADDED Requirements

### Requirement: A named kicker line is a label, not a zone

The template analysis SHALL treat a text shape whose shape name, or whose layout placeholder's name, names a kicker (`kicker`, `eyebrow`, `surtitre`, `sur titre`, `overline`, `pretitle`) as no zone: it SHALL NOT change the slide's kind, its zones or its count of empty zones. The analysis SHALL NOT detect a kicker by geometry, and SHALL NOT treat a title placeholder as one. The renderer SHALL write nothing in a kicker and SHALL remove it from the delivered slide without reporting removed example text. A template without such a name SHALL be analysed and rendered as before.

#### Scenario: Kicker placeholder on a layout

- **GIVEN** a layout whose body placeholder is named `kicker`, above its title
- **WHEN** the template is analysed
- **THEN** the layout's pattern holds no zone for that placeholder and its kind is read from the remaining zones

#### Scenario: Same shapes without the name

- **GIVEN** the same template with the placeholder keeping its automatic name
- **WHEN** the template is analysed
- **THEN** the placeholder is a zone, as before this change

#### Scenario: Kicker on a delivered slide

- **WHEN** a slide is built on a layout or an example slide holding a kicker
- **THEN** the delivered slide holds neither the kicker's example text nor an empty kicker placeholder, and the agent gets no "template example text removed" line for it
