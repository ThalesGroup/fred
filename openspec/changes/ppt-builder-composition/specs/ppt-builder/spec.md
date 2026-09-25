## MODIFIED Requirements

### Requirement: Generation from a typed plan

The system SHALL expose to the agent one tool that renders a deck from a plan: an ordered list of slides, each naming one pattern of the inventory and carrying its content (title, subtitle, body bullets, columns, items, image choices, speaker notes), plus an optional file name. The tool description SHALL list the available patterns with their intent, label, zones and limits so the agent never guesses a pattern.

A slide SHALL be rendered either from a pattern of the template — a layout instantiated or an example slide duplicated, its zones filled by role — or composed on the template's canvas from the template's own design system. Composition is the normal path for structured content; rendering a pattern of the template as it stands answers a plan that names that pattern. The renderer SHALL never draw anything whose colour, typeface, size or position is not derived from that design system: a composed slide is as much within the charter as one the designer drew.

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

### Requirement: The template is read as a design system

The analysis SHALL extract, besides the pattern inventory, the design system the template is built on: the colour palette as surface/text PAIRS rather than loose colours, the typeface, size, weight and line height of each text level, a spacing scale and the vertical rhythm it implies, the grid derived from the master's usable area and the slide's real dimensions, the shape language the template uses (corner radius, presence of strokes), and the optical anchors at which titles and content blocks start. It SHALL be persisted with the inventory and SHALL be the only source every composed slide draws from.

#### Scenario: A plain template still yields a design system

- **WHEN** a template holds no example slide and only a title layout, a blank layout and a closing slide
- **THEN** the analysis still reports paired colours, a type scale, a spacing scale, a grid and a usable area, and the blank layout is offered as a canvas rather than excluded for holding no placeholder

#### Scenario: A template that misuses its theme slots still yields usable tokens

- **WHEN** the theme's colour slots do not carry the roles their names suggest
- **THEN** the palette falls back to the colours the master actually uses for text and background, and no colour absent from the template is ever invented

#### Scenario: Colour pairs are checked for contrast

- **WHEN** the palette yields a surface whose paired text colour does not reach the minimum contrast
- **THEN** the pair falls back to the template's own body ink or background, whichever passes, and if neither does the surface is not offered as a fill — no colour absent from the template is invented to rescue it

#### Scenario: The grid follows the slide's real dimensions

- **WHEN** the template is not 16:9
- **THEN** the grid and every variant's boxes derive from the slide's actual width and height, and nothing assumes a ratio

#### Scenario: The author sees and can refuse composed patterns

- **WHEN** the inventory is reviewed before saving
- **THEN** composed patterns appear beside the template's own, each with its intent and a preview, and the author can relabel, re-intent or exclude any of them

#### Scenario: An author can turn composition off for the agent

- **WHEN** the agent is configured to use only the slides of its template
- **THEN** no slide is ever composed, whatever the plan asks for, and content the template cannot carry is reported as lost exactly as it is today; the setting survives a re-analysis of the template

### Requirement: Content is expressed through a component library

The system SHALL hold a library of typed components — at least Card, Chip, Stat, Bar, Divider and Image frame — and of compositions that arrange them, each component declaring its slots, the tokens it consumes, and a capacity stating how much content it can carry. Because the output format has no automatic layout, a composition SHALL offer a fixed set of variants rather than adapt fluidly, and the variant SHALL be chosen from the item count and the measured text.

#### Scenario: A composition is chosen by variant, not stretched

- **WHEN** a composition that offers a 2-up, a 3-up and a 4-up variant is given three items
- **THEN** the 3-up variant is used, its boxes sit on the grid inside the usable area, and no box is resized outside what that variant declares

#### Scenario: Content beyond a component's capacity is never overflowed

- **WHEN** the content given to a component exceeds the capacity that component declares
- **THEN** a variant that can carry it is chosen if one exists, and otherwise the slide splits (see the density requirement) — text never runs outside its box or over a neighbour

#### Scenario: Components follow the spacing scale and spend one accent

- **WHEN** a composition places its blocks and resolves the colours its components carry
- **THEN** every gap comes from the spacing scale rather than from a value computed to make something fit, and at most one accented element is drawn per slide, so the accent keeps its meaning

#### Scenario: An image is fitted, never distorted

- **WHEN** an Image frame receives an image whose aspect ratio differs from the frame's
- **THEN** the image fills and is cropped, or is contained within the frame, and is never stretched to fit

#### Scenario: A component degenerating at small values stays legible

- **WHEN** a Bar is drawn for a value so small that its length would fall below its own thickness
- **THEN** it is drawn at its minimum legible length or omitted, never as a shape whose corner radius distorts it out of the charter

### Requirement: The shape of the content decides how it is expressed

The renderer SHALL classify each slide's content by shape before choosing how to express it — parallel short items, an item carrying a figure, two opposed sets, an ordered sequence, a single sentence, a quantity out of a whole, continuous prose — and SHALL choose the composition that expresses that shape. The classification SHALL be applied by the renderer and SHALL NOT depend on the agent having asked for the right intent, so that a plan written as plain bullets is still expressed as the content deserves.

#### Scenario: Parallel short items are not rendered as a bullet list

- **WHEN** a slide carries four short parallel items and the plan asked only for body bullets
- **THEN** the slide is expressed as a card row rather than a bullet list, and the deck does not repeat one bullet-list layout for every slide

#### Scenario: A figure attached to an item becomes a stat, not a bullet

- **WHEN** an item carries a figure alongside its heading and text
- **THEN** the figure is rendered at the type scale's largest level for numbers, in a palette colour, rather than inline in a sentence

#### Scenario: Continuous prose stays prose

- **WHEN** a slide carries continuous prose that is not a list of parallel items
- **THEN** it is rendered as body text and is not broken into artificial cards

### Requirement: Composition is the normal path, and the template is the design language

The system SHALL compose a slide whose content has a structured shape — parallel items, figures, quantities, an ordered sequence, two opposed sets — drawing on the template's design system rather than on whichever of the template's own patterns comes closest. A template is the language a deck is written in, not a stock of slides to recycle.

The system SHALL render a pattern of the template exactly as it stands when, and only when, the plan names that pattern: naming it is the request to use that slide.

For content that is not structured — prose and single sentences — the choice SHALL be taken on the share of the slide's content a pattern can actually show, the same measure pattern resolution already uses to weigh what losing a field costs, and SHALL NOT be taken on a composite ranking score, which mixes that share with preference and overflow adjustments and cannot answer whether content would be lost.

#### Scenario: A rich template is composed in, not recycled from

- **WHEN** the plan asks for content the template already has a pattern for, without naming that pattern
- **THEN** the slide is composed from the template's tokens, grid and fixtures, because the slide is built for the content it carries rather than fitted into a slide drawn for another purpose

#### Scenario: Naming a pattern asks for that slide as it stands

- **WHEN** the plan names a pattern id of the template
- **THEN** that pattern is rendered unchanged and the classification does not override it

#### Scenario: A blank template no longer collapses onto its cover

- **WHEN** the template's only pattern with a text zone is its cover, and the plan asks for content, cards and a statement
- **THEN** each of those slides is composed on the blank canvas in the template's palette and type scale, and none of them is rendered on the cover

#### Scenario: A preferred pattern that would lose content does not suppress composition

- **WHEN** the best-ranked template pattern is preferred by the author but cannot show every field the slide carries
- **THEN** the slide is composed rather than rendered on that pattern, because the preference bonus does not make the loss acceptable

#### Scenario: Composed slides carry the template's own design

- **WHEN** a slide is composed
- **THEN** every colour comes from the template's palette, every typeface and size from its type scale, every box sits on the grid inside the master's usable area, and the shapes are real editable PowerPoint shapes rather than a picture

#### Scenario: Composition is reported, never silent

- **WHEN** a deck holds composed slides
- **THEN** the tool result names them, so the agent can tell the user which slides the template did not provide, and the delivered deck itself carries no mark

### Requirement: The design layer never knows about PowerPoint

The system SHALL keep the design reasoning and the emission of PowerPoint in separate layers. The design layer SHALL name components, tokens, grid positions and roles, and SHALL NOT name placeholders, shape types, layout indices or absolute units. The translation layer SHALL be the only place that emits shapes, and SHALL NOT choose a colour, a typeface, a size or a position that the design layer did not resolve from a token.

#### Scenario: No drawing value escapes the design system

- **WHEN** a composed slide is inspected shape by shape
- **THEN** every colour is one of the palette's, every typeface and size one of the type scale's, and no literal value appears that the template did not supply

#### Scenario: Charts remain out of scope while drawing does not

- **WHEN** the content calls for a quantity out of a whole or a series of values
- **THEN** it is expressed with the library's Bar component from primitive shapes, and no PowerPoint chart object with axes, legend or data table is created

### Requirement: Tokens are referenced, not copied

A composed shape SHALL refer to the template's theme — a theme colour slot for a colour, the theme's major or minor latin reference for a typeface — rather than carry the value the analysis read. A literal value SHALL be written only where the template offers no reference to point at, and the design system SHALL record that so it can be reported.

#### Scenario: A composed deck follows a theme change

- **WHEN** a composed deck is opened and the theme's colour variant or fonts are changed in PowerPoint
- **THEN** the composed slides change with it exactly as the template's own slides do, because their shapes reference the theme rather than a copy of its values

#### Scenario: A colour with no theme slot is recorded

- **WHEN** a token can only be read off a shape and has no theme slot to reference
- **THEN** the literal value is used and the design system marks that token as unreferenced, so the author can be told rather than shipping it silently

### Requirement: The template's own blocks are read for the style they demonstrate

The system SHALL read, from the blocks the template draws for itself, how this template draws a block: whether it paints them or outlines them, how round their corners are, how much air sits inside a block and between two blocks side by side, and whether a figure is printed above the label that names it or below. Only shapes that actually paint something SHALL vote on the painted-or-outlined question.

Composed slides SHALL use those values in place of the system's own defaults, and SHALL fall back to the spacing scale and to a defensible default for anything the template does not demonstrate. No value SHALL be invented for what the template does not show.

#### Scenario: A template that outlines its panels gets outlined cards

- **WHEN** the template's own blocks carry an outline and no fill, and a slide is composed with cards
- **THEN** the composed cards are outlined and unfilled, they are still cards rather than absent, and their outline is written as a theme reference like every other colour

#### Scenario: Columns are spaced the way the template spaces its own

- **WHEN** the template puts two blocks side by side with a measurable gap between them
- **THEN** that gap becomes the grid's gutter, and composed columns are separated by it rather than by a step of the spacing scale

#### Scenario: A figure is stacked the way the template stacks it

- **WHEN** the template prints a quantity under the words that name it
- **THEN** a composed stat prints the figure under its label too, while the figure still comes first in the reading order, because the figure is the point

#### Scenario: A template that demonstrates nothing is still composable

- **WHEN** the template shows no block of its own
- **THEN** every field of the component style keeps its default and the spacing scale answers for the gaps, rather than a value being guessed from nothing

### Requirement: A composed slide inherits the template's furniture and never draws over it

A logo, band, rule or footer placed on a slide master or a slide layout is inherited by every slide using that layout. The system SHALL compose on the placeholder-free layout carrying the most of that furniture, not on the barest one, and SHALL read whether a layout suppresses the master's own shapes rather than assuming they are inherited. A layout whose furniture leaves too little room SHALL NOT be used as a canvas.

The system SHALL trim the footprint of every inherited fixture out of the usable area before the grid is built, and SHALL report any composed shape that nonetheless overlaps one. The full-bleed background SHALL NOT be treated as a fixture.

#### Scenario: The company logo stays visible on a composed slide

- **WHEN** the template carries a logo on its master and a slide is composed
- **THEN** the logo is shown, because the canvas inherits it, and no composed shape is placed over it

#### Scenario: The dressed layout is preferred to the bare one

- **WHEN** the template has both a bare layout and a dressed layout with nothing to fill
- **THEN** the dressed one is the canvas, so a composed slide carries the same furniture as the rest of the deck

#### Scenario: A layout that suppresses the master inherits nothing

- **WHEN** the canvas layout switches the master's own shapes off
- **THEN** nothing is reserved for them and the whole usable area is available

### Requirement: The deck is consistent from slide to slide

Every composition SHALL align to the optical anchors the design system carries, whatever variant is chosen, so that a composed slide placed between two template slides lines up with both. Anchors SHALL be read from the template, never chosen by the system.

#### Scenario: Titles do not move between slides

- **WHEN** a deck mixes template patterns and composed slides across several compositions
- **THEN** every title starts at the same ordinate, and every content block at the same ordinate, across the whole deck

#### Scenario: A template whose slides disagree with its master keeps its slides' convention

- **WHEN** the master's anchors and those of the template's own slides differ
- **THEN** the anchors read from the template's slides are used, because that is the convention the template's reader recognises

#### Scenario: A band on the canvas moves the anchors below it

- **WHEN** the canvas inherits a band where the template's own slides start their title
- **THEN** the title ordinate and the content ordinate both move down by what the band takes, keeping the template's distance between them, rather than the title being hidden under it

### Requirement: Density has a ceiling and overflow splits the slide

Each composition SHALL declare a maximum content it can carry. When one planned slide exceeds every variant of the chosen composition, the system SHALL emit one continuation slide carrying the same title rather than cramming or cutting, and SHALL report it. At most one continuation per planned slide SHALL be emitted; content still exceeding that SHALL be fitted and reported as it is today.

#### Scenario: An overfull slide becomes two, not a crammed one

- **WHEN** a planned slide carries more items than any variant of its composition can hold
- **THEN** a continuation slide is emitted with the same title, the content is split across the two, and the result names the split

#### Scenario: Splitting is bounded

- **WHEN** a planned slide carries many times the capacity of every variant
- **THEN** one continuation is emitted and the remainder is fitted and reported as lost, so a planning failure is surfaced rather than hidden behind a cascade of slides

#### Scenario: The deck may differ in length from the plan

- **WHEN** the deck ends up with more slides than the plan listed because a slide was split
- **THEN** the result states it, the same way a deck shorter than planned is already reported

### Requirement: Composed slides are accessible

Composed shapes SHALL carry what assistive technology needs: a text alternative on every Image frame, a decorative marking on shapes that carry no meaning of their own, and a reading order that follows the composition's order rather than the order the shapes were created in.

#### Scenario: Decorative shapes are skipped and images are described

- **WHEN** a composed slide holds a Card background, a Divider and an Image frame
- **THEN** the Card background and the Divider are marked decorative, and the Image frame carries a text alternative

#### Scenario: Reading order follows the composition

- **WHEN** a composed slide's shapes were created back to front so a Card sits behind its text
- **THEN** the reading order still follows the composition's own order, not the creation order
