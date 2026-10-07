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
- **THEN** the analysis is reported as interrupted once its lease expires and can be re-run
- **AND** a re-run on a replica without the model port the save left records that it labelled by rules; the agent stays usable on it, and the next save that carries a model port re-runs it with vision

#### Scenario: Agent unavailable while analysing

- **WHEN** an agent's template analysis is pending or running
- **THEN** the agent is shown as unavailable, with the reason, on the team agents page and cannot be selected in the chat agent picker

#### Scenario: Agent available when analysis succeeds

- **WHEN** the analysis succeeds
- **THEN** the agent becomes available without another save

#### Scenario: Agent becomes available on next listing after analysis completes

- **WHEN** the analysis succeeds while nobody has the agent form open
- **THEN** the next listing of the team's agents re-checks the agent and shows it available, and a pod that does not answer in time leaves it unavailable without delaying the listing
- **AND** a failed analysis is not re-checked by the listing; it changes on a save, a re-run or the form's re-check
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
- **THEN** the agent stays unavailable, the agent form shows the error, and an author who can edit the agent may re-run the analysis from the stored template

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

- **WHEN** a user who cannot edit the agent requests its analysis status, thumbnails or a re-run
- **THEN** the request is refused

#### Scenario: Analysis rules change

- **GIVEN** an agent whose succeeded analysis was produced by older analysis rules
- **WHEN** its readiness is checked, a turn reads the analysis, or the agent is saved
- **THEN** the agent stays available and its turns keep using the stored analysis, and one re-run starts in the background from the stored template, without a user token
- **AND** concurrent checks on any replica start no second re-run while one is running, and the agent form shows the analysis as current meanwhile
- **AND** once the re-run succeeds its result is used; when it fails, the stored analysis stays in use, no re-run starts automatically again, and the form offers the re-run action, which re-runs it the same way

#### Scenario: Vision-labelled analysis refreshed only with its model

- **GIVEN** an outdated succeeded analysis labelled by a vision model
- **WHEN** its readiness is checked or a turn reads it on a replica that holds no model port remembered from the agent's last save
- **THEN** no re-run starts, the agent stays available on the stored analysis, and the agent form shows it as outdated with the hint that saving the agent re-reads it with its vision model
- **AND** on a replica holding that port, one re-run starts as for a rules-labelled analysis, and a save always starts one with the port it remembers
- **AND** a forced re-run on a replica without the port records the rules labelling it used, so a later save with the port relabels it with vision

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

#### Scenario: Variety not triggered by a split list

- **GIVEN** a first deck of the conversation and a variety check that is not `off`
- **WHEN** one slide's list is split over two slides of the same template slide
- **THEN** the two parts count as one slide: no variety ask, repeat note or "same template slide" note names them, while another slide using that template slide still counts normally

#### Scenario: Split cap reached

- **WHEN** a list needs more than two slides of its kind (17 items where the kind's largest slide holds 8) and no close kind holds it whole
- **THEN** no deck is written and `needs_revision` names the slide, the kind's capacity over two slides, and the options to trim to what two slides hold or move the rest to slides of the model's own

#### Scenario: Model's numbering after a split

- **WHEN** slide 2 of a plan is split over two slides and slide 5 has a review note
- **THEN** every message names slides by the plan's numbers (the note says slide 5, not 6), the stored base plan is the plan as sent, so a later `changes` call numbers on it, and an agenda split over two slides announces its items once, the slides that follow being counted after its last part

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

- **GIVEN** a conversation whose history holds no delivered deck yet
- **WHEN** the variety check is `template_slide` (the default) and the assignment uses one template slide that is not a cover, section, agenda or closing three times or more, and the template has an unused variant of its kind or an unused slide of another such kind
- **THEN** no deck is written and `needs_revision` names the repeated slides and the alternatives with the content each suits; the next call is built as sent, even when it repeats the same plan

#### Scenario: Later deck keeps the note

- **GIVEN** a conversation where a deck was already delivered
- **WHEN** a new plan uses one template slide three times or more
- **THEN** the deck is built and the repetition is only reported in the success message

#### Scenario: First deck read from the conversation history

- **GIVEN** the messages sent to the model in the current turn
- **WHEN** they hold an earlier `build_presentation` result that delivered a deck
- **THEN** the conversation has a deck and no variety ask is returned
- **AND** when its only `build_presentation` results are `needs_revision` or errors, the conversation still has no deck and the first call of the turn may ask

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
- **THEN** neither its suggestions nor its options offer `figures`; a kind is offered only while its distinct variants outnumber the deck's slides of that kind, counting each suggestion of the same answer

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

#### Scenario: Partial fix after needs_revision

- **WHEN** a call returns `needs_revision` for slides 4 and 9 of a 12-slide plan and the model calls again with only `changes` replacing or editing slides 4 and 9
- **THEN** the changes are applied to the refused plan, the whole 12-slide plan goes through assignment, fit check, variety rules and render as a full call would, and the other ten slides are exactly those of the refused plan

#### Scenario: Success message invites correction

- **WHEN** a deck is built with kind substitutions, truncations, removed leftovers or lost content
- **THEN** the result names them per slide and allows another call with the whole corrected deck

#### Scenario: Actionable messages

- **WHEN** either tool returns a text to the model (a problem, a note, an error, a variety ask, a delivery)
- **THEN** the text states what happened, why, and one concrete remedy, or says there is nothing to do; a result that builds nothing starts "No deck was built", and the delivery prefixes and the duplicate "Ignored:" prefix stay unchanged

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

#### Scenario: Same call sent twice in parallel

- **WHEN** the model sends the same build call twice at the same time
- **THEN** one deck is built, the copy is answered as ignored without building, and a different plan sent in parallel is built after the first

#### Scenario: Preview unavailable

- **WHEN** PDF conversion fails or is unavailable
- **THEN** the chat shows a download chip and the agent is told the preview is unavailable

### Requirement: Chat-time corrections are per conversation

The system SHALL let the user correct a deck in chat by regenerating from an amended plan, and SHALL NOT change the agent configuration from a conversation. `build_presentation` SHALL accept either the whole deck (`slides`) or `changes` (replace, insert after, remove, edit one field) numbered on the last plan it evaluated in this conversation (delivered or refused with `needs_revision`), stored per conversation and agent so any replica and any later turn reads it, and SHALL always render the whole resulting deck through the normal path.

#### Scenario: Later-turn edit keeps untouched slides

- **WHEN** a deck was delivered in an earlier turn and the user asks to put a phone number on the last slide, and the model sends only `changes` editing that slide
- **THEN** the whole deck is rebuilt from the stored plan with that one change, every other slide of the plan is identical to the delivered plan's, and the result is a normal delivery

#### Scenario: Bad change

- **WHEN** a `changes` call names a slide the previous plan does not have, an unknown operation, a field the slide does not have, or two changes on the same slide
- **THEN** nothing is built and the result names each bad change, why, and the remedy (`changes[2] (remove): slide 14 does not exist; the previous deck has 12 slides. Use a number from 1 to 12.`), and the stored plan is unchanged

#### Scenario: No previous plan

- **WHEN** a `changes` call arrives in a conversation where the tool has evaluated no plan
- **THEN** nothing is built and the result says there is no previous deck to change and to send the whole deck in `slides`

#### Scenario: Corrected resend of refused changes

- **WHEN** a `changes` call is refused with `needs_revision` and the model resends changes of the same shape (same operations on the same slide numbers and fields), corrected or identical, in the same turn (for example the inserted slide fixed, sent again as an insert, or a resend after a variety ask that says a resend is built as is)
- **THEN** they are applied to the plan the refused changes were applied to, so nothing is inserted, removed or edited twice

#### Scenario: User asks for a different kind of slide

- **WHEN** the user says a slide should be another kind of slide
- **THEN** the agent rebuilds the deck with that slide's `kind` changed, and the stored analysis and overrides are unchanged
