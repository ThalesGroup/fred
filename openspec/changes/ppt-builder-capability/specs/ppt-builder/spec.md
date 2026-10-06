## Purpose

Lets an agent generate a PowerPoint presentation from a chat request on an unannotated corporate template — analysed once, in the background, into labelled archetypes — or on the built-in Fred template, choosing each slide in code and delivering a preview and a download.

## ADDED Requirements

### Requirement: Template analysis needs no annotation

The system SHALL inventory an uploaded `.pptx` without requiring any marker, note or shape name. The inventory SHALL hold master layouts and example slides as patterns, each with a stable id, a label, a `kind` from the closed vocabulary (`cover`, `agenda`, `section`, `bullets`, `two_columns`, `comparison`, `cards`, `figures`, `process`, `timeline`, `team`, `quote`, `image_text`, `table`, `closing`, `other`), a reusable flag, its text, image and table slots with capacities, and its repeated groups with their item count.

#### Scenario: Every text shape of an example slide is a slot

- **WHEN** an example slide holds text boxes with real corporate text rather than sample text
- **THEN** each text-bearing shape is a slot, except text repeated on two or more slides and footer, date or slide-number fields

#### Scenario: Layout classified from its placeholders

- **WHEN** a layout has a title placeholder and one body placeholder
- **THEN** the inventory holds a `bullets` pattern for it with a title slot and a body slot

#### Scenario: Repeated sibling groups become a list

- **WHEN** an example slide holds three or more sibling groups of identical structure
- **THEN** the inventory exposes one repeated group with its item count and per-item slots, so a plan may fill fewer items

#### Scenario: Rows of same-size shapes become a list

- **GIVEN** a slide or layout with three or more non-grouped text shapes of near-equal size and the same text style side by side, or two such shapes with an aligned second row under them
- **WHEN** it is analysed
- **THEN** they form one repeated group (the rows giving each item its fields), the tool description says `items max N`, and unused items are removed and the rest recentred

#### Scenario: Column bodies stay columns

- **GIVEN** a two- or three-column layout whose bodies are wider than 35 % or taller than 40 % of the slide
- **WHEN** it is analysed
- **THEN** its bodies stay separate slots and no repeated group is made

#### Scenario: Example slide that copies its layout

- **GIVEN** an example slide holding every placeholder of its layout (empty picture placeholders included), with or without drawn decoration
- **WHEN** it is analysed
- **THEN** the inventory holds one pattern for that design, the slide (copied and filled), with its sample text, notes, shape names and position taken into account, and no separate pattern for the layout

#### Scenario: Placeholders sharing an index

- **GIVEN** an example slide with two placeholders of the same `idx`
- **WHEN** it is analysed
- **THEN** each gets its own slot key and the pattern carries a warning

#### Scenario: First slide is the cover

- **GIVEN** a first example slide with a title slot and no body content
- **WHEN** no template hint states another kind
- **THEN** its kind is `cover`

#### Scenario: Resource slides are excluded by default

- **WHEN** an example slide is an icon bank, or a chart or a table that is not a data table is its main content (merged cells, or per-cell fills that vary across the body, as in a Gantt grid)
- **THEN** it is inventoried but excluded, and the summary counts it as excluded

#### Scenario: Data table becomes a table slot

- **GIVEN** an example slide whose main content is a table of at least two columns, without merged cells, with empty or sample body cells and fills left to its table style
- **WHEN** it is analysed
- **THEN** the slide is a `table` pattern whose table slot records the header row flag, each column's characters per line and the lines its rows show

#### Scenario: Optional annotations refine the analysis

- **WHEN** a shape name or a speaker-note line states a role, kind or label
- **THEN** it takes precedence over the heuristics and the vision label for that shape or slide

#### Scenario: Slot capacity measured and calibrated

- **WHEN** the analysis measures a text slot
- **THEN** it stores the slot's capacity as characters per line × lines, from its geometry and font, raised (within a bound) until the designer's own sample text in that slot fits, and the fit check and the tool description use that stored capacity

#### Scenario: Unreadable or oversized upload

- **WHEN** the upload is not a readable `.pptx` or exceeds 50 MB
- **THEN** the save fails with one error carrying a stable code, and no analysis starts

### Requirement: Example slides are labelled by a vision model

The system SHALL render each example slide to an image with its slots numbered and ask a vision-capable model for the slide's kind, label, the purpose of each slot, the maximum number of items and whether the slide is reusable. Geometry and capacities SHALL stay those of the deterministic analysis.

#### Scenario: Vision label applied

- **WHEN** the model returns a valid label for an example slide
- **THEN** the pattern takes that kind, label, slot purposes and reusable flag

#### Scenario: Vision label incompatible with the slots

- **WHEN** the model's kind needs slots the slide does not have (for example `bullets` without a body slot, `cover` without a title slot, `cards` without a repeated group)
- **THEN** the slide keeps its heuristic kind, takes the model's label and slot purposes, and the rejection is logged and shown as a pattern warning

#### Scenario: Vision toggle off

- **WHEN** the author turns "Use a vision model" off
- **THEN** the analysis makes no model call, labels slides by rules only, and runs again because the setting changed

#### Scenario: No vision-capable model available

- **WHEN** neither the agent's resolved model nor any selectable profile supports vision
- **THEN** the toggle is shown disabled and off with a message explaining that slides are labelled by rules, and the model selector is hidden

#### Scenario: Toggle on with a vision model

- **WHEN** the toggle is on and a vision-capable model is available
- **THEN** example slides are labelled by that model, and the selector lists only vision-capable profiles

#### Scenario: Labelling model

- **WHEN** the capability settings name a labelling model the team may use
- **THEN** that model labels the slides; otherwise the agent's default model does

#### Scenario: Vision unavailable or invalid

- **WHEN** the resolved model is not vision-capable, the call fails, or the answer is malformed
- **THEN** the slide keeps its heuristic kind and label, is marked as heuristically labelled, and the analysis still completes

### Requirement: Analysis runs in the background

The system SHALL complete the agent save without waiting for the template analysis, persist the analysis result durably where every replica can read it, and expose its status to the agent form.

#### Scenario: Save returns before analysis

- **WHEN** an author saves an agent with a new template
- **THEN** the save stores the template, records a pending analysis keyed by the agent and the template hash, and returns without waiting for the analysis to finish

#### Scenario: Status visible in the form

- **WHEN** the author views the agent form while the analysis is pending or running
- **THEN** the form shows that the analysis is in progress, and shows the summary and thumbnails once it has succeeded

#### Scenario: Any replica serves the result

- **WHEN** the analysis ran on one replica and a turn or a status request reaches another
- **THEN** that replica reads the same stored result

#### Scenario: Interrupted analysis recovers

- **WHEN** the replica running an analysis stops before finishing
- **THEN** the analysis is reported as interrupted once its lease expires and can be re-run

#### Scenario: Agent unavailable while analysing

- **WHEN** an agent's template analysis is pending or running
- **THEN** the agent is shown as unavailable, with the reason, on the team agents page and cannot be selected in the chat agent picker

#### Scenario: Agent available when analysis succeeds

- **WHEN** the analysis succeeds
- **THEN** the agent becomes available without another save

#### Scenario: Agent becomes available on next listing after analysis completes

- **WHEN** the analysis succeeds while nobody has the agent form open
- **THEN** the next listing of the team's agents re-checks the agent and shows it available, and a pod that does not answer in time leaves it unavailable without delaying the listing

#### Scenario: Failed or interrupted analysis

- **WHEN** the analysis fails or is interrupted
- **THEN** the agent stays unavailable, the agent form shows the error, and an author who can edit the agent may re-run the analysis from the stored template

#### Scenario: Build requested before analysis completes

- **WHEN** the build tool is reached while the template analysis has not succeeded
- **THEN** the tool builds nothing and returns a short message that the template analysis is not ready

#### Scenario: Only agent editors see the analysis

- **WHEN** a user who cannot edit the agent requests its analysis status, thumbnails or a re-run
- **THEN** the request is refused

#### Scenario: Analysis rules change

- **WHEN** an agent's stored analysis was produced by older analysis rules and the agent is saved
- **THEN** the analysis is run again in the background from the stored template

### Requirement: Author review

The system SHALL let the author review the analysis — a thumbnail, label and kind per pattern — and change a pattern's label or kind or exclude/include it. Overrides SHALL be the only author input persisted besides the template, SHALL survive an ordinary save, and SHALL never be required.

#### Scenario: No review required

- **WHEN** an author uploads a template and saves without opening the review
- **THEN** the agent builds decks with the automatic analysis once it has succeeded

#### Scenario: Override applied

- **WHEN** an author excludes a pattern or changes its kind
- **THEN** the assignment never uses an excluded pattern and treats a re-kinded pattern as its new kind

#### Scenario: Example slides and layouts shown apart

- **WHEN** the author opens the review
- **THEN** the example slides of the deck come first, the remaining layouts follow in a separate collapsed section marked as fallback, excluded patterns last, and each card's controls stay inside it

#### Scenario: Overrides after re-upload

- **WHEN** a new template version is analysed
- **THEN** overrides whose pattern still exists are re-applied and the others are dropped and reported in the form

### Requirement: Slides are chosen by the code

The system SHALL accept from the model a plan of slides carrying content only — title, subtitle, bullets, columns, items, table, images, notes and an optional `kind`, last in the schema — and SHALL assign each slide to a pattern deterministically. The tool schema and description SHALL NOT expose pattern ids; the description SHALL list the kinds the template offers and, per kind, every distinct variant with its label and the measured capacity of each zone (characters per line × lines, maximum items).

#### Scenario: Example slide preferred over a layout

- **WHEN** both an example slide and a layout of the slide's kind fit its content
- **THEN** the example slide is chosen, duplicated with its decoration intact and filled

#### Scenario: Kind inferred from content

- **WHEN** a slide gives no `kind`
- **THEN** its kind is inferred from the shape of its content (items with figures → `figures`, two columns → `two_columns`, ordered items → `process`, …)

#### Scenario: Requested kind unavailable

- **WHEN** a slide asks for a kind the template does not offer, cannot fill with this content, or forbids at that position
- **THEN** the slide is assigned from its content shape to a fitting pattern of another kind, and the success message names the substitution

#### Scenario: Fit check

- **WHEN** a pattern lacks a slot for a non-empty field, holds fewer items than the slide carries, or cannot hold the text above the shrink floor
- **THEN** that pattern is not a candidate for the slide

#### Scenario: Cover exactly once, first

- **WHEN** a deck is assigned on a template holding a cover pattern
- **THEN** the first slide uses the cover and no other slide does

#### Scenario: Closing at most once, last

- **WHEN** a plan holds closing content
- **THEN** a closing pattern is used at most once and only for the last slide

#### Scenario: Variety

- **WHEN** three consecutive slides would use the same pattern and another fitting pattern exists for one of them
- **THEN** the assignment uses the alternative; when none exists the repetition is allowed and reported

#### Scenario: Each template slide once where possible

- **GIVEN** a pattern already used earlier in the deck, not necessarily on the previous slide
- **WHEN** an unused pattern of the same kind tier also fits the slide
- **THEN** the unused pattern is chosen; a pattern used three times or more is reported in the success message with the unused variants and their sizes

#### Scenario: First deck asked to vary once

- **GIVEN** a conversation whose outputs folder holds no deck yet
- **WHEN** the assignment uses one template slide that is not a cover, section, agenda or closing three times or more, and the template has an unused variant of its kind or an unused slide of another such kind
- **THEN** no deck is written and `needs_revision` names the repeated slides and the alternatives with the content each suits; the next call is built as sent, even when it repeats the same plan

#### Scenario: Later deck keeps the note

- **GIVEN** a conversation where a deck was already delivered
- **WHEN** a new plan uses one template slide three times or more
- **THEN** the deck is built and the repetition is only reported in the success message

#### Scenario: Choice guide in the description

- **WHEN** the tool description is built
- **THEN** it says, for the kinds the template offers, which content suits each (numbers → figures, dates → timeline, parallel items → cards, ordered steps → process, a comparison → table, not restated as columns) and that each slide should look different

#### Scenario: Empty item pictures are a cost

- **WHEN** a slide's items carry no images and both a card pattern with item pictures and one without fit
- **THEN** the pattern without pictures is chosen

#### Scenario: Item heading without a heading zone

- **GIVEN** items with a heading and a text, and a list whose items have a single text zone
- **WHEN** the heading and the text fit that zone together
- **THEN** the heading leads the item's text in bold and nothing is reported lost

#### Scenario: Template icons kept

- **WHEN** a card slide with icons is filled and some cards are removed
- **THEN** the remaining cards keep the template's icons and the removed cards' icons leave with them

### Requirement: No silent fallback

The system SHALL NOT substitute an unfitting pattern for a slide. When a slide fits no pattern, the tool SHALL build nothing and return a structured error the model can act on.

#### Scenario: Slide fits nothing

- **WHEN** one slide of the plan fits no included pattern of any kind (for example seven items where the largest list holds six)
- **THEN** no deck is written and the result lists, per failing slide, its index, the exact field and element that does not fit with the measured limit (`bullets[2] is 214 chars; this zone holds ≈40 chars × 3 lines`, `items: 7 given, max 6`) and concrete options available in this template (shorten an element to N chars, split, trim to N items, another kind)

#### Scenario: Same problem twice

- **WHEN** the model calls again and a slide has the same problem as in the previous result
- **THEN** the result says whether that slide was resent unchanged or changed without fixing the problem, instead of repeating the same message

#### Scenario: Plan text that would be dropped

- **WHEN** a slide, column or item carries a key that is no field (`"columns": {"heading": "Espagne", "bullets": [...], "heading2": "Italie"}`), or a column or item has a heading without a body (or a body without a heading) while another entry of the same list has both
- **THEN** no deck is written and `needs_revision` names the slide and the field (`columns: heading2 'Italie' is not a column field`, `columns[1] has heading 'Italie' but no bullets`) with the fix

#### Scenario: Repair loop

- **WHEN** the model calls the tool again with a corrected plan
- **THEN** the deck is built from the corrected plan as a whole, replacing any earlier build

#### Scenario: Success message invites correction

- **WHEN** a deck is built with kind substitutions, truncations, removed leftovers or lost content
- **THEN** the result names them per slide and allows another call with the whole corrected deck

### Requirement: Rendering only fills the template

The system SHALL build each slide by instantiating a layout or duplicating an example slide and filling its slots; it SHALL never draw shapes the template does not hold, and the original example slides SHALL never appear in the output.

#### Scenario: Duplicated slide keeps its look

- **WHEN** an example slide is duplicated
- **THEN** its pictures and media share the template's parts, its colour-map override and speaker notes are copied, and only image, media and external hyperlink relationships are re-created

#### Scenario: Links to other slides are not copied

- **WHEN** an example slide links to another slide of the template (an agenda entry)
- **THEN** the link is dropped and no removed slide reappears in the package

#### Scenario: Multi-level bodies keep their formatting

- **WHEN** a body slot is filled with bullets on several levels
- **THEN** each level takes the template paragraph formatting of that level

#### Scenario: No original text left behind

- **WHEN** a slide has been filled and some original non-shared text is still present on it
- **THEN** that text is removed and reported, so the deck never shows the template's example content

#### Scenario: Subtitle or step numbers without their zone

- **WHEN** a slide gives a subtitle and the chosen slide has a body but no subtitle zone, or gives items numbered 1, 2, 3… and the chosen slide has no number zone
- **THEN** the subtitle leads the body as an unbulleted line and the step numbers are left to the item order, and neither counts as lost content

#### Scenario: Fewer items than the template shows

- **WHEN** a repeated group is filled with fewer items than its count
- **THEN** the unused items and the decoration drawn only for them are removed and the kept items are recentred

#### Scenario: Overflow control

- **WHEN** a text is too long for its slot at its font size
- **THEN** the font is reduced down to a floor, measured with the font the slot is drawn in; text still too long is cut at a word boundary and reported, and shrinking alone is not reported as a truncation

#### Scenario: Images from team folders

- **WHEN** the plan names a valid image document for a slide with an image slot
- **THEN** it is placed keeping its aspect ratio; an image slot left empty is removed, and an invalid reference is named in the result

#### Scenario: Malformed plan from the model

- **WHEN** the plan has wrong JSON shapes (a bullet list as one string, a field under an alias or given twice, a non-object entry)
- **THEN** the tool coerces what it can without losing text, a non-object entry is named in the result, and a key it cannot map is a `needs_revision` problem

### Requirement: Tables fill the template's table

The system SHALL fill a `table` pattern's table from a plan's `table` (`header`, `rows`), keeping the template's table style, column count bound and slide position, and SHALL NOT cut a cell's text or draw a table the template does not hold.

#### Scenario: Rows and columns adapted

- **GIVEN** a template table of 12 rows × 5 columns with a header row
- **WHEN** a plan gives a header and 6 rows of 4 cells
- **THEN** the header row and 6 body rows are written, surplus rows removed, the fifth column removed and the others widened to the same total width, and the frame height follows the rows

#### Scenario: More rows than the template shows

- **WHEN** the rows fit the table's line budget at full size or at the shrink floor although they outnumber the template's rows
- **THEN** body rows are cloned from the last one with fresh row ids and one font scale applies to the whole table

#### Scenario: Table too large

- **WHEN** the rows exceed the line budget at the shrink floor, or give more columns than the template
- **THEN** no deck is written and `needs_revision` names the limits (lines needed vs held, longest cell and its column's characters per line, columns given vs max) with options (split the rows over two slides, shorten cells)

#### Scenario: No table slide in the template

- **WHEN** a plan gives a table and no included pattern has a table slot
- **THEN** the slide is a misfit naming the missing table, never converted to bullets silently

#### Scenario: No template cell text left

- **WHEN** a table slide is rendered
- **THEN** no template cell text remains, the frame stays on the slide and any shrink is reported

### Requirement: Built-in Fred template when none is configured

The system SHALL ship a real `.pptx` template with example slides and its pre-computed analysis, and SHALL use it, through the same assignment and rendering path as a customer template, when the agent has no template.

#### Scenario: Agent without template

- **WHEN** an agent enables the capability without uploading a template
- **THEN** the tool is available at once and builds decks from the built-in template's example slides

#### Scenario: Built-in analysis kept current

- **WHEN** the analysis rules change
- **THEN** a test fails until the built-in template's stored analysis is regenerated

### Requirement: Delivery

The system SHALL write the generated deck to the conversation's agent workspace, publish a PDF preview beside the chat when conversion is available, and otherwise offer a download.

#### Scenario: Preview available

- **WHEN** the deck is generated and PDF conversion succeeds
- **THEN** the chat shows the `ppt_filler` preview card and side pane with a download of the `.pptx`, even when the agent has no `ppt_filler` capability

#### Scenario: Deck rebuilt within one answer

- **WHEN** the agent builds the deck several times before answering
- **THEN** the answer shows a single preview card, for the last build

#### Scenario: Preview unavailable

- **WHEN** PDF conversion fails or is unavailable
- **THEN** the chat shows a download chip and the agent is told the preview is unavailable

### Requirement: Chat-time corrections are per conversation

The system SHALL let the user correct a deck in chat by regenerating from an amended plan, and SHALL NOT change the agent configuration from a conversation.

#### Scenario: User asks for a different kind of slide

- **WHEN** the user says a slide should be another kind of slide
- **THEN** the agent rebuilds the deck with that slide's `kind` changed, and the stored analysis and overrides are unchanged
