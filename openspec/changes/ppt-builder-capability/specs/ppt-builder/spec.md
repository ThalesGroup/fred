## Purpose

Lets an agent generate a PowerPoint presentation from a chat request on an unannotated corporate template — analysed once, in the background, into labelled archetypes — or on the built-in Fred template, choosing each slide in code and delivering a preview and a download.

## ADDED Requirements

### Requirement: Template analysis needs no annotation

The system SHALL inventory an uploaded `.pptx` without requiring any marker, note or shape name. The inventory SHALL hold master layouts and example slides as patterns, each with a stable id, a label, a `kind` from the closed vocabulary (`cover`, `agenda`, `section`, `bullets`, `two_columns`, `comparison`, `cards`, `figures`, `process`, `timeline`, `team`, `quote`, `image_text`, `closing`, `other`), a reusable flag, its text and image slots with capacities, and its repeated groups with their item count.

#### Scenario: Every text shape of an example slide is a slot

- **WHEN** an example slide holds text boxes with real corporate text rather than sample text
- **THEN** each text-bearing shape is a slot, except text repeated on two or more slides and footer, date or slide-number fields

#### Scenario: Layout classified from its placeholders

- **WHEN** a layout has a title placeholder and one body placeholder
- **THEN** the inventory holds a `bullets` pattern for it with a title slot and a body slot

#### Scenario: Repeated sibling groups become a list

- **WHEN** an example slide holds three or more sibling groups of identical structure
- **THEN** the inventory exposes one repeated group with its item count and per-item slots, so a plan may fill fewer items

#### Scenario: Resource slides are excluded by default

- **WHEN** an example slide is an icon bank, or a chart or table is its main content
- **THEN** it is inventoried but excluded, and the summary counts it as excluded

#### Scenario: Optional annotations refine the analysis

- **WHEN** a shape name or a speaker-note line states a role, kind or label
- **THEN** it takes precedence over the heuristics and the vision label for that shape or slide

#### Scenario: Unreadable or oversized upload

- **WHEN** the upload is not a readable `.pptx` or exceeds 50 MB
- **THEN** the save fails with one error carrying a stable code, and no analysis starts

### Requirement: Example slides are labelled by a vision model

The system SHALL render each example slide to an image with its slots numbered and ask a vision-capable model for the slide's kind, label, the purpose of each slot, the maximum number of items and whether the slide is reusable. Geometry and capacities SHALL stay those of the deterministic analysis.

#### Scenario: Vision label applied

- **WHEN** the model returns a valid label for an example slide
- **THEN** the pattern takes that kind, label, slot purposes and reusable flag

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

#### Scenario: Overrides after re-upload

- **WHEN** a new template version is analysed
- **THEN** overrides whose pattern still exists are re-applied and the others are dropped and reported in the form

### Requirement: Slides are chosen by the code

The system SHALL accept from the model a plan of slides carrying content only — title, subtitle, bullets, columns, items, images, notes and an optional `kind`, last in the schema — and SHALL assign each slide to a pattern deterministically. The tool schema and description SHALL NOT expose pattern ids; the description SHALL list the kinds the template offers with their capacities.

#### Scenario: Example slide preferred over a layout

- **WHEN** both an example slide and a layout of the slide's kind fit its content
- **THEN** the example slide is chosen, duplicated with its decoration intact and filled

#### Scenario: Kind inferred from content

- **WHEN** a slide gives no `kind`
- **THEN** its kind is inferred from the shape of its content (items with figures → `figures`, two columns → `two_columns`, ordered items → `process`, …)

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

### Requirement: No silent fallback

The system SHALL NOT substitute an unfitting pattern for a slide. When a slide fits no pattern, the tool SHALL build nothing and return a structured error the model can act on.

#### Scenario: Slide fits nothing

- **WHEN** one slide of the plan fits no included pattern (for example seven items where the largest list holds six)
- **THEN** no deck is written and the result lists, per failing slide, its index, the problem and options available in this template (split, trim to N items, another kind)

#### Scenario: Repair loop

- **WHEN** the model calls the tool again with a corrected plan
- **THEN** the deck is built from the corrected plan as a whole, replacing any earlier build

#### Scenario: Success message invites correction

- **WHEN** a deck is built with truncations, removed leftovers or lost content
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

- **WHEN** the plan has wrong JSON shapes (a bullet list as one string, unknown keys, a non-object entry)
- **THEN** the tool coerces what it can, and anything it could not place is named in the result

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
