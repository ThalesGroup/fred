## Purpose

Lets an agent generate a PowerPoint presentation from a chat request, on an unannotated corporate template analysed at configuration time or on a built-in theme, and deliver it with a preview and a download.

## ADDED Requirements

### Requirement: Template analysis needs no annotation

The system SHALL inventory the usable patterns of an uploaded `.pptx` template without requiring any marker, note, or shape name in the file. A pattern is either a master layout or an example slide of the deck body. Each pattern SHALL carry a stable id, a label, an intent, and the list of zones the agent may fill (text zones with a role, image zones, and repeated groups with their item count and per-item zones).

#### Scenario: Layout classified from its placeholders

- **WHEN** a template layout has a title placeholder and one body placeholder
- **THEN** the inventory contains a pattern for that layout with intent `content`, a title zone and a body zone

#### Scenario: Example slide keeps its typed placeholders

- **WHEN** an example slide instantiates a layout and its title and body placeholders still exist on the slide
- **THEN** those placeholders are inventoried as fillable zones with the roles their placeholder types imply, regardless of the sample text they hold

#### Scenario: Free text boxes classified by heuristics

- **WHEN** an example slide holds free text boxes that are not placeholders
- **THEN** each box holding sample text is inventoried as a fillable zone whose role is derived from its position, size, font size and sample text (heading, body, caption, number, label), and boxes whose text is repeated identically across several slides are not inventoried

#### Scenario: Repeated sibling groups become a list

- **WHEN** an example slide holds three or more sibling shape groups with the same internal structure (same shape kinds and text sizes) laid out on a grid
- **THEN** the inventory exposes one repeated group with the item count and the per-item zones, so the plan can fill fewer items than the template shows

#### Scenario: Slides with nothing to fill are fixed slides

- **WHEN** an example slide has no fillable zone (for example a closing "thank you" slide)
- **THEN** it is inventoried with intent `fixed`, can only be included verbatim, is never marked as the preferred pattern of its intent, and the catalogue offers no zone for it

#### Scenario: Resource slides are excluded by default

- **WHEN** an example slide is an icon bank, a chart slide or a table slide (no fillable text zone besides a caption, or a chart/table as its main content)
- **THEN** it is inventoried but excluded by default, and the analysis summary counts it as excluded

#### Scenario: Optional annotations refine the analysis

- **WHEN** a shape carries a meaningful name set in PowerPoint's Selection pane (such as `title`, `subtitle`, `kpi_value`) or the slide's speaker notes describe the slide's purpose
- **THEN** that information takes precedence over the heuristics for that zone or that slide's intent, and a template without any such annotation is still fully analysed

#### Scenario: Unreadable or oversized upload

- **WHEN** the uploaded file is not a readable `.pptx` or exceeds 50 MB
- **THEN** the analysis reports one error with a stable code and no pattern, and the agent cannot be saved with that upload

### Requirement: Analysis is available before saving

The system SHALL expose a stateless analysis of an uploaded template so the agent form can show the inventory and a rendered preview of every pattern before the agent is saved, and SHALL recompute the same inventory from the real bytes when the agent is saved.

#### Scenario: Instant preview in the form

- **WHEN** an author picks a `.pptx` in the agent form
- **THEN** the form shows within the analysis round-trip a summary (patterns detected, fixed slides, excluded slides) and can show a thumbnail of every pattern, without anything being persisted

#### Scenario: Stored analysis follows the rules

- **WHEN** an agent whose inventory was computed by older analysis rules is saved without a new upload
- **THEN** the inventory is recomputed from the stored template, the author's corrections are re-applied, and a failure to recompute keeps the stored inventory

#### Scenario: Save recomputes and stores

- **WHEN** the agent is saved with a staged template
- **THEN** the template bytes are stored as an agent asset, the recomputed inventory and the author overrides are stored in the capability config, and the template bytes never appear in the stored config

### Requirement: Author overrides

The system SHALL let the agent author correct the analysis without editing the template: change a pattern's label or intent, exclude or re-include a pattern, and change a zone's role (including "do not touch"). Overrides SHALL be the only author input persisted besides the analysis, and SHALL survive an ordinary save without re-upload.

#### Scenario: Override applied at generation

- **WHEN** an author marks a zone as "do not touch" and saves
- **THEN** the generation never modifies that zone's content

#### Scenario: Overrides re-applied after re-upload

- **WHEN** the author uploads a new version of the template
- **THEN** the inventory is recomputed and each override whose pattern and zone still exist is re-applied, while overrides that no longer match are dropped and reported in the form

#### Scenario: No override is required

- **WHEN** an author uploads a template and saves without opening the pattern review
- **THEN** the agent is saved and generates decks with the automatic analysis

### Requirement: Generation from a typed plan

The system SHALL expose to the agent one tool that renders a deck from a plan: an ordered list of slides, each naming one pattern of the inventory and carrying its content (title, subtitle, body bullets, columns, items, image choices, speaker notes), plus an optional file name. The tool description SHALL list the available patterns with their intent, label, zones and limits so the agent never guesses a pattern.

#### Scenario: Layout pattern rendered

- **WHEN** the plan uses a layout pattern
- **THEN** a new slide is instantiated from that layout and its placeholders are filled from the plan by role, leaving every other layout shape untouched

#### Scenario: Example slide pattern rendered

- **WHEN** the plan uses an example-slide pattern
- **THEN** the example slide is duplicated with its decoration and pictures intact, its fillable zones are filled from the plan, and the original example slides never appear in the generated deck

#### Scenario: No sample text left behind

- **WHEN** the plan does not provide content for a fillable zone
- **THEN** that zone's sample text is removed (or the zone removed when it is an image zone or an unused list item), so the deck never shows placeholder text such as "Cliquez ici pour modifier le texte"

#### Scenario: Fewer items than the template shows

- **WHEN** the plan fills a repeated group with fewer items than the template's count
- **THEN** the unused items are removed rather than left with sample text

#### Scenario: Overflow control

- **WHEN** a text value is too long for its zone at the zone's font size
- **THEN** the font size is reduced within the zone's autofit rule down to a floor, and the tool result tells the agent which zones were still truncated so it can shorten them; a one-line heading or label that still does not fit is reported with the number of characters that would fit

#### Scenario: Text width is measured, not guessed

- **WHEN** the analysis states a zone's character limit, or the generation decides that a text overflows
- **THEN** the width is measured with the font the zone is drawn in, resolved to the substitute the server actually renders with, so the same ruler serves the limits shown to the agent, the shrinking and the box sizing; without a usable font a conservative per-character estimate stands in

#### Scenario: A zone's capacity is what the box really holds

- **WHEN** the analysis states a zone's character and line limits
- **THEN** the box's own padding comes off both dimensions, a line advances by the paragraph spacing the template declares (inherited from the layout and the master, not only what the slide's own text carries), and the character count allows for the room greedy wrapping wastes at each line break, so text written to the stated limit does not overflow the slide

#### Scenario: One capacity, quoted and enforced

- **WHEN** the catalogue quotes a limit for a plan field several zones are filled from
- **THEN** it quotes the tightest of those zones, item zones carry their own limits, a box that grows with its text instead of wrapping carries none, and the generation enforces exactly the number the catalogue quoted

#### Scenario: A box that auto-sizes in height is still fitted

- **WHEN** a zone's box wraps inside its width and auto-sizes its height, on the slide or through the rule it inherits from its layout
- **THEN** it is fitted to its line budget like any other wrapping zone — never widened, since that pushes the text out of the design — and an overflow is reported; only a box that does not wrap at all is sized to its text instead

#### Scenario: Shrinking is not truncating

- **WHEN** a text only had to be shrunk to the font floor to fit, or a box auto-sizes to its text through the rule it inherits from its layout
- **THEN** no content is dropped and the result does not report a truncation; a zone that genuinely overflows keeps a cut first line rather than rendering empty

#### Scenario: A replaced picture keeps its place in the drawing order

- **WHEN** an image zone that is not a placeholder is filled
- **THEN** the new picture takes the position the one it replaces held, so a cover photo does not come to the front and hide the title written over it

#### Scenario: Nothing the plan carries is dropped in silence

- **WHEN** the plan names a field that is not a slide field, wraps a bullet under a key of its own, gives the same field under two aliases, or fills both `image` and `images`
- **THEN** the content is kept where it can be read, and anything that could not be placed is named in the result so the agent can correct it on the next turn

#### Scenario: Comparable zones of one slide are read as a set

- **WHEN** several zones playing the same part on a slide are fitted, and one of them needs a smaller font than its siblings
- **THEN** they all take the smallest of their sizes, a single unbreakable token such as an address never takes a zone below the font floor, and a column heading written into a body for want of a heading zone drops its bullet so it still reads as a heading

#### Scenario: One answer delivers one presentation

- **WHEN** an agent splits a deck across several build calls, or repeats one after a busy answer
- **THEN** the tool states that a single call builds the whole deck and that calling again replaces it, and the decks of one conversation that share a name share a key, so the reader is never shown a card per fragment each holding a truncated presentation

#### Scenario: Lost columns come with advice the agent can act on

- **WHEN** a slide carries more columns than the chosen pattern can show
- **THEN** the result names a pattern of this template that would hold them, or, when the template has none, says how many columns it does hold and that no rewrite of that slide can carry more — rather than telling the agent to move it to a pattern that does not exist

#### Scenario: A deck shorter than the agent planned is caught

- **WHEN** the plan holds far fewer slides than the agent intended, for example an agenda announcing several topics that no slide follows
- **THEN** the result states the number of slides delivered, says the deck holds what was sent rather than what was planned, and invites one further call with the complete list — a deck is always rebuilt whole, never extended

#### Scenario: A busy server does not invite parallel retries

- **WHEN** a build is refused because the server's heavy-job slots are taken
- **THEN** the refusal tells the agent to wait and then make a single call with the whole deck, rather than to retry immediately or in parallel

#### Scenario: Unused item slots leave the slide clean

- **WHEN** a repeated group is filled with fewer items than the template shows
- **THEN** the unused slots go with the loose decoration drawn for them — icons, card frames, and the connectors that span the area they occupied — the kept items are slid back to the middle of the room the group had, and nothing that also serves a kept item is touched

#### Scenario: A group pattern given no items keeps its design

- **WHEN** the plan names a pattern whose content is a repeated group but puts its content in another field
- **THEN** every slot is removed without sweeping the slide's own background with them, and the result tells the agent the pattern shows its content as items and how many it holds

#### Scenario: No placeholder is left prompting

- **WHEN** a pattern has more text placeholders than the plan fills
- **THEN** the unfilled ones are removed rather than emptied, so the delivered deck shows no "click to add text" prompt when the user opens it to edit

#### Scenario: A pattern is chosen for the content it is given

- **WHEN** the plan asks for an intent rather than a pattern id
- **THEN** the pattern is the one that can show the most of what the slide actually fills — weighted by how costly each field is to lose, a title more than a column heading — rather than the first of that intent; a pattern whose picture zones the plan cannot fill and one that would truncate the text both lose to one that can hold the content

#### Scenario: Missing intent degrades gracefully

- **WHEN** the plan asks for an intent the inventory does not offer, or the patterns of that intent cannot show the slide's content
- **THEN** the tool substitutes the closest available pattern following a documented degradation order (for example `two_columns` → `content`, `section` → `title`) and reports the substitution in its result

#### Scenario: Unknown or excluded pattern is substituted

- **WHEN** the plan names a pattern id that is not in the inventory, is excluded, or is a slide number or label the model mistook for an id
- **THEN** the tool uses the pattern that name designates when it can hold the slide's content, otherwise the best pattern for the intent the slide's content implies, builds the deck, and reports each substitution in its result

#### Scenario: Malformed plan from the model

- **WHEN** the plan has the wrong JSON shapes (a bullet list given as one string, numbers as integers, a non-object entry in the slide list, unknown keys)
- **THEN** the tool coerces what it can (including zone role names used as keys, such as `body` for an item's `text` or a slide's `bullets`), skips entries that are not slides, builds the deck from the remaining slides and reports what it skipped; it never fails argument validation

#### Scenario: Content the pattern cannot show is reported

- **WHEN** a slide gives content its pattern has no zone for (bullets on a section slide, an item text on a figures slide, content on a fixed slide other than its own title)
- **THEN** the deck is built without that content and the tool result names it per slide, so the agent can move it to a pattern that shows it

#### Scenario: Closing slide by intent

- **WHEN** the plan asks for the `fixed` intent
- **THEN** the tool uses a fixed pattern named as a closing slide ("Merci", "Thank you") before any other fixed pattern

#### Scenario: Every error result is readable

- **WHEN** the tool cannot build the deck (no usable slide, server busy, template unavailable)
- **THEN** its error result carries a short actionable text, so the user sees that text rather than a generic failure message

#### Scenario: Empty plan is rejected

- **WHEN** the plan has no slide with any content
- **THEN** the tool returns an error asking for content and nothing is generated

### Requirement: Images from team folders

The system SHALL let the plan fill an image zone with an image document chosen from the team's resource folders, and SHALL remove an image zone the plan leaves empty.

#### Scenario: Image placed

- **WHEN** the plan names a valid image document for an image zone
- **THEN** the image is embedded in that zone preserving its aspect ratio: a picture placeholder is filled edge to edge (cropped as PowerPoint does), a free picture zone is scaled to fit inside its box

#### Scenario: Image zone left empty

- **WHEN** the plan gives no image for an image zone
- **THEN** the empty picture placeholder is removed from the generated slide

#### Scenario: Invalid image reference

- **WHEN** the plan names a document that cannot be fetched or is not an image
- **THEN** the deck is built without that picture and the tool result names the document that was left out

### Requirement: Built-in theme when no template is configured

The system SHALL generate decks with a neutral built-in theme when the agent has no template, covering every intent of the vocabulary.

#### Scenario: Agent without template

- **WHEN** an agent enables the capability without uploading a template
- **THEN** the tool is available and renders every intent on the built-in theme

### Requirement: Delivery

The system SHALL write the generated deck to the agent workspace of the conversation, publish a PDF preview beside the chat when conversion is available, and otherwise offer a download.

#### Scenario: Preview available

- **WHEN** the deck is generated and the PDF conversion succeeds
- **THEN** the chat shows the same preview card and side pane as `ppt_filler`, with a download of the `.pptx`, and the pane opens on its own even when the agent has no `ppt_filler` capability

#### Scenario: Preview keeps one-line text on one line

- **WHEN** the deck holds a text box set not to wrap (a template's closing "Merci"), which LibreOffice would break when its substitute font runs wider
- **THEN** the PDF preview is converted from a copy where such boxes are widened around their alignment, and the delivered `.pptx` keeps the template's geometry

#### Scenario: Deck regenerated within one answer

- **WHEN** the agent builds the same deck several times before answering (for example to fix the adjustments the tool reported)
- **THEN** the answer shows a single preview card, for the last build, as the other chat cards do for an object updated several times in one answer

#### Scenario: Preview unavailable

- **WHEN** the PDF conversion fails or is unavailable
- **THEN** the chat shows a download chip for the `.pptx` and the agent is told the preview is unavailable

### Requirement: Chat-time corrections are per conversation

The system SHALL let the user correct a generated deck in chat by regenerating from an amended plan, and SHALL NOT change the agent configuration from a conversation.

#### Scenario: User asks for a different pattern

- **WHEN** the user says a slide should use another kind of slide
- **THEN** the agent regenerates the deck with the amended plan and the stored inventory and overrides are unchanged
