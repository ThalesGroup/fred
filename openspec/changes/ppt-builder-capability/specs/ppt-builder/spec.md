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

#### Scenario: Repeated heading and text pairs become a list, whatever their placeholder types

- **GIVEN** a slide or layout where no group or row was found, holding two size classes of text shapes as many each (placeholders typed TITLE or SUBTITLE included, as Google Slides exports type them), every bigger-font shape with its own text right of it, or above or under it in its column
- **WHEN** it is analysed
- **THEN** three or more (heading, text) pairs form one repeated group read row by row, a staircase left to right: `cards`, or `figures` when the headings are figures ("333,000", "386,000 km", "xx%") captioned by a `label`, `timeline` when they are years or "20XX", `cards` again for numbered texts laid out in a grid of rows and columns, `process` for numbered texts along one line
- **AND** two plain pairs stay separate slots, the column headings and bodies of a `two_columns` slide, and a lone big figure with its caption is a one-item `figures` slide
- **AND** a SUBTITLE placeholder covering a fifth of the slide or more is a body, so a paragraph slide is never a cover, and a text repeated on other slides stays a slot when its slide holds two same-size slots beside it

#### Scenario: Column bodies stay columns

- **GIVEN** a two- or three-column layout whose bodies are wider than 35 % or taller than 40 % of the slide
- **WHEN** it is analysed
- **THEN** its bodies stay separate slots and no repeated group is made

#### Scenario: Example slide that copies its layout

- **GIVEN** an example slide holding every placeholder of its layout (empty picture placeholders included), with or without drawn decoration
- **WHEN** it is analysed
- **THEN** the inventory holds one pattern for that design, the slide (copied and filled), with its sample text, notes, shape names and position taken into account, and no separate pattern for the layout

#### Scenario: Placeholders sharing an index

- **GIVEN** an example slide with two placeholders of the same `idx`, top-level slots or the picture slots of a repeated group
- **WHEN** it is analysed and then filled, pictures included
- **THEN** each gets its own slot key (the first in drawing order keeps the `idx`, the next one its shape path), the pattern carries a warning, and each slot is filled on its own, the picture in that slot's own frame; the deck never fails on it

#### Scenario: First slide is the cover

- **GIVEN** a first example slide with a title slot and no body content
- **WHEN** no template hint states another kind
- **THEN** its kind is `cover`

#### Scenario: Resource slides are excluded by default

- **WHEN** an example slide is a library slide, or a chart or a table that is not a data table is its main content (merged cells, or per-cell fills that vary across the body, as in a Gantt grid)
- **THEN** it is inventoried but excluded, and the summary counts it as excluded

#### Scenario: Library slides are never a design

- **GIVEN** an example slide that is a resource sheet rather than a design: an icon sheet (twenty or more small text-free pictures, groups or freeform glyphs), a slide titled as a resource page (icons, fonts, typography, palette, attributions, credits, graphic resources, instructions for use, this template), or a slide with no placeholder and no text but links that draws eight or more shapes (editable graphics) or a linked picture (a promotion)
- **WHEN** it is analysed
- **THEN** it is excluded with the reason `library`, so no deck slide is ever built on it, and its shapes stay in the stored template for a later change to reuse

#### Scenario: A few icons beside text stay a design

- **GIVEN** an example slide with three or four icons next to its text, or a closing "Thank you" slide asking to keep an attribution
- **WHEN** it is analysed
- **THEN** it is not a library slide and keeps its kind

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

#### Scenario: Zip bomb refused before it is inflated

- **WHEN** an upload under 50 MB declares members that would inflate beyond 512 MB in total or 256 MB for one member, or a member over 10 MB compressed more than 100 times
- **THEN** the save (of `ppt_builder` or `ppt_filler`) fails as an unreadable template without decompressing the archive, and no analysis starts

### Requirement: Example slides are labelled by a vision model

The system SHALL render each example slide to an image with its slots numbered and ask a vision-capable model for the slide's kind, label, the purpose of each slot, the maximum number of items and whether the slide is reusable. Geometry and capacities SHALL stay those of the deterministic analysis.

#### Scenario: Vision label applied

- **WHEN** the model returns a valid label for an example slide
- **THEN** the pattern takes that kind, label, slot purposes and reusable flag

#### Scenario: Vision label incompatible with the slots

- **WHEN** the model's kind needs slots the slide does not have (for example `bullets` without a body slot, `cover` without a title slot, `cards` without a repeated group)
- **THEN** the slide keeps its heuristic kind, takes the model's label and slot purposes, and the rejection is logged and shown as a pattern warning

#### Scenario: Labelling model revoked during an analysis

- **WHEN** the team loses access to the labelling model while an analysis runs
- **THEN** the analysis stops using that model within 30 seconds

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

#### Scenario: Same file uploaded again

- **GIVEN** a succeeded analysis made by the current rules
- **WHEN** the author uploads the same file again with the same labelling settings
- **THEN** the analysis is kept as is and the agent stays available

#### Scenario: Status visible in the form

- **WHEN** the author views the agent form while the analysis is pending or running
- **THEN** the form shows that the analysis is in progress, and shows the summary and thumbnails once it has succeeded

#### Scenario: Any replica serves the result

- **WHEN** the analysis ran on one replica and a turn or a status request reaches another
- **THEN** that replica reads the same stored result

#### Scenario: Interrupted analysis recovers

- **WHEN** the replica running an analysis stops before finishing
- **THEN** the analysis is reported as interrupted once its lease expires, and the next readiness check, turn or save restarts it
- **AND** a vision-labelled analysis is restarted by a readiness check or a turn only on a replica holding the model port the agent's last save left; elsewhere (after a restart, on another replica) it stays interrupted, the agent unavailable, until a save, which carries the port, re-runs it with vision; it never comes back labelled by rules

#### Scenario: Agent unavailable while analysing

- **WHEN** an agent's template analysis is pending or running
- **THEN** the agent is shown as unavailable, with the reason, on the team agents page and cannot be selected in the chat agent picker
- **AND** the agent card and the agent form say the template is being read and that the agent will be available again automatically in a few minutes, in the user's language; an agent whose preparing capability cannot be told apart (several capabilities declare what they prepare) gets the generic text that the agent will be available again in a few minutes with nothing to do

#### Scenario: Agent available when analysis succeeds

- **WHEN** the analysis succeeds
- **THEN** the agent becomes available without another save

#### Scenario: Agent becomes available on next listing after analysis completes

- **WHEN** the analysis succeeds while nobody has the agent form open
- **THEN** the next listing of the team's agents re-checks the agent and shows it available, and a pod that does not answer in time leaves it unavailable without delaying the listing
- **AND** a failed analysis is not re-checked by the listing; it changes on a save or the form's re-check
- **AND** with more than ten preparing agents, each listing checks ten of them, so every one gets its turn

#### Scenario: No readiness answer after a save

- **WHEN** an agent with a capability is saved, created or copied and the pod gives no readiness answer (timeout, error, unreachable)
- **THEN** the agent is unavailable until a listing, re-check or sweep gets an answer; a save never makes a preparing agent available, even briefly

#### Scenario: Readiness hook fails

- **WHEN** a capability's readiness check raises an error
- **THEN** the capability is reported as still preparing and the agent stays unavailable

#### Scenario: A slow check never undoes a newer suspension

- **WHEN** an agent is suspended for another reason while a readiness check is in flight
- **THEN** the check's answer does not clear or replace that suspension

#### Scenario: Copied agent waits for its analysis

- **WHEN** an agent with a custom template is copied to a team
- **THEN** the copy's analysis runs with the destination team's model routing, and the copy is unavailable until it succeeds

#### Scenario: Failed or interrupted analysis

- **WHEN** the analysis fails or is interrupted
- **THEN** the agent stays unavailable, the agent form shows the error and that saving the agent re-runs the analysis, and a save re-runs it from the stored template with the model port the save carries

#### Scenario: Build requested before analysis completes

- **WHEN** the build tool is reached while the template analysis has not succeeded
- **THEN** the tool builds nothing and returns a short message that the template analysis is not ready

#### Scenario: Deck rendered on the analysed template only

- **GIVEN** a save that stored a new template while a turn still runs on the previous config
- **WHEN** that turn builds a deck
- **THEN** the deck is rendered on the template its analysis was made from, or the tool refuses; it never renders the newer file with the older inventory

#### Scenario: Only team members reach a team's capability services

- **WHEN** a user saves or copies a capability config for a team whose agents they cannot edit, or checks readiness for a team whose agents they cannot use
- **THEN** the pod refuses the request before building any service scoped to that team, including its models

#### Scenario: Only agent editors see the analysis

- **WHEN** a user who cannot edit the agent requests its analysis status or thumbnails
- **THEN** the request is refused

#### Scenario: Analysis rules change

- **GIVEN** an agent whose succeeded analysis was produced by older analysis rules
- **WHEN** its readiness is checked, a turn reads the analysis, or the agent is saved
- **THEN** the agent stays available and its turns keep using the stored analysis, and one re-run starts in the background from the stored template, without a user token
- **AND** concurrent checks on any replica start no second re-run while one is running, and the agent form shows the analysis as being read again meanwhile, without offering a re-run, then shows the new result when it ends, without a reload
- **AND** once the re-run succeeds its result is used; when it fails, the stored analysis stays in use, no re-run starts automatically again, and the form says that saving the agent re-runs it, which a save does

#### Scenario: Vision-labelled analysis refreshed only with its model

- **GIVEN** an outdated succeeded analysis labelled by a vision model
- **WHEN** its readiness is checked or a turn reads it on a replica that holds no model port remembered from the agent's last save
- **THEN** no re-run starts, the agent stays available on the stored analysis, and the agent form shows it as outdated with the hint that saving the agent re-reads it
- **AND** on a replica holding that port, one re-run starts as for a rules-labelled analysis, and a save always starts one with the port it carries
- **AND** a job that still runs without the port for a vision labelling (a save on a pod that gives none) logs a warning and records the rules labelling it used, so a later save with the port relabels it with vision

#### Scenario: Background analyses leave room for turns

- **WHEN** many analyses run at once on a pod (an analysis rules change refreshing every template)
- **THEN** they hold at most two of the pod's four heavy-job slots, so building a deck is not refused as busy because of them

### Requirement: Author review

The system SHALL let the author review the analysis — a thumbnail, label and kind per pattern — and change a pattern's label or kind or exclude/include it. Overrides SHALL be the only author input persisted besides the template, SHALL survive an ordinary save, and SHALL never be required.

#### Scenario: No review required

- **WHEN** an author uploads a template and saves without opening the review
- **THEN** the agent builds decks with the automatic analysis once it has succeeded

#### Scenario: Override applied

- **WHEN** an author excludes a pattern or changes its kind
- **THEN** the assignment never uses an excluded pattern and treats a re-kinded pattern as its new kind

#### Scenario: Other slide re-kinded in the review

- **WHEN** the analysis read a slide as `other` (never chosen) and the author changes its kind to a real kind
- **THEN** the assignment uses the slide as that kind, as a `kind:` note in the template would; re-kinded back to `other`, it is unused again

#### Scenario: Example slides and layouts shown apart

- **WHEN** the author opens the review
- **THEN** the example slides of the deck come first, the remaining layouts follow in a separate collapsed section marked as fallback, excluded patterns last, and each card's controls stay inside it
- **AND** the excluded section opens by itself when the analysis set some of them aside, and a pattern the analysis set aside keeps its reason when the author excludes it too

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
- **THEN** the slide is assigned to a fitting pattern of a kind close to the requested one, and the success message names the substitution, why, and how to get the requested kind

#### Scenario: Semantic fallback

- **WHEN** a slide asks for `agenda` with 17 items, the agenda slide holds 8 items (two slides hold 16) and a process slide holds 20
- **THEN** the slide is built on the process slide, never on a team, figures, cards or other unrelated slide, and the note reads "built as 'process' instead of 'agenda': the 'agenda' slide does not fit (items: 17 given, max 8). To get the 'agenda' slide, call again and trim to 8 items or split them over two slides; otherwise nothing to do."

#### Scenario: No absurd substitution

- **WHEN** a slide asks for `agenda` with 17 items, the agenda slide holds 8 items, a team slide holds 30 and no close kind (bullets, process, timeline) holds the content
- **THEN** no deck is written and `needs_revision` names the slide with `items: 17 given; the largest 'agenda' slide holds 8, two slides hold 16`, the options `trim to 16 items (beyond 8 they continue on a second slide)` and `or keep 8 here and move the rest to slides of your own`, and what each close kind the template offers takes; the team slide is never offered

#### Scenario: Overflowing list continues on a same-kind slide

- **WHEN** a slide asks for `agenda` (or, with no kind, its content suits `agenda` first) with 9 items, the agenda slide holds 8, and each half fits it
- **THEN** the deck holds two agenda slides of 5 and 4 items, titled with ` (1/2)` and ` (2/2)` after the slide's title, preferably on the same template slide, before any close-kind fallback
- **AND** the delivery note reads `Slide 2: its 9 items continue on a second 'agenda' slide (5 + 4, titles marked (1/2) and (2/2)): the largest 'agenda' slide holds 8. Nothing to do; to keep one slide, send at most 8 items.`
- **AND** a table whose rows overflow every table slide of its kind is split the same way, its header repeated on each part
- **AND** bullets, columns and a single field too long are never split

#### Scenario: Numbering kept across the split

- **WHEN** a list of 9 items is split over two slides
- **THEN** items numbered by the model keep their numbers (6 to 9 on the second slide), and items without numbers on a slide that shows numbers continue the count (06 to 09) instead of restarting at 01
- **AND** that count is set at render, never stored: when a later change removes an item from the first part, the second part is numbered on from the first part's new count

#### Scenario: Variety not triggered by a split list

- **GIVEN** a first deck of the conversation and a variety check that is not `off`
- **WHEN** one slide's list is split over two slides of the same template slide
- **THEN** the two parts count as one slide: no variety ask, repeat note or "same template slide" note names them, while another slide using that template slide still counts normally

#### Scenario: Split cap reached

- **WHEN** a list needs more than two slides of its kind (17 items where the kind's largest slide holds 8) and no close kind holds it whole
- **THEN** no deck is written and `needs_revision` names the slide, the kind's capacity over two slides, and the options to trim to what two slides hold or move the rest to slides of the model's own

#### Scenario: One numbering after a split

- **WHEN** slide 2 of a plan is split over two slides and slide 5 of the plan has a review note
- **THEN** the deck is delivered with the message naming that slide 6, its place in the file, the delivery says later `changes` use the file's slide numbers, and the stored base plan is the deck as delivered (each part a slide with its rendered title, entries and kind), so a later `changes` call numbers on the file
- **AND** an agenda split over two slides announces its items once, the slides that follow being counted after its last part

#### Scenario: Stored split rebuilt as it is

- **GIVEN** a stored deck whose slides 2 and 3 are `Offers (1/2)` and `Offers (2/2)` from an earlier split
- **WHEN** a later `changes` call rebuilds the deck
- **THEN** the two slides are neither split nor suffixed again, stay on one template slide, and count as one slide for variety, even at a max of one use

#### Scenario: A part left alone drops its part number

- **GIVEN** a stored deck whose slides 2 and 3 are `Offers (1/2)` and `Offers (2/2)` from an earlier split
- **WHEN** a later call inserts a slide between them, moves one away or removes one
- **THEN** the part numbers of delivered slides are recounted on the deck as it stands: a part left alone is titled `Offers`, parts swapped back in order read `(1/2)` and `(2/2)`
- **AND** a title on a slide never delivered, or with a count above two, keeps its own words

#### Scenario: Fit check

- **WHEN** a pattern lacks a slot for a non-empty field, holds fewer items than the slide carries, or cannot hold the text above the shrink floor
- **THEN** that pattern is not a candidate for the slide

#### Scenario: The cover opens the deck, never forced

- **WHEN** a deck is assigned on a template holding a cover pattern
- **THEN** only the first slide may use the cover; a first slide with no `kind` holding only a title and subtitle uses it
- **AND** a first slide with another `kind` or another content shape keeps it, so a deck without a cover (a single summary slide, "no cover", slide 1 removed) is built as sent

#### Scenario: Closing at most once, last

- **WHEN** a plan holds closing content
- **THEN** a closing pattern is used at most once and only for the last slide

#### Scenario: Variety

- **WHEN** three consecutive slides would use the same pattern and another fitting pattern exists for one of them
- **THEN** the assignment uses the alternative; when none exists the repetition is allowed and reported

#### Scenario: Each template slide once where possible

- **GIVEN** a pattern already used earlier in the deck, not necessarily on the previous slide
- **WHEN** an unused pattern of the same kind tier also fits the slide
- **THEN** the unused pattern is chosen; a pattern used three times or more is reported in the success message with the kinds its content suits, when the template holds one

#### Scenario: First deck asked to vary once

- **GIVEN** a conversation whose history holds no delivered deck yet
- **WHEN** the variety check is `template_slide` (the default) and the assignment uses one template slide that is not a cover, section, agenda or closing three times or more, and the content of one of those slides suits another kind the template holds (`suggested`, checked against that content)
- **THEN** no deck is written and `needs_revision` names the repeated slides and the suggested recasts; the next call is built as sent, even when it repeats the same plan
- **AND** a template slide never checked against the content (an unused variant, one slide per other kind) is never offered

#### Scenario: Later deck keeps the note

- **GIVEN** a conversation where a deck was already delivered
- **WHEN** a new plan uses one template slide three times or more
- **THEN** the deck is built and the repetition is only reported in the success message

#### Scenario: First deck read from the conversation history

- **GIVEN** the messages sent to the model in the current turn
- **WHEN** they hold an earlier `build_presentation` result that delivered a deck
- **THEN** the conversation has a deck and no variety ask is returned, also when the platform has cleared the messages' names (the result is matched by its tool call id) or the result's content is a list of text blocks
- **AND** when its only `build_presentation` results are `needs_revision` or errors, or another tool's text reads like a delivery, the conversation still has no deck and the first call of the turn may ask

#### Scenario: Choice guide in the description

- **WHEN** the tool description is built
- **THEN** it says, for the kinds the template offers, which content suits each (numbers → figures, dates → timeline, parallel items → cards, ordered steps → process, a comparison → table, not restated as columns)
- **AND** when the variety check is on, it states the maximum: with `variety_max_uses` 1, that each slide of the deck must look different; otherwise at most N uses of any variant (`template_slide`) or at most N slides of any non-structural kind (`kind`); with the check off it states no maximum

#### Scenario: One kind on three slides is a repeat

- **GIVEN** a conversation whose history holds no delivered deck yet
- **WHEN** the variety check is `kind` and one non-structural kind (for example `bullets`) is used on three slides or more, even on three different template slides
- **THEN** no deck is written and `needs_revision` names those slides and the kind, once per turn; a resend is built as sent; cover, section, agenda and closing slides never count as a kind repeat

#### Scenario: Alternatives read from the content

- **GIVEN** a kind repeat whose slides hold dated lines on one slide and `Label :` header lines followed by `- ` lines on two others
- **WHEN** the variety ask is returned
- **THEN** it names the first slide with `timeline` and the two others with `two_columns` and `cards` (one kind per slide, spread across kinds), only when the template offers that kind with a slide holding that many entries; the suggestions come from text patterns, without any model call

#### Scenario: Variety asked on the first call only

- **GIVEN** a conversation whose history holds no delivered deck yet
- **WHEN** the first `build_presentation` call of the turn has a fit problem and no kind repeat, and the corrected second call repeats one kind on three slides
- **THEN** the second call is built, with the repetition only reported in the success message: no variety ask after a fit repair
- **AND** a first call refused before its plan is evaluated (unreadable, every slide empty, bad changes) does not use up the turn's ask: the corrected call is still asked

#### Scenario: A change to a delivered deck is never asked to vary

- **GIVEN** a delivered deck, and a later turn whose history no longer shows that delivery (trimmed)
- **WHEN** the model sends `changes` that make one template slide repeat
- **THEN** the deck is built with the repetition only reported in the success message: a `changes` call always has a delivered deck as its base

#### Scenario: Variety ask merged with fit problems

- **GIVEN** a conversation whose history holds no delivered deck yet
- **WHEN** the first call of the turn has slides that fit nothing and, among the slides that fit, one kind on three slides or more
- **THEN** one `needs_revision` lists the fit problems and the variety block together, and the next call is built once it fits, whatever its kinds

#### Scenario: Slides to fix that repeat are asked in the same round

- **GIVEN** a conversation whose history holds no delivered deck yet and a variety check that is not `off`
- **WHEN** the first call of the turn has slides that fit nothing and whose closest fits, counted with the slides that fit, put one template slide (or kind) over its cap
- **THEN** the `needs_revision` lists those slides under `slides` with their fit problems and under `variety` as a repeat, in the same round
- **AND** no option or suggestion for them names a template slide that has the same fit problem
- **AND** when the next call fixes the fit problems with the kinds unchanged, the deck is built as is, the repeat only noted

#### Scenario: The limit counts within each section

- **GIVEN** a first deck with two sections, each starting at a `section` slide (or, when the deck has none, at a slide titled as an entry of its agenda), and a variety cap of 2
- **WHEN** one template slide is used twice in Italy (its 2nd and 4th content slides) and twice in Spain (its 1st and 3rd)
- **THEN** no variety ask is returned and the deck is built: the count resets from one section to the next, so a later section may reuse an earlier one's slides in any order
- **AND** the same slides without section boundaries count four uses and are asked to vary; a deck with fewer than two sections is one section; cover, agenda, section and closing slides are never counted
- **AND** the variety ask and the choice guide say that the limit counts within each section and that a later section may reuse an earlier one's slides

#### Scenario: Three uses inside one section are revised

- **GIVEN** a first deck with two sections and a variety cap of 2
- **WHEN** one template slide is used three times inside one section, wherever it sits in it
- **THEN** `needs_revision` lists those three slides under `variety` with `at_most` 2; the other section's uses are not listed

#### Scenario: Three identical slides in a row are revised across a section boundary

- **GIVEN** a first deck whose sections start at agenda entries, so no section slide separates them
- **WHEN** the last two content slides of one section and the first of the next use the same template slide and no other slide fits them
- **THEN** `needs_revision` lists those three slides under `variety` with `in_a_row` true, although each section is within its cap; when another slide fits, the assignment avoids the run itself

#### Scenario: Identical slides the user asked for are built and noted

- **GIVEN** the same deck, with `repeat_layout` true on the third slide of the run (the user explicitly asked for identical consecutive slides)
- **WHEN** the deck is assigned
- **THEN** that slide keeps the previous slide's template slide, is left out of the per-section cap and of the three-in-a-row rule, no variety ask is returned and the deck is built
- **AND** the agent's notes say the slide keeps the previous slide's template slide as the user asked, and the "What was built" summary carries `layout_repeated` on it
- **AND** when its content does not fit the previous slide's template slide, it is built on another one, with a note saying how to keep the layout and `layout_not_repeated` in the summary
- **AND** the tool description says to set `repeat_layout` only when the user explicitly asked for identical consecutive slides, never on the model's own initiative; `{"op": "edit", "slide": N, "field": "repeat_layout", "value": true}` sets it on a delivered deck

#### Scenario: Suggestions state what the slide holds

- **WHEN** the variety ask suggests a kind for a slide from its content
- **THEN** the suggestion quotes, from the inventory, what the favoured variant of that kind holds: `up to N items` with each item field and its size, or `exactly 2 columns` with the heading and bullets sizes
- **AND** when the slide's longest entry is longer than that room, it says to shorten each entry to that size
- **AND** a kind whose variants cannot hold the slide's entries is not suggested

#### Scenario: Later deck notes the kind repeat

- **GIVEN** a conversation where a deck was already delivered
- **WHEN** a new plan uses one non-structural kind on three slides or more
- **THEN** the deck is built and the success message names the slides, the kind and the content-based alternatives

#### Scenario: Structural slides are never part of a repeat

- **GIVEN** a plan whose agenda slide, too long for the template's agenda slide, is built on a bullets slide, beside two bullets slides
- **WHEN** the first call of the turn is assessed
- **THEN** no variety ask is returned: a slide asked (or inferred) as cover, section, agenda or closing, or built on such a template slide, never counts towards a repeat and is never named in an ask

#### Scenario: Suggestions capped by the template's variants

- **GIVEN** a template with a single `figures` variant and a deck that already has one figures slide
- **WHEN** a variety ask is returned
- **THEN** its suggestions do not offer `figures`; a kind is offered only while its distinct variants outnumber the deck's slides of that kind, counting each suggestion of the same answer

#### Scenario: Variety check setting

- **GIVEN** the capability's `variety_check` setting, `template_slide` (default), `kind` or `off`
- **WHEN** a deck is built on the next turn after the setting changed
- **THEN** the ask follows the setting without re-analysing the template; `off` never asks; every mode keeps the passive note and the choice guide's content pairs; an agent saved before the setting existed uses `template_slide`

#### Scenario: Max uses setting

- **GIVEN** the capability's `variety_max_uses` setting, 1 to 5, default 2, and a variety check that is not `off`
- **WHEN** a first deck of the conversation is assessed on the first call of the turn
- **THEN** a variety ask is returned when one non-structural template slide (`template_slide`) or kind (`kind`) is on more slides than the maximum, and each variety entry states that maximum; with 2 the ask comes from the third use, as before the setting existed
- **AND** an agent saved before the setting existed uses 2, and changing it never re-runs the analysis

#### Scenario: Max uses steers the assignment

- **GIVEN** a variety check that is not `off`, `variety_max_uses` 1, and four bullets slides on a template with four bullets variants that fit them
- **WHEN** the deck is assigned
- **THEN** each slide gets a different variant; a slide whose requested kind has fewer variants than its slides keeps that kind (the reuse is priced, never switched to another kind)

#### Scenario: Max uses never demands the impossible

- **GIVEN** `variety_max_uses` 1 and more content slides in the deck than the template has content template slides (or, in `kind` mode, content kinds)
- **WHEN** the deck is assessed
- **THEN** the maximum applied, one for the whole deck, is raised to the content slides divided by those template slides (or kinds), rounded up, so a deck within that is neither re-priced nor asked; cover, agenda, section and closing slides never count
- **AND** a kind with fewer variants than its slides gets no higher maximum of its own: while the deck as a whole fits, its extra slides are priced and asked to recast

#### Scenario: Variety row in the agent form

- **GIVEN** the ppt_builder settings in the agent form
- **WHEN** the author turns the variety switch off
- **THEN** `variety_check` is saved as `off` and the mode and max selects are disabled; turning it on restores the last mode (`template_slide` by default); the max select saves `variety_max_uses`

#### Scenario: Empty item pictures are a cost

- **WHEN** a slide's items carry no images and both a card pattern with item pictures and one without fit
- **THEN** the pattern without pictures is chosen

#### Scenario: A picture framed by its layout needs a picture

- **GIVEN** a template slide whose picture zones sit on a shape of its layout or master (not a placeholder, no text, under half the slide), such as Paintress "3 colonnes d'image + texte" over its layout's grey band
- **WHEN** a slide asking for that slide's kind carries no picture for a framed zone (or for a used item's framed zone)
- **THEN** that template slide is not a candidate: the slide is built on another variant or kind, or, when nothing else holds it, `needs_revision` names the missing picture; the catalogue quotes those pictures as required
- **AND** with a picture for each framed zone it is a candidate as before
- **AND** only pictures that load count: an id that is missing or not an image document counts as no picture, and the tool reports it as left out

#### Scenario: Field limits in the tool schema

- **WHEN** the tool schema is built for a template
- **THEN** each text field's description states its room from the inventory: per kind, the largest variant's room for that field (the catalogue's measure), as the most common value across kinds plus the kinds that differ, the cover's own room included
- **AND** no field carries a hard `maxLength`, so an over-long text still reaches the tool and gets `needs_revision`

#### Scenario: Limits phrased in words

- **GIVEN** any template, a zone measured at C characters per line × L lines
- **WHEN** the description, the schema hints or a `needs_revision` result quotes that zone's room
- **THEN** it reads as a word budget followed by the measured characters (`≤4 words (≈32 chars)`, `≤20 words (≈71 chars × 2 lines)`, `1 word (≈12 chars)`), the words being `floor((C + 1) / 7)` per line × L, at least one ("1 short word" under 6 characters per line), from the same rule on every template
- **AND** the fit check still measures characters against the same room, and a shortening option names the same target (`shorten items[2].label to 1 word (≈12 chars)`)

#### Scenario: A list field states how many entries its zone holds

- **GIVEN** a `bullets` or `columns.bullets` zone of L lines, each entry starting its own paragraph, so it holds at most `floor(L / 0.7)` entries at the smallest font
- **WHEN** the description or the schema hints quote that field's room
- **THEN** the lines are always shown and the entry limit follows (`≤14 words (≈101 chars × 1 line, max 1 entry)`)
- **AND** when a slide gives more entries than that, the misfit names the count and the limit, not characters (`bullets: 3 entries; this zone holds 1 line (≈101 chars): at most 1 entry`), with the option `merge bullets into at most 1 entry, or use another kind`
- **AND** when the count fits but entries wrap past the zone, the misfit names the lines they take and the lines the zone holds at the smallest font (`bullets: 2 entries wrap to 23 lines; this zone holds 11`), with the option to keep each entry to one line

#### Scenario: Item heading without a heading zone

- **GIVEN** items with a heading and a text, and a list whose items have a single text zone
- **WHEN** the heading and the text fit that zone together
- **THEN** the heading leads the item's text in bold and nothing is reported lost

#### Scenario: Template icons kept

- **WHEN** a card slide with icons is filled and some cards are removed
- **THEN** the remaining cards keep the template's icons and the removed cards' icons leave with them

### Requirement: The agent builds directly

The system SHALL instruct the agent to write the plan and call `build_presentation` in the same answer, and to ask the user to validate an outline only when the user asked for it or the request does not say what the presentation is about.

#### Scenario: Request with a subject

- **WHEN** the user asks for a presentation on a stated subject without asking to see the plan first
- **THEN** the agent's working rules tell it to build the deck in that answer rather than propose an outline and ask for confirmation

#### Scenario: User asks to validate the plan

- **WHEN** the user asks to see or validate the outline first, or gives no subject
- **THEN** the working rules allow the agent to ask before building

#### Scenario: A revision request

- **WHEN** the user asks to change a delivered deck
- **THEN** the working rules tell the agent to do only what was asked (any other slide or content is proposed, not added), to send `changes` for the slides concerned and the whole deck only for a new deck or a rewrite of most slides, to ask which slide when the request names none, to say a deck was built or changed only after a delivery in that answer and to describe only what the result lists, and to say so when nothing needed changing or could be applied

#### Scenario: A request for another template

- **WHEN** the user asks to use another template
- **THEN** the working rules name the template in use (the built-in one, or the one uploaded in the agent's settings) and say the tool cannot switch it: an editor of the agent uploads another in its settings

### Requirement: No silent fallback

The system SHALL NOT substitute an unfitting pattern for a slide. When a slide fits no pattern, the tool SHALL build nothing and return a structured `needs_revision` result the model can act on. An expected revision SHALL NOT be returned as a failed tool call: only a bad call, an unavailable template, a busy server, a render or a storage failure SHALL be an error.

#### Scenario: A revision is not a failed call

- **WHEN** a call is refused for fit problems, for a variety ask, as a resend identical to a call refused this turn, as a later call of one model round, or as a deck that changes nothing (unchanged changes, a resend of the deck just delivered)
- **THEN** the tool result is not an error, so the runtime hands it to the model and never ends the turn on its text; a fit or variety refusal carries `status: "needs_revision"` and the same `slides` / `variety` payload as before
- **AND** each revision's text (fit, variety, identical resend) ends with: `Your very next message MUST be a new build_presentation call with these fixes applied, never a final answer, unless the user must decide something first.`
- **AND** an unreadable plan, `slides` and `changes` together, empty `changes`, no deck to change, changes that cannot be applied, a plan whose every slide is empty, the previous deck unreadable, the template not loadable, a busy server, a render failure, an upload failure, or a template whose analysis is not ready stay errors

#### Scenario: Remedies only name what the content can fill

- **WHEN** a fit problem's close-kind options, a variety option or a variety suggestion would name a template slide whose framed picture area (one that shows a frame left empty) none of the slides concerned can fill, as they hold no image
- **THEN** that template slide is not offered, and its kind is not proposed through it (a `cards` variant with a picture per item is never offered for slides without images; another `cards` variant without pictures still is)

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

#### Scenario: Partial fix after needs_revision

- **WHEN** a call returns `needs_revision` for slides 4 and 9 of a 12-slide plan and the model calls again with only `changes` replacing or editing slides 4 and 9
- **THEN** the changes are applied to the refused plan, the whole 12-slide plan goes through assignment, fit check, variety rules and render as a full call would, and the other ten slides are exactly those of the refused plan

#### Scenario: Success message invites correction

- **WHEN** a deck is built with kind substitutions, truncations, removed leftovers or lost content
- **THEN** the result names them per slide and allows another call with the whole corrected deck

#### Scenario: Actionable messages

- **WHEN** either tool returns a text to the model (a problem, a note, an error, a variety ask, a delivery)
- **THEN** the text states what happened, why, and one concrete remedy, or says there is nothing to do; a result that builds nothing starts "No deck was built", and the delivery prefixes stay unchanged

#### Scenario: Renderer findings reach the model

- **WHEN** the render finds something the after-check report does not carry (an agenda announcing more parts than slides follow it, a one-line heading that runs into the text below, an items slide given no items, content sent to a fixed slide, a table it cannot fit)
- **THEN** the delivery's "To review" notes hold one line for it with its remedy (`Slide 2: the agenda announces 6 parts but only 2 slide(s) follow it. Add the missing slides or remove those parts from the agenda; otherwise nothing to do.`), after the unchanged success prefix; findings the report already names stay in the logs only

### Requirement: Rendering only fills the template

The system SHALL build each slide by instantiating a layout or duplicating an example slide and filling its slots; it SHALL never draw shapes the template does not hold, and the original example slides SHALL never appear in the output.

#### Scenario: Duplicated slide keeps its look

- **WHEN** an example slide is duplicated
- **THEN** its pictures and media share the template's parts, its colour-map override and speaker notes are copied, and only image, media and external hyperlink relationships are re-created

#### Scenario: Template sections dropped

- **GIVEN** a template whose slides are grouped in sections
- **WHEN** a deck or the patterns deck is rendered
- **THEN** it holds no section list, so PowerPoint opens it without offering a repair

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
- **THEN** the unused items and the decoration drawn only for them are removed (the frame around an item and what it holds, a mark just above or beside it, a connector to it), whether the slide or its layout draws it, and the kept items are recentred with their own decoration

#### Scenario: An unused item's frame drawn on the layout

- **GIVEN** a layout drawing a card, tile or dot for each item of its example slide
- **WHEN** the slide is filled with fewer items
- **THEN** the layout's graphics are copied onto that slide only, behind its own shapes, the layout's are hidden there, and the unused items' ones are removed like the slide's own; a slide using every item keeps its layout untouched

#### Scenario: Overflow control

- **WHEN** a text is too long for its slot at its font size
- **THEN** the font is reduced down to a floor, measured with the font the slot is drawn in; text still too long is cut at a word boundary and reported, and shrinking alone is not reported as a truncation

#### Scenario: Images from team folders

- **WHEN** the plan names a valid image document for a slide with an image slot
- **THEN** it fills the slot's frame keeping its aspect ratio, centre-cropped rather than letterboxed, in the slot's own shape (a round frame stays round) and with the example picture's alt text; an image slot left empty is removed, and an invalid reference is named in the result

#### Scenario: A text zone left empty is removed

- **GIVEN** a slide whose text zone is a text box drawn with its own fill or outline (a panel), not a placeholder
- **WHEN** the plan gives that zone nothing
- **THEN** the box is removed with its fill, as an empty placeholder is; a shape that is no zone stays

#### Scenario: Fewer team photos than the template shows

- **GIVEN** a team slide of four members, each a photo over a name
- **WHEN** it is filled with three members
- **THEN** each photo is recentred with its name, exactly as far

#### Scenario: Section numbers

- **GIVEN** section slides whose template slide has a number zone
- **WHEN** the plan gives no `number` for them
- **THEN** each shows its place among the deck's section slides (01, 02…), written as the zone's example writes it (zero-padded when the example is); a `number` the plan gives is shown as is; a number on a slide without a number zone is not lost content

#### Scenario: Columns sent as one object

- **WHEN** a slide's `columns` is one object instead of a list (in `slides`, or as a `changes` edit value)
- **THEN** nothing is built: a `slides` call gets `needs_revision` with `columns sent as one object, not a list` and the list form as its option; an edit of a list field with one object is refused, naming the whole list or `columns[i]` as the fix
- **AND** two edits of the same field of one slide in one call are refused, since the second would replace the first

#### Scenario: Malformed plan from the model

- **WHEN** the plan has wrong JSON shapes (a bullet list as one string, a field under an alias or given twice, a non-object entry)
- **THEN** the tool coerces what it can without losing text, a non-object entry is named in the result, and a key it cannot map is a `needs_revision` problem

#### Scenario: A two-column slide takes columns only

- **WHEN** a slide sends `bullets` and no `columns`, and a `two_columns` or `comparison` template slide has two body zones
- **THEN** that template slide does not fit it (`bullets: this slide has no place for it`, option: give the points as `columns`), as the catalogue lists `columns.bullets×2` for it; the list is never cut over the two columns
- **AND** a template slide that takes `columns` and has headings but no title zone is listed without `title`, and a titled slide does not fit it (option: another kind, never "drop title")

#### Scenario: A takeaway zone beside a body is never a column

- **GIVEN** a template slide with a body and, beside it, a takeaway zone
- **WHEN** the catalogue lists it or a slide is placed on it
- **THEN** its body is `bullets` at its own room, never `columns.bullets×2` capped by the takeaway zone, and the takeaway zone holds only the takeaway shown on the slide, else it is left empty and removed
- **AND** a takeaway zone that is the slide's only body holds its bullets when the takeaway is not shown

#### Scenario: A closing's single text box holds its bullets

- **WHEN** a closing slide's only free text zone is one body and the plan gives it several bullets
- **THEN** the bullets go in that body as a list, as its catalogue room says, instead of one bullet per box (which suits contact details)
- **AND** a closing shown on a section slide (no closing fits) gets no section number and does not count among the deck's sections

#### Scenario: A key figure's label under its heading

- **WHEN** a `figures` slide's cards have a number and a heading zone but no label zone, and an item gives `label`
- **THEN** the label is a line under the item's heading, never refused as content with no place

#### Scenario: Symbol bullets LibreOffice cannot show

- **WHEN** the template draws a bullet in Wingdings 3, which LibreOffice cannot recode
- **THEN** the preview copy draws it as `►` in Arial; the delivered `.pptx` keeps the template's glyph

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

#### Scenario: Built-in deck read by the rules

- **WHEN** the built-in deck is analysed without a vision model
- **THEN** its agenda is a list of up to seven numbered entries, its section slides read as `section` with a number zone that never takes the subtitle, each timeline milestone carries its date as the item's number, its table takes up to five columns, its statement slides read as `quote`, and each item slide removes an unused item with its card, tile or dot

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

#### Scenario: Several build calls in one model round

- **WHEN** one assistant message asks for several `build_presentation` calls (fragments of one deck, or copies of one call)
- **THEN** only the first in that message's order is run, whichever finishes first, and each other call builds nothing; its result says how many calls were sent at once, which one is processed (by its first slide's title), that a deck is sent in ONE call with every slide, cover first, and that a delivered deck is changed with `changes` (`insert` after N, `replace`, `edit`)
- **AND** a tool called outside the agent loop runs one call at a time, a copy of a delivered deck then being answered as unchanged

#### Scenario: Resend of the deck just delivered

- **GIVEN** a deck delivered in this turn
- **WHEN** a `slides` call assigns exactly that deck (same file name, every slide with the same content and template slide)
- **THEN** nothing is rendered, uploaded or stored and no preview is added; the result, not an error, says "unchanged, deck already delivered as '<file>'", not to tell the user it was changed, and to send `changes` to change it
- **AND** another file name or other content is built as a new deck

#### Scenario: What was built

- **WHEN** a deck is delivered with a preview
- **THEN** the preview part carries, per rendered slide, its place in the deck, its part of a split list, its title, kind and template slide, and note codes for what was cut, left out, continued or built as another kind, taken from the render and not from the model's reply; the card and pane show an info button opening that account in the user's language, and a `ppt_filler` deck (no summary) shows no button

#### Scenario: Preview unavailable

- **WHEN** PDF conversion fails or is unavailable
- **THEN** the chat shows a download chip and the agent is told the preview is unavailable

### Requirement: Chat-time corrections are per conversation

The system SHALL let the user correct a deck in chat by regenerating from an amended plan, and SHALL NOT change the agent configuration from a conversation. `build_presentation` SHALL accept either the whole deck (`slides`) or `changes` (replace, insert after, remove, move, edit one field) numbered on the last deck it delivered or plan it proposed in this conversation, stored per conversation and agent so any replica and any later turn reads it (within a turn, on the `slides` plan it last refused with `needs_revision`, never stored; a refused `changes` call leaves that base as it was, so its corrected resend carries every change again), and SHALL always render the whole resulting deck through the normal path.

#### Scenario: Later-turn edit keeps untouched slides

- **WHEN** a deck was delivered in an earlier turn and the user asks to put a phone number on the last slide, and the model sends only `changes` editing that slide
- **THEN** the whole deck is rebuilt from the stored plan with that one change, every other slide of the plan is identical to the delivered plan's, and the result is a normal delivery

#### Scenario: Replace that only changes text keeps the design

- **GIVEN** a delivered deck whose closing slide was built on one of two closing template slides
- **WHEN** a `changes` call replaces it with a closing slide whose text differs and that still fits that template slide
- **THEN** the rebuilt closing slide is on the same template slide; a replacement of another kind, or one that no longer fits there, is assigned as any slide
- **AND** a slide whose requested kind the template replaced (a timeline built on one of two process slides) stays on that template slide when an unrelated change rebuilds the deck
- **AND** a template slide pin written by the model itself (`built_on`, `asked_design`, `asked_from` in a sent slide) is ignored: only delivery and `like` set it
- **AND** a whole deck resent in `slides` after a delivery: a slide identical to a delivered slide keeps that slide's template slide while it fits; a changed slide is assigned as any slide
- **AND** the tool description tells the model to change text inside a slide with `edit`, which keeps the slide's design, and to use `replace` for a different slide

#### Scenario: Same design as another slide

- **GIVEN** a delivered deck whose bullets slides 5 and 7 were spread over two template slides by the variety rules
- **WHEN** the user asks for slide 7 with the same layout as slide 5 and the model sends `{op: "edit", slide: 7, field: "like", value: 5}`
- **THEN** slide 7 is rebuilt on the template slide slide 5 has in the delivered file (read from the stored deck, whatever the same call changes on slide 5), counted for nobody's variety ask, and the stored deck pins it there as any slide
- **AND** content that does not fit that template slide, or a kind it does not hold, builds nothing and `needs_revision` names slide 5's design, what does not fit (or the kind it holds) and the remedy (shorten, reshape, set that kind, or drop the `like`)
- **AND** a `like` with no slide number, a number out of range, the slide itself, a slide removed by the same call, a second `like` on one slide, or a slide not yet in a delivered deck builds nothing, with what, why and the remedy
- **AND** a design with a picture area asked for a slide with no picture builds nothing: `needs_revision` says the picture area would stay empty, with the remedies (a picture from `list_images_in_folder`, or drop the `like`)
- **AND** the tool description tells the model to use `like` when the user wants the layout or design of another slide

#### Scenario: The delivery names each slide's design

- **GIVEN** a deck delivered with bullets slides 5, 6 and 7 on three template slides and a process list split over slides 2 and 3
- **WHEN** the model reads the success text
- **THEN** one `Designs:` line names, per file slide number, the template slide's label as the review shows it (`2 'Process' · 3 'Process'`, three different names for slides 5 to 7), never a template id, and says that different names look different and that `like` gives slide N the design of slide M
- **AND** two included template slides sharing a label read as distinct names (`'Free text'`, `'Free text #2'`), and a label longer than 28 chars is cut, two labels cut to the same text being numbered the same way

#### Scenario: Changes that change nothing

- **GIVEN** a delivered deck
- **WHEN** a `changes` call leaves every slide's content and template slide as they are and keeps the file name (for example slide 7's current kind and bullets sent again, a replacement identical to the slide, or a `like` naming the design the slide already has)
- **THEN** nothing is built or stored and the result, not an error, says nothing changed, why (the values sent are the current ones), not to tell the user it was changed, and the remedy (`edit` with the new text, `like` for another slide's design)

#### Scenario: New slide written in the change itself

- **WHEN** a `replace` or `insert` change carries slide fields (`title`, `items`, `kind`…) beside `op` and no `slides`
- **THEN** those fields are read as its one new slide
- **AND** slide fields beside a non-empty `slides`, or on an `edit` or `remove`, build nothing and the result says which fields, why they cannot be read, and where to put them

#### Scenario: Bad change

- **WHEN** a `changes` call names a slide the previous plan does not have, an unknown operation, a field the slide does not have, or two changes on the same slide
- **THEN** nothing is built and the result names each bad change, why, and the remedy (`changes[2] (remove): slide 14 does not exist; the previous deck has 12 slides. Use a number from 1 to 12.`), and the stored plan is unchanged

#### Scenario: No previous plan

- **WHEN** a `changes` call arrives in a conversation where the tool has delivered no deck and this turn has evaluated no plan
- **THEN** nothing is built and the result says there is no previous deck to change and to send the whole deck in `slides`

#### Scenario: A refused changes call leaves no trace

- **WHEN** a `changes` call is refused (`needs_revision`, a variety ask, or a bad change) and the model sends another `changes` call in the same turn, of any shape (the refused changes corrected, or other changes)
- **THEN** it applies to the deck the refused call applied to (the delivered deck, or a refused or proposed `slides` plan), never to the refused plan, so nothing is inserted, removed or edited twice and no edit of the refused call reaches the deck unless sent again
- **AND** the refused slides are numbered on that deck, as the corrected call numbers them; a slide the refused changes sent (an insert) is pointed to its change (`new, sent in changes[0]: fix it there`)
- **AND** once a deck is delivered, changes of the same shape sent again are a new change to that deck (a second insert after slide 2 adds a slide beside the first)

#### Scenario: A kind edit clears what the new kind cannot hold

- **GIVEN** a delivered deck whose slide 10 is a `bullets` slide
- **WHEN** a `changes` call edits slide 10's `kind` to `two_columns`, its `title` and its `columns`, and leaves its bullets
- **THEN** the bullets are cleared, since no `two_columns` slide of the template shows them beside columns, the title and notes stay, and the deck is built
- **AND** the result says slide 10's bullets were cleared and why
- **AND** a field the same call sets is never cleared, and an edit to the kind the slide already has clears nothing

#### Scenario: A drop option gives its exact change

- **WHEN** a `changes` call is refused and an option asks to drop a whole slide field (`drop bullets`)
- **THEN** the option carries the change that does it, numbered on the deck the changes apply to (`drop bullets: {"op": "edit", "slide": 10, "field": "bullets", "value": []}`), and that change clears the field; a slide the changes replace or add keeps its options in words
- **AND** a refused `slides` call keeps the option in words

#### Scenario: A call identical to one already refused

- **GIVEN** a call refused with `needs_revision` for fit problems in this turn
- **WHEN** the model sends the identical call again (same arguments, same base plan) before any deck is delivered
- **THEN** it is not evaluated again: the result says it is the same call as one already refused, restates the problems briefly, and suggests sending each listed slide whole with `replace` or dropping the change (leaving the slide out for a `slides` call)

#### Scenario: A refused plan is never the next turn's base

- **GIVEN** a delivered deck
- **WHEN** a `changes` call is refused with `needs_revision` (or a variety ask) and the turn ends
- **THEN** the stored base is still the delivered deck, so the next turn's `changes` number on the file the user has

#### Scenario: User asks for a different kind of slide

- **WHEN** the user says a slide should be another kind of slide
- **THEN** the agent rebuilds the deck with that slide's `kind` changed, and the stored analysis and overrides are unchanged

#### Scenario: An insert at the start

- **GIVEN** a delivered deck that opens on the template's cover
- **WHEN** a `changes` call inserts slides, or moves a slide, with `after` 0
- **THEN** they open the deck as sent, never moved behind the cover

#### Scenario: The result names what changed

- **GIVEN** a deck delivered earlier in the conversation
- **WHEN** a new deck is delivered (by `changes` or a `slides` resend)
- **THEN** the result lists the slides of the new file that changed or were added, the previous deck's slides removed, the slides found at another place (`moved: 3 (was 2)`), and how many stayed unchanged
- **AND** slides are compared by what the delivered files show (each slide's XML with the charts and pictures it uses), so an edit that renders the same (a chart setting already in place, a replacement with the same content) is no change; a slide whose speaker notes alone differ is listed as changed in the speaker notes only, the slide itself looking the same
- **AND** inside a run of differing slides, a before and an after slide are paired by the words they share, in order, so a resend that drops one slide and edits the next names the slide that went
- **AND** a changed slide on another design holding fewer points (bullets, column bullets, items, table rows; a list continued on the next slides counted whole) is listed with both counts (`fewer points where the design changed: slide 8 (7 → 6)`)
- **AND** when no slide differs, the result says so and to tell the user the deck is the same; when a `slides` resend changed, added or removed at most two slides and kept more, the result adds that such an edit is sent as `changes`

#### Scenario: Move a slide

- **GIVEN** a delivered deck
- **WHEN** a `changes` call sends `{"op": "move", "slide": 2, "after": 3}`
- **THEN** slide 2, with any edit the same call makes to it, goes after slide 3 (first for `after` 0), a slide moved after another moved slide follows it, and the deck is built
- **AND** a move without `after`, after the slide itself, of a slide the same call removes, a second move of one slide, or moves forming a loop build nothing, with what, why and the remedy

#### Scenario: Slides and changes sent together

- **WHEN** a call sends both `slides` and `changes`
- **THEN** nothing is built and the one-line result names the one to send: only `slides`, every slide of the deck in order (the slides `changes` added included), while no deck was delivered; only `changes` once the user has a deck

